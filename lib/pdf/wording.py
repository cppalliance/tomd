"""Wording section detection via multi-signal HSV color + drawing analysis.

Detects ins/del markup in WG21 PDF papers by combining three signals:
  1. Block-level color contamination filter - blocks containing non-green/
     non-red chromatic colors (purple, orange, cyan) are syntax-highlighted
     code and are skipped entirely.
  2. Line-level colored fraction - only lines where the majority (>50%) of
     non-link characters are green or red are treated as wording lines.
     This rejects accent-color hyperlinks scattered through prose.
  3. Span-level classification - green spans on wording lines become ins;
     red spans with a confirmed strikethrough drawing become del.

Hyperlinks (span.link_url set) are excluded from all checks and fractions.
Insertions require no drawing decoration. Deletions require a strikethrough
drawing whose width overlaps at least 30% of the span to avoid matching
table borders and decorative rules.
"""

import colorsys
import logging
from collections import Counter

from .types import Block

_log = logging.getLogger(__name__)

_SATURATION_THRESHOLD = 0.15
_GREEN_HUE_MIN = 90
_GREEN_HUE_MAX = 180
_RED_HUE_WRAP = 30
_BLUE_HUE_MIN = 210
_BLUE_HUE_MAX = 270
_UNDERLINE_Y_TOLERANCE = 1.5
_STRIKETHROUGH_Y_TOLERANCE = 2.0
_STRIKETHROUGH_OVERLAP_MIN = 0.3
_WORDING_LINE_MAJORITY = 0.5
_MIN_WORDING_SPANS = 5


def _color_int_to_rgb(color_int: int) -> tuple[float, float, float]:
    """Convert MuPDF integer color to (r, g, b) in 0-1 range."""
    if color_int == 0:
        return (0.0, 0.0, 0.0)
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)


def _rgb_to_hue_sat(r: float, g: float, b: float) -> tuple[float, float]:
    """Convert RGB (0-1) to hue (0-360 degrees) and saturation (0-1)."""
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s


def _is_chromatic(s: float) -> bool:
    return s >= _SATURATION_THRESHOLD


def _classify_hue(h: float) -> str | None:
    """Map hue angle to candidate neighborhood, or None for other hues."""
    if _GREEN_HUE_MIN <= h <= _GREEN_HUE_MAX:
        return "green"
    if h <= _RED_HUE_WRAP or h >= (360 - _RED_HUE_WRAP):
        return "red"
    if _BLUE_HUE_MIN <= h <= _BLUE_HUE_MAX:
        return "blue"
    return None


def _match_strikethrough(span_bbox, drawings: list) -> bool:
    """True if a horizontal drawing crosses the vertical center of the span.

    Requires the drawing to overlap at least _STRIKETHROUGH_OVERLAP_MIN of
    the span width, rejecting full-page table borders and decorative rules.
    """
    if not drawings:
        return False
    sx0, sy0, sx1, sy1 = span_bbox
    y_center = (sy0 + sy1) / 2.0
    span_w = max(sx1 - sx0, 1.0)
    for dy, dx0, dx1, _ in drawings:
        if abs(dy - y_center) > _STRIKETHROUGH_Y_TOLERANCE:
            continue
        overlap = min(dx1, sx1) - max(dx0, sx0)
        if overlap / span_w >= _STRIKETHROUGH_OVERLAP_MIN:
            return True
    return False


def _block_has_foreign_colors(block: Block) -> bool:
    """True if the block contains non-green/red/blue chromatic spans.

    Indicates syntax-highlighted code where accent colors (purple, orange,
    cyan) appear alongside green/red. Hyperlink spans are excluded since
    blue links are expected in wording sections. Returns False for blocks
    that contain only black, green, red, and blue (hyperlink) text.
    """
    for line in block.lines:
        for span in line.spans:
            if span.link_url:
                continue
            if not span.text.strip():
                continue
            h, s = _rgb_to_hue_sat(*_color_int_to_rgb(span.color))
            if _is_chromatic(s) and _classify_hue(h) is None:
                return True
    return False


def _line_colored_fraction(line) -> float:
    """Fraction of non-link non-whitespace characters that are green or red.

    Hyperlink spans are excluded from both numerator and denominator so
    that a line full of red hyperlinks doesn't appear to be wording markup.
    """
    total = green = red = 0
    for span in line.spans:
        if span.link_url:
            continue
        n = len(span.text.replace(" ", ""))
        if n == 0:
            continue
        total += n
        h, s = _rgb_to_hue_sat(*_color_int_to_rgb(span.color))
        if _is_chromatic(s):
            hue = _classify_hue(h)
            if hue == "green":
                green += n
            elif hue == "red":
                red += n
    return (green + red) / total if total else 0.0


def _build_body_color(blocks: list[Block]) -> tuple[float, float, float]:
    """Identify the dominant body text color."""
    color_counts: Counter[int] = Counter()
    for b in blocks:
        for ln in b.lines:
            for s in ln.spans:
                if s.text.strip():
                    color_counts[s.color] += len(s.text)
    if not color_counts:
        return (0.0, 0.0, 0.0)
    dominant = color_counts.most_common(1)[0][0]
    return _color_int_to_rgb(dominant)


def collect_line_drawings(page) -> list[tuple[float, float, float, tuple]]:
    """Collect horizontal line drawings from a page for decoration detection.

    Returns list of (y, x0, x1, color_rgb) for horizontal lines.
    """
    lines = []
    try:
        for drawing in page.get_drawings():
            items = drawing.get("items", [])
            color = drawing.get("color")
            if not color or not isinstance(color, (tuple, list)):
                continue
            for item in items:
                if item[0] != "l":
                    continue
                p1 = item[1]
                p2 = item[2]
                if abs(p1.y - p2.y) < 1.0:
                    y = (p1.y + p2.y) / 2.0
                    x0 = min(p1.x, p2.x)
                    x1 = max(p1.x, p2.x)
                    if x1 - x0 > 5.0:
                        lines.append((y, x0, x1, tuple(color)))
    except Exception:
        # MuPDF can raise various internal errors from get_drawings()
        _log.debug("get_drawings() failed", exc_info=True)
    return lines


def classify_wording(blocks: list[Block],
                     page_drawings: dict[int, list]) -> list[str]:
    """Classify spans as ins/del/context using multi-signal analysis.

    Three-layer filter:
      1. Blocks with foreign chromatic colors (not green/red/blue) are
         skipped - they are syntax-highlighted code, not wording markup.
      2. Only lines where >50% of non-link characters are green or red
         are classified - this rejects accent-color hyperlinks in prose.
      3. Green spans on majority lines become ins (no drawing required).
         Red spans on majority lines become del only with a confirmed
         strikethrough drawing (requires 30% span overlap to reject borders).

    Sets span.wording_role on matching spans.
    Returns a list of problem descriptions for the prompts file.
    """
    candidates: list[tuple] = []

    for block in blocks:
        if _block_has_foreign_colors(block):
            continue

        drawings = page_drawings.get(block.page_num, [])

        for line in block.lines:
            if _line_colored_fraction(line) <= _WORDING_LINE_MAJORITY:
                continue

            for span in line.spans:
                if not span.text.strip():
                    continue
                if span.link_url:
                    continue

                rgb = _color_int_to_rgb(span.color)
                h, s = _rgb_to_hue_sat(*rgb)

                if not _is_chromatic(s):
                    # Non-chromatic span on a wording-majority line = context
                    if span.color != 0:
                        r, g, b = rgb
                        lightness = (r + g + b) / 3.0
                        if 0.25 < lightness < 0.65:
                            candidates.append((span, "context", "high"))
                    continue

                hue_class = _classify_hue(h)
                if hue_class == "blue":
                    continue

                if hue_class == "green":
                    candidates.append((span, "ins", "high"))
                elif hue_class == "red":
                    if _match_strikethrough(span.bbox, drawings):
                        candidates.append((span, "del", "high"))

    ins_del = [c for c in candidates if c[1] in ("ins", "del")]
    if len(ins_del) < _MIN_WORDING_SPANS:
        _log.debug("Too few wording candidates (%d < %d), skipping",
                    len(ins_del), _MIN_WORDING_SPANS)
        return []

    for span, role, _confidence in candidates:
        span.wording_role = role

    ins_count = sum(1 for _, r, _ in candidates if r == "ins")
    del_count = sum(1 for _, r, _ in candidates if r == "del")
    ctx_count = sum(1 for _, r, _ in candidates if r == "context")
    _log.info("Wording detected: %d ins, %d del, %d context",
               ins_count, del_count, ctx_count)

    return []
