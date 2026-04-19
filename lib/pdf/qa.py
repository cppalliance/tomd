"""Quality assurance metrics and scoring for Markdown conversion output.

Parses the Markdown output with mistune to validate structure from
the reader's perspective, not from pipeline internals.

DESIGN CONSTRAINT: compute_metrics() takes only a Markdown string.
No page count, no file format, no pipeline internals. Every signal
must be derivable from the Markdown text alone. This keeps scoring
format-agnostic (works on PDF output, HTML output, or any Markdown)
and prevents coupling between the scorer and the converter.
"""

import json
import logging
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import mistune

__all__ = ["QAMetrics", "compute_metrics", "run_qa_report"]

_log = logging.getLogger(__name__)

_FRONT_MATTER_RE = re.compile(r"^---\n(.+?\n)---", re.DOTALL)
_UNCERTAIN_MARKER = "tomd:uncertain"

_FRONT_MATTER_FIELDS = frozenset({"title", "document", "date", "reply-to", "audience"})
_WG21_DOC_NUM_RE = re.compile(r"[DPN]\d{3,5}R?\d*", re.IGNORECASE)

_STRUCTURAL_CODE_RE = re.compile(
    r"^\s*[{}]|"               # standalone brace lines
    r";\s*$|"                  # trailing semicolons (code statements)
    r"#include\s*<|"           # preprocessor includes
    r"\w+\s*\([^)]*\)\s*\{|"  # function_name(...) {
    r"\w+\s*\([^)]*\)\s*;",   # declaration: name(...);
    re.MULTILINE,
)


@dataclass
class QAMetrics:
    """Per-document quality metrics computed purely from Markdown text."""
    file: str = ""
    total_chars: int = 0
    heading_count: int = 0
    max_heading_level: int = 0
    code_block_count: int = 0
    list_count: int = 0
    table_count: int = 0
    front_matter_count: int = 0
    has_doc_number: bool = False
    uncertain_count: int = 0
    unfenced_code_lines: int = 0
    paragraph_count: int = 0
    empty_output: bool = False
    score: int = 100
    issues: list[str] = field(default_factory=list)


def _parse_front_matter(md_text: str) -> dict[str, str]:
    """Extract YAML front matter fields and values from Markdown text."""
    m = _FRONT_MATTER_RE.match(md_text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            key = line.split(":")[0].strip().lower()
            val = line.split(":", 1)[1].strip() if ":" in line else ""
            if key:
                fields[key] = val
    return fields


def _paragraph_plain_text(node: dict) -> str:
    """Get plain text from a paragraph, excluding inline code and HTML."""
    parts = []
    for child in node.get("children", []):
        if child["type"] == "text":
            parts.append(child.get("raw", ""))
    return " ".join(parts)


def _has_wording_markup(node: dict) -> bool:
    """True if a paragraph contains <ins> or <del> wording tags."""
    for child in node.get("children", []):
        if child["type"] == "inline_html":
            raw = child.get("raw", "")
            if raw.startswith(("<ins", "<del", "</ins", "</del")):
                return True
    return False


def _looks_like_code(node: dict) -> bool:
    """True if a paragraph looks like an unfenced code block.

    Checks only the plain-text children (not codespan or inline_html).
    Looks for structural code patterns — braces, semicolons, function
    declarations — not single keywords that appear naturally in prose.
    Wording sections (<ins>/<del> markup) are excluded since C++ syntax
    in proposed standard text is expected, not a missed code block.
    """
    children = node.get("children", [])
    if not children:
        return False
    if _has_wording_markup(node):
        return False
    text_children = [c for c in children if c["type"] == "text"]
    code_children = [c for c in children if c["type"] == "codespan"]
    if code_children and not text_children:
        return False
    text = _paragraph_plain_text(node)
    return bool(_STRUCTURAL_CODE_RE.search(text))


def _count_unfenced_code(paragraphs: list[dict]) -> int:
    """Count paragraphs that look like unfenced code blocks."""
    return sum(1 for p in paragraphs if _looks_like_code(p))


def compute_metrics(md_text: str, file: str = "") -> QAMetrics:
    """Compute QA metrics by parsing the Markdown output with mistune.

    Takes only the Markdown text. No page count, no format hints.
    Everything is derived from the text itself.
    """
    m = QAMetrics(file=file)
    m.total_chars = len(md_text)
    m.empty_output = m.total_chars == 0 or not md_text.strip()

    if m.empty_output:
        m.score, m.issues = 0, ["empty output"]
        return m

    ast_renderer = mistune.create_markdown(renderer="ast", plugins=["table"])
    tokens = ast_renderer(md_text)

    headings = [t for t in tokens if t["type"] == "heading"]
    m.heading_count = len(headings)
    if headings:
        m.max_heading_level = max(t["attrs"]["level"] for t in headings)

    m.code_block_count = sum(1 for t in tokens if t["type"] == "block_code")

    m.list_count = sum(1 for t in tokens if t["type"] == "list")

    m.table_count = sum(1 for t in tokens if t["type"] == "table")

    # Front matter: mistune doesn't parse YAML, so we check raw text.
    # The AST's leading thematic_break confirms the --- opener.
    fm_fields = _parse_front_matter(md_text)
    m.front_matter_count = sum(1 for f in _FRONT_MATTER_FIELDS if f in fm_fields)
    doc_val = fm_fields.get("document", "")
    m.has_doc_number = bool(_WG21_DOC_NUM_RE.search(doc_val))

    m.uncertain_count = sum(
        1 for t in tokens
        if t["type"] == "block_html" and _UNCERTAIN_MARKER in t.get("raw", "")
    )

    paragraphs = [t for t in tokens if t["type"] == "paragraph"]
    m.paragraph_count = len(paragraphs)
    m.unfenced_code_lines = _count_unfenced_code(paragraphs)

    m.score, m.issues = _score(m)
    return m


_LONG_DOC_PARAGRAPHS = 10


def _score(m: QAMetrics) -> tuple[int, list[str]]:
    """Compute 0-100 quality score purely from Markdown structure."""
    score = 100
    issues: list[str] = []

    if m.empty_output:
        return 0, ["empty output"]

    is_long = m.paragraph_count >= _LONG_DOC_PARAGRAPHS

    if m.uncertain_count > 0:
        penalty = min(40, 8 * m.uncertain_count)
        score -= penalty
        issues.append(f"{m.uncertain_count} uncertain regions")

    if m.heading_count == 0 and is_long:
        score -= 25
        issues.append("no headings")

    if m.front_matter_count == 0 and is_long:
        score -= 10
        issues.append("no front matter")

    if m.unfenced_code_lines > 5:
        penalty = min(15, m.unfenced_code_lines)
        score -= penalty
        issues.append(f"{m.unfenced_code_lines} unfenced code lines")

    has_structure = (m.heading_count > 0) + (m.code_block_count > 0) + \
                    (m.list_count > 0) + (m.table_count > 0)
    if is_long and has_structure <= 1:
        score -= 10
        issues.append(f"low variety ({has_structure} structural types)")

    return max(0, score), issues


_HTML_EXTENSIONS = frozenset({".html", ".htm"})
_PDF_EXTENSIONS = frozenset({".pdf"})


def _qa_one(path_str: str) -> dict:
    """Run the appropriate pipeline and score the Markdown output."""
    path = Path(path_str)
    ext = path.suffix.lower()

    try:
        if ext in _HTML_EXTENSIONS:
            from ..html import convert_html
            md_text, _ = convert_html(path)
            m = compute_metrics(md_text, file=str(path))
            return asdict(m)

        from . import _run_pipeline
        r = _run_pipeline(path)

        if not r.readable:
            m = QAMetrics(file=str(path),
                          score=0, issues=["unreadable (scanned/encrypted PDF)"])
            return asdict(m)

        if r.skipped:
            m = QAMetrics(file=str(path),
                          score=100, issues=[f"{r.skip_reason} (skipped)"])
            return asdict(m)

        m = compute_metrics(r.md, file=str(path))
        return asdict(m)

    except Exception as exc:
        _log.error("Pipeline failed for %s: %s", path, exc)
        m = QAMetrics(file=str(path), score=0,
                      issues=[f"pipeline error: {exc}"])
        return asdict(m)


def _qa_metrics_from_dict(d: dict) -> QAMetrics:
    return QAMetrics(**d)


def run_qa_report(paths: list[Path], json_path: Path | None = None,
                  workers: int = 1, timeout: int = 120) -> None:
    """Run QA scoring on a list of PDF/HTML files and print a ranked report.

    Uses *workers* parallel processes (default 1 = sequential).
    *timeout* is seconds of no progress before aborting remaining files.
    """
    total = len(paths)
    results: list[QAMetrics] = []
    t0 = time.monotonic()

    if workers > 1:
        path_strs = [str(p) for p in paths]
        done_count = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            future_to_path = {pool.submit(_qa_one, s): s for s in path_strs}
            pending = set(future_to_path.keys())
            last_completion = time.monotonic()

            while pending:
                newly_done = {f for f in pending if f.done()}

                if newly_done:
                    last_completion = time.monotonic()
                    for f in newly_done:
                        pending.discard(f)
                        done_count += 1
                        path_str = future_to_path[f]
                        name = Path(path_str).name
                        elapsed = time.monotonic() - t0
                        rate = done_count / elapsed if elapsed > 0 else 0
                        eta = (total - done_count) / rate if rate > 0 else 0
                        print(f"\r  [{done_count}/{total}] {name:<40} "
                              f"{rate:.1f} files/s  ETA {eta/60:.0f}m",
                              end="", file=sys.stderr)
                        sys.stderr.flush()
                        try:
                            d = f.result()
                            results.append(_qa_metrics_from_dict(d))
                        except Exception as exc:
                            results.append(QAMetrics(
                                file=path_str, score=0,
                                issues=[f"error: {exc}"]))

                elif time.monotonic() - last_completion > timeout:
                    timed_out = []
                    for f in pending:
                        path_str = future_to_path[f]
                        timed_out.append(Path(path_str).name)
                        f.cancel()
                        results.append(QAMetrics(
                            file=path_str, score=0,
                            issues=[f"timeout (no progress for {timeout}s)"]))
                    done_count += len(pending)
                    print(f"\n  TIMEOUT: {len(timed_out)} files aborted: "
                          f"{', '.join(timed_out)}", file=sys.stderr)
                    break

                else:
                    time.sleep(0.5)

            pool.shutdown(wait=False, cancel_futures=True)
    else:
        for i, path in enumerate(paths, 1):
            elapsed = time.monotonic() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(f"\r  [{i}/{total}] {path.name:<40} "
                  f"{rate:.1f} files/s  ETA {eta/60:.0f}m",
                  end="", file=sys.stderr)
            sys.stderr.flush()
            d = _qa_one(str(path))
            results.append(_qa_metrics_from_dict(d))

    wall = time.monotonic() - t0
    print(f"\n  Finished in {wall/60:.1f} minutes "
          f"({wall/total:.1f}s/file avg)\n", file=sys.stderr)

    results.sort(key=lambda r: r.score)

    buckets = {"90-100": 0, "70-89": 0, "50-69": 0, "0-49": 0}
    for r in results:
        if r.score >= 90:
            buckets["90-100"] += 1
        elif r.score >= 70:
            buckets["70-89"] += 1
        elif r.score >= 50:
            buckets["50-69"] += 1
        else:
            buckets["0-49"] += 1

    print(f"\ntomd QA Report: {total} files")
    print("=" * 40)
    print("\nScore Distribution:")
    for label, count in buckets.items():
        pct = 100 * count / total if total else 0
        print(f"  {label}: {count:>6}  ({pct:.1f}%)")

    needs_review = sum(1 for r in results if r.score < 70)
    print(f"\nFiles needing review (score < 70): {needs_review}")
    print(f"Files probably OK (score >= 70):   {total - needs_review}")

    worst = [r for r in results if r.score < 100][:30]
    if worst:
        print(f"\nWorst {len(worst)} files:")
        print(f"  {'Score':>5}  {'File':<40}  Issues")
        print(f"  {'-----':>5}  {'-' * 40}  {'-' * 40}")
        for r in worst:
            name = Path(r.file).name
            if len(name) > 40:
                name = name[:37] + "..."
            issue_str = ", ".join(r.issues) if r.issues else "ok"
            print(f"  {r.score:>5}  {name:<40}  {issue_str}")

    if json_path is not None:
        rows = [asdict(r) for r in results]
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nDetailed metrics written to {json_path}")
