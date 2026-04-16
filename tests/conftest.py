"""Shared test fixtures for tomd."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pdf.types import Span, Line, Block, Section, SectionKind, Confidence


def make_span(text, font_size=10.0, bold=False, italic=False,
              monospace=False, font_name="TestFont", **kwargs):
    return Span(text=text, font_name=font_name, font_size=font_size,
                bold=bold, italic=italic, monospace=monospace, **kwargs)


def make_line(texts, page_num=0, **span_kwargs):
    spans = [make_span(t, **span_kwargs) for t in texts]
    return Line(spans=spans, page_num=page_num)


def make_block(line_texts, page_num=0, **span_kwargs):
    lines = [make_line(t if isinstance(t, list) else [t],
                       page_num=page_num, **span_kwargs)
             for t in line_texts]
    return Block(lines=lines, page_num=page_num)


def make_section(text, kind=SectionKind.PARAGRAPH, page_num=0,
                 font_size=10.0, confidence=Confidence.HIGH,
                 heading_level=0, lines=None, **kwargs):
    if lines is None:
        lines = [make_line([text], font_size=font_size)]
    return Section(kind=kind, text=text, confidence=confidence,
                   heading_level=heading_level, lines=lines,
                   page_num=page_num, font_size=font_size, **kwargs)
