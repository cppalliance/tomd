"""Tests for lib.pdf.emit."""

from conftest import make_section, make_line, make_span
from lib.pdf.types import SectionKind, Confidence
from lib.pdf.emit import emit_markdown, emit_prompts


def test_emit_heading():
    sec = make_section("Introduction", kind=SectionKind.HEADING,
                       heading_level=2)
    md = emit_markdown({}, [sec])
    assert "## Introduction" in md


def test_emit_paragraph_unwrapped():
    sec = make_section("Hello world")
    md = emit_markdown({}, [sec])
    assert "Hello world" in md


def test_emit_code_fenced():
    sec = make_section("int main() {}", kind=SectionKind.CODE,
                       fence_lang="cpp")
    sec.lines[0].spans[0].monospace = True
    md = emit_markdown({}, [sec])
    assert "```cpp" in md
    assert "int main()" in md


def test_emit_uncertain_has_comment():
    sec = make_section("uncertain text", kind=SectionKind.UNCERTAIN,
                       confidence=Confidence.UNCERTAIN)
    sec.mupdf_text = "uncertain text"
    sec.spatial_text = "different text"
    md = emit_markdown({}, [sec])
    assert "<!-- tomd:uncertain:" in md


def test_emit_prompts_none_when_no_uncertain():
    sec = make_section("hello")
    assert emit_prompts([sec]) is None


def test_emit_prompts_has_content():
    sec = make_section("uncertain", kind=SectionKind.UNCERTAIN,
                       confidence=Confidence.UNCERTAIN)
    sec.mupdf_text = "mupdf version"
    sec.spatial_text = "spatial version"
    result = emit_prompts([sec])
    assert result is not None
    assert "MuPDF extraction" in result
    assert "Spatial extraction" in result


def test_front_matter_title_quoted():
    md = emit_markdown({"title": "My Paper: A Study"}, [])
    assert 'title: "My Paper: A Study"' in md


def test_front_matter_reply_to_list():
    meta = {"reply-to": ["Alice <a@b.com>", "Bob <c@d.com>"]}
    md = emit_markdown(meta, [])
    assert "reply-to:" in md
    assert '"Alice <a@b.com>"' in md
    assert '"Bob <c@d.com>"' in md


def test_front_matter_special_chars_quoted():
    from lib import format_front_matter
    result = format_front_matter({"document": "P1234R0", "audience": "SG1: Concurrency"})
    assert '"SG1: Concurrency"' in result


def test_emit_list():
    from lib.pdf.types import Span, Line
    span = make_span("- item one")
    line = make_line(["- item one"])
    sec = make_section("- item one", kind=SectionKind.LIST)
    md = emit_markdown({}, [sec])
    assert "- item one" in md


def test_emit_table():
    from lib.pdf.types import Span, Line, Section
    sec = Section(
        kind=SectionKind.TABLE,
        text="",
        columns=[
            [[make_span("Header A")], [make_span("Header B")]],
            [[make_span("Cell 1")], [make_span("Cell 2")]],
        ],
    )
    md = emit_markdown({}, [sec])
    assert "Header A" in md
    assert "Header B" in md
    assert "---" in md
    assert "Cell 1" in md


def test_emit_wording_section():
    from lib.pdf.types import Span, Line, Section
    span = make_span("added text")
    span.wording_role = "ins"
    line = make_line(["added text"])
    line.spans[0].wording_role = "ins"
    sec = Section(
        kind=SectionKind.WORDING_ADD,
        text="added text",
        lines=[line],
    )
    md = emit_markdown({}, [sec])
    assert ":::wording-add" in md
    assert ":::" in md


def test_emit_wording_remove_section():
    from lib.pdf.types import Section
    line = make_line(["removed text"])
    line.spans[0].wording_role = "del"
    sec = Section(
        kind=SectionKind.WORDING_REMOVE,
        text="removed text",
        lines=[line],
    )
    md = emit_markdown({}, [sec])
    assert ":::wording-remove" in md
