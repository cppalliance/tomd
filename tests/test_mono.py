"""Tests for lib.pdf.mono."""

from conftest import make_span, make_line, make_block
from lib.pdf.mono import classify_monospace, propagate_monospace


def test_keyword_courier():
    assert classify_monospace("Courier")


def test_keyword_menlo():
    assert classify_monospace("Menlo-Regular")


def test_keyword_consolas():
    assert classify_monospace("Consolas")


def test_keyword_source_code_pro():
    assert classify_monospace("SourceCodePro")


def test_no_keyword_no_data():
    assert not classify_monospace("Arial")


def test_no_keyword_no_data_unnamed():
    assert not classify_monospace("Unnamed-T3")


def test_uniform_widths_and_spacings():
    widths = [10.0] * 10
    origins = [float(i * 10) for i in range(10)]
    assert classify_monospace("UnknownFont", widths, origins)


def test_non_uniform_widths():
    widths = [5.0, 15.0, 5.0, 15.0, 5.0]
    origins = [0.0, 5.0, 20.0, 25.0, 40.0]
    assert not classify_monospace("UnknownFont", widths, origins)


def test_proportional_advance_ratio_rejects():
    """Proportional font: M advances much further than i -> reject."""
    chars = ["M", "i", "M", "i"]
    origins = [0.0, 15.0, 20.0, 35.0]  # M=15 units, i=5 units
    widths = [14.0, 3.0, 14.0, 3.0]
    assert not classify_monospace("UnknownFont", widths, origins, chars=chars)


def test_monospace_advance_ratio_accepts():
    """Monospace font: all chars advance equally regardless of glyph body width."""
    chars = ["M", "i", "M", "i"]
    origins = [0.0, 10.0, 20.0, 30.0]  # All advance 10 units
    widths = [14.0, 3.0, 14.0, 3.0]    # Bbox widths vary but that's fine
    assert classify_monospace("UnknownFont", widths, origins, chars=chars)


def test_fat_thin_not_checked_without_origins():
    """Fat/thin check is bypassed when x-origins are absent; font name decides."""
    widths = [14.0, 3.0, 14.0, 3.0]  # M wide, i narrow (proportional-looking bboxes)
    chars = ["M", "i", "M", "i"]
    # No x_origins -> fat/thin skipped; Courier font name accepted via signal 1
    assert classify_monospace("Courier", widths, None, chars=chars)
    # Without a monospace name and without origins, signals 1 and 3 are both False
    assert not classify_monospace("Arial", widths, None, chars=chars)


def test_propagate_sets_monospace():
    m_block = make_block(["hello world"], page_num=0)
    m_block.lines[0].spans[0].font_name = "Menlo-Regular"
    m_block.lines[0].spans[0].monospace = False

    s_block = make_block(["hello world"], page_num=0)
    s_block.lines[0].spans[0].font_name = "Menlo-Regular"
    s_block.lines[0].spans[0].monospace = True

    propagate_monospace([m_block], [s_block], "arial")
    assert m_block.lines[0].spans[0].monospace is True


def test_propagate_excludes_dominant_proportional():
    """Dominant font is discarded if its name is not a monospace family."""
    m_block = make_block(["hello world"], page_num=0)
    m_block.lines[0].spans[0].font_name = "Arial"
    m_block.lines[0].spans[0].monospace = False

    s_block = make_block(["hello world"], page_num=0)
    s_block.lines[0].spans[0].font_name = "Arial"
    s_block.lines[0].spans[0].monospace = True  # spatial path false-positive

    propagate_monospace([m_block], [s_block], "arial")
    assert m_block.lines[0].spans[0].monospace is False


def test_propagate_keeps_dominant_monospace():
    """Dominant monospace font is NOT discarded - code-heavy papers need this."""
    m_block = make_block(["code code code"], page_num=0)
    m_block.lines[0].spans[0].font_name = "Courier"
    m_block.lines[0].spans[0].monospace = False

    s_block = make_block(["code code code"], page_num=0)
    s_block.lines[0].spans[0].font_name = "Courier"
    s_block.lines[0].spans[0].monospace = True

    propagate_monospace([m_block], [s_block], "courier")
    assert m_block.lines[0].spans[0].monospace is True
