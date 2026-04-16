"""Wording section detection via multi-signal HSV color + drawing analysis.

Detects ins/del markup in WG21 PDF papers by combining two active signals:
  1. HSV color analysis - saturation gates chromaticity, hue identifies
     green (ins) vs red (del) vs blue (link) neighborhoods
  2. Drawing decoration - horizontal underlines (ins) and strikethroughs
     (del) from page.get_drawings() correlated with span bboxes

Document-level body-relative color clustering (_build_body_color) is
retained for planned v2 integration but not yet wired into classification.

Confidence depends on signal agreement, per the Multi-Signal Confidence rule.
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
    """Map hue angle to candidate neighborhood."""
    if _GREEN_HUE_MIN <= h <= _GREEN_HUE_MAX:
        return "green"
    if h <= _RED_HUE_WRAP or h >= (360 - _RED_HUE_WRAP):
        return "red"
    if _BLUE_HUE_MIN <= h <= _BLUE_HUE_MAX:
        return "blue"
    return None


def _match_drawing(span_bbox, drawings: list, tolerance: float,
                   anchor: str) -> bool:
    """True if a horizontal drawing exists near a vertical anchor of the span.

    anchor="bottom" checks near bbox bottom (underline).
    anchor="center" checks near bbox vertical center (strikethrough).
    """
    if not drawings:
        return False
    sx0, sy0, sx1, sy1 = span_bbox
    if anchor == "center":
        y_ref = (sy0 + sy1) / 2.0
    else:
        y_ref = sy1
    for dy, dx0, dx1, _ in drawings:
        if abs(dy - y_ref) <= tolerance and dx0 <= sx1 and dx1 >= sx0:
            return True
    return False


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


_MIN_WORDING_SPANS = 5


def classify_wording(blocks: list[Block],
                     page_drawings: dict[int, list]) -> list[str]:
    """Classify spans as ins/del/context using multi-signal analysis.

    Two active signals: HSV color analysis and drawing decoration
    correlation. Sets span.wording_role on matching spans.

    Returns a list of problem descriptions for the prompts file
    (empty if all ins/del classifications are high confidence).
    """
    candidates: list[tuple] = []

    for block in blocks:
        drawings = page_drawings.get(block.page_num, [])

        for line in block.lines:
            for span in line.spans:
                if not span.text.strip():
                    continue

                rgb = _color_int_to_rgb(span.color)
                h, s = _rgb_to_hue_sat(*rgb)

                if not _is_chromatic(s):
                    if span.color != 0:
                        r, g, b = rgb
                        lightness = (r + g + b) / 3.0
                        if 0.25 < lightness < 0.65:
                            candidates.append((span, "context", "high"))
                    continue

                hue_class = _classify_hue(h)

                if hue_class == "blue":
                    continue

                has_underline = _match_drawing(
                    span.bbox, drawings, _UNDERLINE_Y_TOLERANCE, "bottom")
                has_strikethrough = _match_drawing(
                    span.bbox, drawings, _STRIKETHROUGH_Y_TOLERANCE, "center")

                if hue_class == "green" and has_underline:
                    candidates.append((span, "ins", "high"))
                elif hue_class == "red" and has_strikethrough:
                    candidates.append((span, "del", "high"))
                elif hue_class == "green":
                    candidates.append((span, "ins", "medium"))
                elif hue_class == "red":
                    candidates.append((span, "del", "medium"))
                elif has_underline:
                    candidates.append((span, "ins", "low"))
                elif has_strikethrough:
                    candidates.append((span, "del", "low"))

    ins_del = [c for c in candidates if c[1] in ("ins", "del")]
    if len(ins_del) < _MIN_WORDING_SPANS:
        _log.debug("Too few wording candidates (%d < %d), skipping",
                    len(ins_del), _MIN_WORDING_SPANS)
        return []

    for span, role, confidence in candidates:
        span.wording_role = role

    ins_count = sum(1 for _, r, _ in candidates if r == "ins")
    del_count = sum(1 for _, r, _ in candidates if r == "del")
    ctx_count = sum(1 for _, r, _ in candidates if r == "context")
    high = sum(1 for _, r, c in candidates if c == "high" and r in ("ins", "del"))
    medium = sum(1 for _, _, c in candidates if c == "medium")
    low = sum(1 for _, _, c in candidates if c == "low")
    _log.info("Wording detected: %d ins, %d del, %d context "
               "(%d high, %d medium, %d low confidence)",
               ins_count, del_count, ctx_count, high, medium, low)

    problems = []
    if medium > 0 and high == 0:
        problems.append(
            f"Wording detected by color only (no underline/strikethrough "
            f"decoration confirmation). {medium} spans classified at "
            f"MEDIUM confidence. Verify these sections are actual "
            f"proposed wording changes, not incidental colored text.")
    if low > 0:
        problems.append(
            f"{low} spans classified at LOW confidence "
            f"(decoration found but hue not in green/red range). "
            f"These may be emphasis or non-wording decorations.")

    return problems
