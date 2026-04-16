"""Tests for lib.pdf.table."""

from conftest import make_span
from lib.pdf.types import Block, Line, Section, SectionKind, Confidence
from lib.pdf.table import detect_tables, exclude_table_regions


def _col_line(text, x_start, y_start, page_num=0):
    """Create a Line positioned at a specific x-start for column layout."""
    span = make_span(text)
    return Line(
        spans=[span],
        bbox=(x_start, y_start, x_start + 100, y_start + 12),
        page_num=page_num,
    )


def _col_block(col_texts, col_xs, y_start, page_num=0):
    """Create a Block with lines at specific x-positions (one per column)."""
    lines = [
        _col_line(text, x, y_start, page_num)
        for text, x in zip(col_texts, col_xs)
    ]
    x0 = col_xs[0]
    x1 = col_xs[-1] + 100
    return Block(
        lines=lines,
        bbox=(x0, y_start, x1, y_start + 12),
        page_num=page_num,
    )


class TestDetectColumnar:
    def test_two_column_block_detected(self):
        """A block with 2 lines whose x-starts differ by >50 is columnar."""
        blocks = [
            _col_block(["Name", "Value"], [50, 300], y_start=100),
            _col_block(["Alpha", "100"], [50, 300], y_start=120),
        ]
        tables, remaining = detect_tables(blocks)
        assert len(tables) == 1
        assert tables[0].kind == SectionKind.TABLE

    def test_non_columnar_not_detected(self):
        """Lines all starting at the same x should not be columnar."""
        blocks = [
            _col_block(["Line one", "Line two"], [50, 60], y_start=100),
            _col_block(["Line three", "Line four"], [50, 60], y_start=120),
        ]
        tables, remaining = detect_tables(blocks)
        assert len(tables) == 0
        assert len(remaining) == 2


class TestDetectTables:
    def test_consecutive_columnar_blocks_form_table(self):
        """Two consecutive columnar blocks with matching columns form a table."""
        xs = [50, 300]
        blocks = [
            _col_block(["Header A", "Header B"], xs, y_start=100),
            _col_block(["Row 1 A", "Row 1 B"], xs, y_start=120),
            _col_block(["Row 2 A", "Row 2 B"], xs, y_start=140),
        ]
        tables, remaining = detect_tables(blocks)
        assert len(tables) == 1
        assert tables[0].confidence == Confidence.HIGH
        assert len(remaining) == 0

    def test_single_columnar_block_no_table(self):
        """A lone columnar block does not form a table (minimum 2 rows)."""
        blocks = [
            _col_block(["Only", "Row"], [50, 300], y_start=100),
        ]
        tables, remaining = detect_tables(blocks)
        assert len(tables) == 0
        assert len(remaining) == 1

    def test_mismatched_columns_separate(self):
        """Columnar blocks with different column counts don't group."""
        blocks = [
            _col_block(["A", "B"], [50, 300], y_start=100),
            _col_block(["C", "D", "E"], [50, 200, 400], y_start=120),
        ]
        tables, remaining = detect_tables(blocks)
        assert len(tables) == 0
        assert len(remaining) == 2

    def test_table_text_pipe_separated(self):
        """Table section text uses pipe-separated columns."""
        xs = [50, 300]
        blocks = [
            _col_block(["Name", "Score"], xs, y_start=100),
            _col_block(["Alice", "95"], xs, y_start=120),
        ]
        tables, _ = detect_tables(blocks)
        assert "Name | Score" in tables[0].text
        assert "Alice | 95" in tables[0].text

    def test_non_columnar_interleaved(self):
        """A non-columnar block between columnar blocks breaks the run."""
        xs = [50, 300]
        plain_line = _col_line("Just a paragraph.", 50, 150)
        plain = Block(lines=[plain_line], bbox=(50, 150, 400, 162), page_num=0)
        blocks = [
            _col_block(["A", "B"], xs, y_start=100),
            plain,
            _col_block(["C", "D"], xs, y_start=200),
        ]
        tables, remaining = detect_tables(blocks)
        assert len(tables) == 0
        assert len(remaining) == 3


class TestExcludeTableRegions:
    def test_blocks_inside_table_removed(self):
        """Blocks whose y-center falls within a table range are excluded."""
        table_line = _col_line("x", 50, 100)
        table_line2 = _col_line("y", 50, 140)
        table_sec = Section(
            kind=SectionKind.TABLE,
            text="table",
            confidence=Confidence.HIGH,
            lines=[table_line, table_line2],
            page_num=0,
        )

        inside = Block(lines=[], bbox=(50, 110, 400, 130), page_num=0)
        outside = Block(lines=[], bbox=(50, 300, 400, 320), page_num=0)

        result = exclude_table_regions([inside, outside], [table_sec])
        assert len(result) == 1
        assert result[0] is outside

    def test_different_page_not_excluded(self):
        """Blocks on a different page from the table are kept."""
        table_line = _col_line("x", 50, 100, page_num=0)
        table_sec = Section(
            kind=SectionKind.TABLE,
            text="table",
            confidence=Confidence.HIGH,
            lines=[table_line],
            page_num=0,
        )

        block = Block(lines=[], bbox=(50, 100, 400, 112), page_num=1)
        result = exclude_table_regions([block], [table_sec])
        assert len(result) == 1

    def test_empty_tables_returns_all(self):
        """No table sections means all blocks are returned."""
        blocks = [
            Block(lines=[], bbox=(50, 100, 400, 112), page_num=0),
            Block(lines=[], bbox=(50, 200, 400, 212), page_num=0),
        ]
        result = exclude_table_regions(blocks, [])
        assert len(result) == 2
