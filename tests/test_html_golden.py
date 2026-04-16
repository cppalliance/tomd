"""Golden regression: full HTML papers vs committed expected Markdown."""

import difflib
from pathlib import Path

import pytest

from lib.html import convert_html

_REPO = Path(__file__).resolve().parent.parent
_PAPERS = _REPO / "papers"
_GOLDEN = _REPO / "tests" / "fixtures" / "golden"

# Stems must match `papers/{stem}.html` and `tests/fixtures/golden/{stem}.golden.md`.
_GOLDEN_STEMS = (
    "p3411r5",
    "p2728r11",
    "p3953r0",
    "p4005r0",
    "p4020r0",
    "p3911r2",
    "n5034",
)


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_expected(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _diff_head(actual: str, golden: str, limit: int = 120) -> str:
    a_lines = _normalize_newlines(actual).splitlines(keepends=True)
    b_lines = _normalize_newlines(golden).splitlines(keepends=True)
    diff = difflib.unified_diff(
        b_lines, a_lines, fromfile="golden", tofile="actual", n=3,
    )
    return "".join(list(diff)[:limit])


@pytest.mark.parametrize("stem", _GOLDEN_STEMS)
def test_convert_html_matches_golden(stem: str):
    html_path = _PAPERS / f"{stem}.html"
    if not html_path.is_file():
        pytest.skip(f"missing paper HTML: {html_path} (papers/ is gitignored)")

    md, prompts = convert_html(html_path)
    golden_md = _GOLDEN / f"{stem}.golden.md"
    assert golden_md.is_file(), f"missing golden: {golden_md}"
    expected_md = _read_expected(golden_md)
    got_md = _normalize_newlines(md)
    exp_md = _normalize_newlines(expected_md)
    if got_md != exp_md:
        pytest.fail(
            f"Markdown mismatch for {stem}\n{_diff_head(md, expected_md)}",
        )

    golden_prompts = _GOLDEN / f"{stem}.golden.prompts.md"
    if golden_prompts.is_file():
        assert prompts is not None, f"expected prompts for {stem}"
        exp_p = _read_expected(golden_prompts)
        got_p = _normalize_newlines(prompts)
        exp_pn = _normalize_newlines(exp_p)
        if got_p != exp_pn:
            pytest.fail(
                f"Prompts mismatch for {stem}\n{_diff_head(prompts, exp_p)}",
            )
    else:
        assert prompts is None, f"unexpected prompts for {stem}"
