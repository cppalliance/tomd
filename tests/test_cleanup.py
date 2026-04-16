"""Tests for lib.pdf.cleanup."""

from conftest import make_span, make_line, make_block
from lib.pdf.cleanup import normalize_whitespace, cleanup_text
from lib import strip_format_chars
from lib.pdf.types import is_readable, Line, Block


def test_strip_format_chars_zwsp():
    assert strip_format_chars("hello\u200bworld") == "helloworld"


def test_strip_format_chars_zwj():
    assert strip_format_chars("a\u200db") == "ab"


def test_strip_format_chars_lrm():
    assert strip_format_chars("text\u200e") == "text"


def test_strip_format_chars_soft_hyphen():
    assert strip_format_chars("imple\u00admentation") == "implementation"


def test_strip_format_chars_preserves_normal():
    assert strip_format_chars("Hello, World! 123") == "Hello, World! 123"


def test_strip_format_chars_empty():
    assert strip_format_chars("") == ""


def test_normalize_whitespace_nbsp():
    assert "\u00a0" not in normalize_whitespace("hello\u00a0world")


def test_normalize_whitespace_multi_space():
    assert "  " not in normalize_whitespace("hello   world")


def test_normalize_whitespace_trailing():
    result = normalize_whitespace("hello   \n  world  ")
    for line in result.split("\n"):
        assert line == line.rstrip()


def test_is_readable_normal():
    text = "This is a normal paragraph with enough text to pass the check."
    assert is_readable(text * 3)


def test_is_readable_too_short():
    assert not is_readable("short")


def test_is_readable_garbage():
    assert not is_readable("/" * 500)


def test_is_readable_empty():
    assert not is_readable("")


def test_cleanup_dehyphenates_joins():
    span1 = make_span("imple-")
    span2 = make_span("mentation of things")
    block = Block(lines=[Line(spans=[span1]), Line(spans=[span2])])
    result = cleanup_text([block])
    assert "implementation" in result[0].text


def test_cleanup_dehyphenates_single_span_continuation():
    span1 = make_span("imple-")
    span2 = make_span("mentation")
    block = Block(lines=[Line(spans=[span1]), Line(spans=[span2])])
    result = cleanup_text([block])
    full_text = result[0].text
    assert "implementation" in full_text
    assert "mentation" not in full_text.split("implementation")[-1]


def test_cleanup_dehyphenates_skips_compound():
    span1 = make_span("self-")
    span2 = make_span("contained")
    block = Block(lines=[Line(spans=[span1]), Line(spans=[span2])])
    result = cleanup_text([block])
    assert "self-" in result[0].text


def test_cleanup_dehyphenates_no_hyphen():
    span1 = make_span("hello")
    span2 = make_span("world")
    block = Block(lines=[Line(spans=[span1]), Line(spans=[span2])])
    result = cleanup_text([block])
    assert "hello" in result[0].text
    assert "world" in result[0].text


def test_cleanup_dehyphenates_single_span_next_line():
    """Regression: when the next line has one span entirely consumed by
    dehyphenation, the consumed word must not remain as a duplicate."""
    span1 = make_span("imple-")
    span2 = make_span("mentation")
    block = Block(lines=[Line(spans=[span1]), Line(spans=[span2])])
    result = cleanup_text([block])
    full_text = result[0].text
    assert "implementation" in full_text
    assert full_text.count("mentation") == 1, (
        f"'mentation' appears {full_text.count('mentation')} times in {full_text!r}"
    )


def test_cleanup_dehyphenates_next_line_multi_span_consumed():
    """When the next line has multiple spans and the first is fully consumed,
    remaining spans must survive."""
    span1 = make_span("imple-")
    first_consumed = make_span("mentation")
    remaining = make_span(" of things")
    block = Block(lines=[
        Line(spans=[span1]),
        Line(spans=[first_consumed, remaining]),
    ])
    result = cleanup_text([block])
    full_text = result[0].text
    assert "implementation" in full_text
    assert " of things" in full_text
    assert full_text.count("mentation") == 1


def test_cleanup_merges_cross_page():
    b1 = make_block(["Some text without terminal"], page_num=0)
    b2 = make_block(["continuation here"], page_num=1)
    result = cleanup_text([b1, b2])
    assert len(result) == 1
    assert "continuation" in result[0].text


def test_cleanup_no_merge_cross_page_with_terminal():
    b1 = make_block(["Some text with terminal."], page_num=0)
    b2 = make_block(["Next paragraph."], page_num=1)
    result = cleanup_text([b1, b2])
    assert len(result) == 2


def test_cleanup_cross_page_no_mutation():
    b1 = make_block(["Some text without terminal"], page_num=0)
    b2 = make_block(["continuation here"], page_num=1)
    original_text = b1.text
    cleanup_text([b1, b2])
    assert b1.text == original_text


def test_cleanup_text_strips_nbsp():
    block = make_block(["hello\u00a0world"])
    result = cleanup_text([block])
    assert "\u00a0" not in result[0].text


def test_cleanup_text_dehyphenates():
    span1 = make_span("imple-")
    span2 = make_span("mentation of things")
    line1 = make_line.__wrapped__ if hasattr(make_line, '__wrapped__') else None
    from lib.pdf.types import Line, Block
    l1 = Line(spans=[span1])
    l2 = Line(spans=[span2])
    block = Block(lines=[l1, l2])
    result = cleanup_text([block])
    full_text = result[0].text
    assert "implementation" in full_text
