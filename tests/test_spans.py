"""Tests for lib.pdf.spans."""

from lib.pdf.types import Span, Line, Block
from lib.pdf.spans import normalize_spans


def _make_span(text, bold=False, italic=False, monospace=False):
    return Span(text=text, bold=bold, italic=italic, monospace=monospace)


def test_normalize_snaps_bold_boundary():
    spans = [
        _make_span("hello wor", bold=True),
        _make_span("ld here", bold=False),
    ]
    line = Line(spans=spans)
    block = Block(lines=[line])
    result = normalize_spans([block])
    texts = [s.text for s in result[0].lines[0].spans]
    joined = "".join(texts)
    assert joined == "hello world here"
    assert "wor" not in texts[0] or "ld" not in texts[0]


def test_normalize_monospace_exempt():
    spans = [
        _make_span("std::vec", monospace=True),
        _make_span("tor", monospace=False),
    ]
    line = Line(spans=spans)
    block = Block(lines=[line])
    result = normalize_spans([block])
    assert result[0].lines[0].spans[0].text == "std::vec"


def test_normalize_no_touch_no_change():
    spans = [
        _make_span("hello ", bold=True),
        _make_span("world", bold=False),
    ]
    line = Line(spans=spans)
    block = Block(lines=[line])
    result = normalize_spans([block])
    assert result[0].lines[0].spans[0].text == "hello "
    assert result[0].lines[0].spans[1].text == "world"


def test_normalize_empty_spans():
    line = Line(spans=[])
    block = Block(lines=[line])
    result = normalize_spans([block])
    assert len(result[0].lines[0].spans) == 0


def test_normalize_single_span():
    spans = [_make_span("hello")]
    line = Line(spans=spans)
    block = Block(lines=[line])
    result = normalize_spans([block])
    assert result[0].lines[0].spans[0].text == "hello"
