"""PDF to Markdown converter - pipeline entry point."""

import logging
import re
from collections import Counter
from pathlib import Path

from .cleanup import (get_edge_items, detect_repeating, strip_repeating,
                      cleanup_text, find_hidden_regions, strip_hidden_blocks)
from .extract import extract_mupdf, extract_spatial, collect_links, attach_links
from .mono import propagate_monospace
from .wording import classify_wording, collect_line_drawings
from .spans import normalize_spans
from .structure import compare_extractions, structure_sections
from .table import detect_tables, exclude_table_regions
from .wg21 import extract_metadata_from_blocks
from .emit import emit_markdown, emit_prompts
from .types import SectionKind, is_readable
from ..toc import find_toc_indices

__all__ = ["convert_pdf"]

_log = logging.getLogger(__name__)

_STANDALONE_PAGE_RE = re.compile(r'^\d{1,4}$')
_TOC_X_TOLERANCE = 5.0


def _toc_structural_hints(sections) -> list[bool]:
    """Mark sections that structurally resemble TOC entries.

    A section qualifies when its second non-empty text line is a bare page
    number AND its x coordinate clusters with other such candidates (the
    right-aligned page-number column). Used as a fallback for headingless
    wording papers where find_toc_indices would otherwise get an empty
    headings set.
    """
    from .types import Section as _Section  # local to avoid circular at module level

    candidates: list[tuple[int, float | None]] = []
    for i, sec in enumerate(sections):
        lines = [l.strip() for l in sec.text.split("\n") if l.strip()]
        if len(lines) >= 2 and _STANDALONE_PAGE_RE.match(lines[1]):
            x = None
            non_empty = [ln for ln in sec.lines if ln.text.strip()]
            if len(non_empty) >= 2 and non_empty[1].spans:
                x = non_empty[1].spans[0].bbox[0]
            candidates.append((i, x))

    if not candidates:
        return [False] * len(sections)

    xs = sorted(x for _, x in candidates if x is not None)
    med_x = xs[len(xs) // 2] if xs else None

    result = [False] * len(sections)
    for i, x in candidates:
        if med_x is None or x is None or abs(x - med_x) <= _TOC_X_TOLERANCE:
            result[i] = True
    return result


def _get_page0_text_colors(page) -> dict[float, float]:
    """Map y-positions to text lightness using texttrace space-color proxy.

    Type 3 fonts report black for all glyphs. Space characters (type=0)
    leak the true graphics-state fill color. Returns {rounded_y: lightness}
    where lightness is 0.0 (black) to 1.0 (white).
    """
    colors: dict[float, float] = {}
    for span in page.get_texttrace():
        if span.get("type") != 0:
            continue
        color = span.get("color")
        if color is None:
            continue
        chars = span.get("chars", [])
        if not chars:
            continue
        y = round(chars[0][2][1])
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            lightness = sum(color[:3]) / 3.0
        elif isinstance(color, (int, float)):
            lightness = float(color)
        else:
            continue
        colors[y] = lightness
    return colors


def convert_pdf(path: Path) -> tuple[str, str | None]:
    """Convert a PDF file to Markdown.

    Returns (markdown_text, prompts_text_or_none).
    Returns ("", None) for empty or unreadable PDFs.
    Raises fitz exceptions for corrupt or inaccessible files.
    """
    import fitz

    path = Path(path)
    doc = None
    try:
        doc = fitz.open(str(path))
        page_count = doc.page_count
        if page_count == 0:
            return "", None

        all_mupdf_blocks = []
        all_spatial_blocks = []
        all_edge_items = []

        for pg_num in range(page_count):
            page = doc[pg_num]
            page_height = page.rect.height

            mupdf_blocks = extract_mupdf(page, pg_num)
            spatial_blocks = extract_spatial(page, pg_num)

            edge_items = get_edge_items(mupdf_blocks, pg_num, page_height)
            all_edge_items.append(edge_items)

            links = collect_links(page)
            attach_links(mupdf_blocks, links)
            attach_links(spatial_blocks, links)

            all_mupdf_blocks.extend(mupdf_blocks)
            all_spatial_blocks.extend(spatial_blocks)

        font_counts: Counter[str] = Counter()
        for b in all_mupdf_blocks:
            for ln in b.lines:
                for s in ln.spans:
                    if s.text.strip():
                        font_counts[s.font_name.lower()] += len(s.text)
        body_fonts = {f for f, _ in font_counts.most_common(5)}

        all_hidden: set[tuple[float, float, float, float]] = set()
        for pg_num in range(page_count):
            page = doc[pg_num]
            all_hidden |= find_hidden_regions(page, body_fonts)

        page0_colors = _get_page0_text_colors(doc[0]) if page_count > 0 else {}

        page_drawings: dict[int, list] = {}
        for pg_num in range(page_count):
            drawings = collect_line_drawings(doc[pg_num])
            if drawings:
                page_drawings[pg_num] = drawings
    finally:
        if doc is not None:
            doc.close()

    if all_hidden:
        _log.info("Stripping text hidden by %d covered regions", len(all_hidden))
        all_mupdf_blocks = strip_hidden_blocks(all_mupdf_blocks, all_hidden)
        all_spatial_blocks = strip_hidden_blocks(all_spatial_blocks, all_hidden)

    mupdf_text = "\n".join(b.text for b in all_mupdf_blocks)
    if not is_readable(mupdf_text):
        _log.warning("Extracted text is not readable (encrypted/scanned PDF?)")
        return "", None

    repeating = detect_repeating(all_edge_items, page_count)
    if repeating:
        _log.info("Stripping %d repeating header/footer patterns", len(repeating))
        all_mupdf_blocks = strip_repeating(all_mupdf_blocks, repeating)
        all_spatial_blocks = strip_repeating(all_spatial_blocks, repeating)

    dominant_font = font_counts.most_common(1)[0][0] if font_counts else ""
    propagate_monospace(all_mupdf_blocks, all_spatial_blocks, dominant_font)

    wording_problems = classify_wording(all_mupdf_blocks, page_drawings)

    all_mupdf_blocks = cleanup_text(all_mupdf_blocks)
    all_spatial_blocks = cleanup_text(all_spatial_blocks)

    all_mupdf_blocks = normalize_spans(all_mupdf_blocks)
    all_spatial_blocks = normalize_spans(all_spatial_blocks)

    wg21_metadata, _ = extract_metadata_from_blocks(all_mupdf_blocks,
                                                     text_colors=page0_colors)

    table_sections, all_mupdf_blocks = detect_tables(all_mupdf_blocks)
    if table_sections:
        _log.info("Detected %d table(s)", len(table_sections))
        all_spatial_blocks = exclude_table_regions(
            all_spatial_blocks, table_sections)

    sections = compare_extractions(all_mupdf_blocks, all_spatial_blocks)

    for ts in table_sections:
        inserted = False
        for i, sec in enumerate(sections):
            if sec.page_num > ts.page_num:
                sections.insert(i, ts)
                inserted = True
                break
            if (sec.page_num == ts.page_num and sec.lines
                    and ts.lines
                    and sec.lines[0].bbox[1] > ts.lines[0].bbox[1]):
                sections.insert(i, ts)
                inserted = True
                break
        if not inserted:
            sections.append(ts)

    has_title = "title" in wg21_metadata
    structure_metadata, sections = structure_sections(sections, has_title=has_title)
    # Three metadata pathways, merged here in precedence order (last wins):
    #   1. structure._extract_metadata  - PDF section line scan (lowest precedence)
    #   2. wg21.extract_metadata_from_blocks - PDF block-level scan (wins on conflict)
    # HTML conversion uses a third pathway: html.extract.extract_metadata (DOM scan).
    metadata = {**structure_metadata, **wg21_metadata}

    texts = [sec.text.split("\n")[0].strip() for sec in sections]
    heading_texts = {sec.text.split("\n")[0].strip()
                     for sec in sections if sec.kind == SectionKind.HEADING}
    structural_hints = _toc_structural_hints(sections) if not heading_texts else None
    toc_indices = find_toc_indices(texts, heading_texts, structural_hints)
    if toc_indices:
        sections = [s for i, s in enumerate(sections) if i not in toc_indices]

    md = emit_markdown(metadata, sections)
    prompts = emit_prompts(sections)

    if wording_problems:
        wording_prompt = "\n\n".join(
            ["\n## Wording Detection Issues\n"] + wording_problems)
        if prompts:
            prompts += "\n" + wording_prompt
        else:
            prompts = "# tomd - Conversion Issues\n" + wording_prompt

    return md, prompts
