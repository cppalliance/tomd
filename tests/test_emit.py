"""Tests for lib.pdf.emit."""

from conftest import make_section, make_line, make_span
from lib.pdf.types import SectionKind, Confidence, Span, Line
from lib.pdf.emit import emit_markdown, emit_prompts, _render_wording_line


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


def _ins(text: str) -> Span:
    s = Span(text=text)
    s.wording_role = "ins"
    return s


def _del(text: str) -> Span:
    s = Span(text=text)
    s.wording_role = "del"
    return s


def _plain(text: str) -> Span:
    return Span(text=text)


class TestRenderWordingLine:
    def _line(self, *spans: Span) -> Line:
        return Line(spans=list(spans))

    def test_single_ins(self):
        result = _render_wording_line(self._line(_ins("added")))
        assert result == "<ins>added</ins>"

    def test_single_del(self):
        result = _render_wording_line(self._line(_del("removed")))
        assert result == "<del>removed</del>"

    def test_adjacent_ins_merged(self):
        result = _render_wording_line(self._line(_ins("A"), _ins("B")))
        assert result == "<ins>AB</ins>"

    def test_adjacent_del_merged(self):
        result = _render_wording_line(self._line(_del("X"), _del("Y")))
        assert result == "<del>XY</del>"

    def test_whitespace_between_same_role_absorbed(self):
        result = _render_wording_line(self._line(_ins("A"), _plain(" "), _ins("B")))
        assert result == "<ins>A B</ins>"

    def test_whitespace_between_different_roles_emitted(self):
        result = _render_wording_line(self._line(_ins("A"), _plain(" "), _del("B")))
        assert result == "<ins>A</ins> <del>B</del>"

    def test_ins_then_del_not_merged(self):
        result = _render_wording_line(self._line(_ins("add"), _del("remove")))
        assert result == "<ins>add</ins><del>remove</del>"

    def test_context_between_ins_not_merged(self):
        ctx = Span(text=" context ")
        ctx.wording_role = "context"
        result = _render_wording_line(self._line(_ins("A"), ctx, _ins("B")))
        assert result == "<ins>A</ins> context <ins>B</ins>"

    def test_many_fragmented_ins_merged(self):
        """Reproduces the p3596r0 fragment: 8 separate ins → one block."""
        spans = [
            _ins("1"), _plain(" "), _ins("Specified in:"),
            _ins(" [lifetime.outside.pointer.delete]"), _plain(" "),
            _ins("For a pointer"), _plain(" "), _ins("pointing to an object."),
        ]
        result = _render_wording_line(self._line(*spans))
        assert result.count("<ins>") == 1
        assert "1 Specified in:" in result
        assert "pointing to an object." in result

    def test_leading_whitespace_preserved(self):
        result = _render_wording_line(self._line(_plain("  "), _ins("code")))
        assert result == "  <ins>code</ins>"

    def test_empty_line(self):
        assert _render_wording_line(Line(spans=[])) == ""
