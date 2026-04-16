"""Tests for lib.pdf.wording."""

from unittest.mock import MagicMock
from conftest import make_span, make_line, make_block
from lib.pdf.wording import classify_wording, collect_line_drawings


def _color_to_int(r, g, b):
    """Convert 0-255 RGB to MuPDF integer color."""
    return (r << 16) | (g << 8) | b


class TestDrawingMatch:
    def test_underline_boosts_confidence(self):
        green = _color_to_int(0, 133, 71)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"added {i}", color=green,
                       bbox=(100, 50, 200, 60)) for i in range(6)]
        lines = [Line(spans=[s]) for s in spans]
        block = Block(lines=lines, page_num=0)
        drawings = {0: [(60.5, 100, 200, (0, 0.5, 0))]}
        problems = classify_wording([block], drawings)
        assert len(problems) == 0

    def test_underline_too_far_no_boost(self):
        green = _color_to_int(0, 133, 71)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"added {i}", color=green,
                       bbox=(100, 50, 200, 60)) for i in range(6)]
        lines = [Line(spans=[s]) for s in spans]
        block = Block(lines=lines, page_num=0)
        drawings = {0: [(65, 100, 200, (0, 0.5, 0))]}
        problems = classify_wording([block], drawings)
        assert len(problems) > 0

    def test_strikethrough_boosts_confidence(self):
        red = _color_to_int(204, 0, 0)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"removed {i}", color=red,
                       bbox=(100, 50, 200, 60)) for i in range(6)]
        lines = [Line(spans=[s]) for s in spans]
        block = Block(lines=lines, page_num=0)
        drawings = {0: [(55, 100, 200, (0.8, 0, 0))]}
        problems = classify_wording([block], drawings)
        assert len(problems) == 0

    def test_strikethrough_too_far_no_boost(self):
        red = _color_to_int(204, 0, 0)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"removed {i}", color=red,
                       bbox=(100, 50, 200, 60)) for i in range(6)]
        lines = [Line(spans=[s]) for s in spans]
        block = Block(lines=lines, page_num=0)
        drawings = {0: [(48, 100, 200, (0.8, 0, 0))]}
        problems = classify_wording([block], drawings)
        assert len(problems) > 0

    def test_no_drawings_medium_confidence(self):
        green = _color_to_int(0, 133, 71)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"added {i}", color=green,
                       bbox=(100, 50, 200, 60)) for i in range(6)]
        lines = [Line(spans=[s]) for s in spans]
        block = Block(lines=lines, page_num=0)
        problems = classify_wording([block], {})
        assert len(problems) > 0


class TestClassifyWording:
    def test_green_span_classified_as_ins(self):
        green = _color_to_int(0, 133, 71)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"added {i}", color=green,
                       bbox=(10, 50, 200, 60)) for i in range(6)]
        lines = [Line(spans=[s]) for s in spans]
        block = Block(lines=lines, page_num=0)
        drawings = {0: [(60.5, 0, 300, (0, 0.5, 0.3))]}
        problems = classify_wording([block], drawings)
        assert block.lines[0].spans[0].wording_role == "ins"

    def test_red_span_classified_as_del(self):
        red = _color_to_int(204, 0, 0)
        block = make_block(["removed text"] * 5, page_num=0)
        for ln in block.lines:
            ln.spans[0].color = red
        problems = classify_wording([block], {})
        assert block.lines[0].spans[0].wording_role == "del"

    def test_below_threshold_no_classification(self):
        green = _color_to_int(0, 133, 71)
        block = make_block(["tiny"], page_num=0)
        block.lines[0].spans[0].color = green
        problems = classify_wording([block], {})
        assert block.lines[0].spans[0].wording_role is None

    def test_black_span_not_classified(self):
        block = make_block(["normal text"] * 10, page_num=0)
        problems = classify_wording([block], {})
        assert all(s.wording_role is None
                   for ln in block.lines for s in ln.spans)

    def test_blue_span_not_classified(self):
        blue = _color_to_int(5, 85, 193)
        block = make_block(["link text"] * 10, page_num=0)
        for ln in block.lines:
            ln.spans[0].color = blue
        problems = classify_wording([block], {})
        assert all(s.wording_role is None
                   for ln in block.lines for s in ln.spans)

    def test_medium_confidence_generates_problem(self):
        green = _color_to_int(0, 133, 71)
        blocks = [make_block(["added"] * 10, page_num=0)]
        for ln in blocks[0].lines:
            ln.spans[0].color = green
        problems = classify_wording(blocks, {})
        assert any("MEDIUM" in p or "medium" in p.lower() for p in problems)

class TestCollectLineDrawings:
    def _make_page(self, drawings):
        page = MagicMock()
        page.get_drawings.return_value = drawings
        return page

    def _make_drawing(self, x0, y0, x1, y1, color=(0.0, 0.5, 0.0)):
        """Build a minimal drawing dict with a single 'l' (line) item."""
        p1 = MagicMock()
        p1.x, p1.y = x0, y0
        p2 = MagicMock()
        p2.x, p2.y = x1, y1
        return {"items": [("l", p1, p2)], "color": color}

    def test_horizontal_line_collected(self):
        drawing = self._make_drawing(10, 50, 200, 50)
        page = self._make_page([drawing])
        result = collect_line_drawings(page)
        assert len(result) == 1
        y, x0, x1, color = result[0]
        assert abs(y - 50) < 0.1
        assert x0 == 10
        assert x1 == 200

    def test_short_line_filtered_out(self):
        """Lines <= 5 px wide are discarded."""
        drawing = self._make_drawing(10, 50, 14, 50)
        page = self._make_page([drawing])
        assert collect_line_drawings(page) == []

    def test_diagonal_line_filtered_out(self):
        """Lines with |dy| >= 1 are not horizontal and are discarded."""
        drawing = self._make_drawing(10, 50, 200, 52)
        page = self._make_page([drawing])
        assert collect_line_drawings(page) == []

    def test_get_drawings_exception_returns_empty(self):
        """If get_drawings() raises, degrade gracefully and return []."""
        page = MagicMock()
        page.get_drawings.side_effect = RuntimeError("MuPDF internal error")
        assert collect_line_drawings(page) == []

    def test_no_color_drawing_skipped(self):
        """Drawings without a color tuple are skipped."""
        p1 = MagicMock()
        p1.x, p1.y = 10, 50
        p2 = MagicMock()
        p2.x, p2.y = 200, 50
        drawing = {"items": [("l", p1, p2)], "color": None}
        page = self._make_page([drawing])
        assert collect_line_drawings(page) == []


class TestHighConfidenceWording:
    def test_high_confidence_no_problem(self):
        green = _color_to_int(0, 133, 71)
        from lib.pdf.types import Span, Line, Block
        spans = [Span(text=f"added {i}", color=green,
                       bbox=(10, 50, 200, 60)) for i in range(10)]
        lines = [Line(spans=[s]) for s in spans]
        blocks = [Block(lines=lines, page_num=0)]
        drawings = {0: [(60.5, 0, 500, (0, 0.5, 0.3))]}
        problems = classify_wording(blocks, drawings)
        assert len(problems) == 0
