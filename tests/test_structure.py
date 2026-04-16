"""Tests for lib.pdf.structure."""

from conftest import make_block, make_section
from lib.pdf.types import (
    Block, Line, Span, Section, SectionKind, Confidence,
)
from lib.pdf.structure import (
    compare_extractions, structure_sections,
    heading_confidence, _extract_metadata,
)


class TestHeadingConfidence:
    def test_number_font_bold(self):
        level, conf = heading_confidence(True, 2, 2, True, False)
        assert level == 2
        assert conf == Confidence.HIGH

    def test_number_font_no_bold(self):
        level, conf = heading_confidence(True, 2, 2, False, False)
        assert level == 2
        assert conf == Confidence.MEDIUM

    def test_number_font_disagree(self):
        level, conf = heading_confidence(True, 2, 3, False, False)
        assert level == 2
        assert conf == Confidence.MEDIUM

    def test_number_bold_no_font(self):
        level, conf = heading_confidence(True, 2, None, True, False)
        assert level == 2
        assert conf == Confidence.MEDIUM

    def test_number_alone(self):
        level, conf = heading_confidence(True, 2, None, False, False)
        assert level == 2
        assert conf == Confidence.LOW

    def test_font_known_bold(self):
        level, conf = heading_confidence(False, 0, 1, True, True)
        assert level == 2
        assert conf == Confidence.HIGH

    def test_font_known_no_bold(self):
        level, conf = heading_confidence(False, 0, 1, False, True)
        assert level == 2
        assert conf == Confidence.MEDIUM

    def test_font_bold(self):
        level, conf = heading_confidence(False, 0, 1, True, False)
        assert level == 2
        assert conf == Confidence.MEDIUM

    def test_font_alone(self):
        level, conf = heading_confidence(False, 0, 1, False, False)
        assert level == 2
        assert conf == Confidence.LOW

    def test_known_alone(self):
        level, conf = heading_confidence(False, 0, None, False, True)
        assert level == 2
        assert conf == Confidence.LOW

    def test_nothing(self):
        level, conf = heading_confidence(False, 0, None, False, False)
        assert level == 0
        assert conf == Confidence.UNCERTAIN


class TestExtractionSimilarity:
    def test_identical_text_confident(self):
        m = [make_block(["alpha beta gamma"], page_num=0)]
        s = [make_block(["alpha beta gamma"], page_num=0)]
        sections = compare_extractions(m, s)
        assert all(sec.kind != SectionKind.UNCERTAIN for sec in sections)

    def test_disjoint_text_uncertain(self):
        m = [make_block(["The quick brown fox jumps over the lazy dog and then some more"], page_num=0)]
        s = [make_block(["Completely unrelated text about different topics entirely and more words"], page_num=0)]
        sections = compare_extractions(m, s)
        assert any(sec.kind == SectionKind.UNCERTAIN for sec in sections)

    def test_high_overlap_confident(self):
        shared = "alpha beta gamma delta epsilon zeta eta theta"
        m = [make_block([shared + " iota"], page_num=0)]
        s = [make_block([shared + " kappa"], page_num=0)]
        sections = compare_extractions(m, s)
        assert all(sec.kind != SectionKind.UNCERTAIN for sec in sections)

    def test_both_empty_no_sections(self):
        sections = compare_extractions([], [])
        assert len(sections) == 0

    def test_one_side_empty_short_demoted(self):
        m = [make_block(["short"], page_num=0)]
        sections = compare_extractions(m, [])
        uncertain = [s for s in sections if s.kind == SectionKind.UNCERTAIN]
        assert len(uncertain) == 0


class TestCompareExtractions:
    def test_identical_blocks_confident(self):
        m = [make_block(["hello world"], page_num=0)]
        s = [make_block(["hello world"], page_num=0)]
        sections = compare_extractions(m, s)
        assert all(sec.kind != SectionKind.UNCERTAIN for sec in sections)

    def test_different_blocks_uncertain(self):
        m = [make_block(["The quick brown fox jumps over the lazy dog and then some more words"], page_num=0)]
        s = [make_block(["Completely unrelated text about different topics entirely with enough words here"], page_num=0)]
        sections = compare_extractions(m, s)
        assert any(sec.kind == SectionKind.UNCERTAIN for sec in sections)

    def test_tiny_uncertain_demoted(self):
        m = [make_block(["short"], page_num=0)]
        s = [make_block(["diff"], page_num=0)]
        sections = compare_extractions(m, s)
        uncertain = [s for s in sections if s.kind == SectionKind.UNCERTAIN]
        assert len(uncertain) == 0


class TestCompareExtractionsOrdering:
    """Regression: promoted pages must not break document order."""

    def test_promoted_pages_preserve_order(self):
        """Sections stay in page_num order even when promotions rewrite the list."""
        shared = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        p0_m = [make_block([shared], page_num=0)]
        p0_s = [make_block([shared], page_num=0)]

        # Page 1: mupdf/spatial have swapped halves so per-page similarity is low
        p1_m = [make_block(["aaa bbb ccc ddd eee fff ggg hhh iii jjj"], page_num=1)]
        p1_s = [make_block(["kkk lll mmm nnn ooo ppp qqq rrr sss ttt"], page_num=1)]

        # Page 2: carries the other half so combined p1+p2 similarity is high
        p2_m = [make_block(["kkk lll mmm nnn ooo ppp qqq rrr sss ttt"], page_num=2)]
        p2_s = [make_block(["aaa bbb ccc ddd eee fff ggg hhh iii jjj"], page_num=2)]

        p3_m = [make_block([shared], page_num=3)]
        p3_s = [make_block([shared], page_num=3)]

        mupdf = p0_m + p1_m + p2_m + p3_m
        spatial = p0_s + p1_s + p2_s + p3_s

        sections = compare_extractions(mupdf, spatial)
        page_nums = [s.page_num for s in sections]
        assert page_nums == sorted(page_nums), (
            f"Sections out of order after promotion: {page_nums}"
        )


class TestParagraphMerging:
    def test_merges_continuation(self):
        sections = [
            make_section("Some text without terminal"),
            make_section("continuation here"),
        ]
        _, result = structure_sections(sections, has_title=True)
        paragraphs = [s for s in result if s.kind == SectionKind.PARAGRAPH]
        assert len(paragraphs) == 1
        assert "continuation" in paragraphs[0].text

    def test_no_merge_with_terminal(self):
        sections = [
            make_section("Some text with terminal."),
            make_section("Next paragraph."),
        ]
        _, result = structure_sections(sections, has_title=True)
        paragraphs = [s for s in result if s.kind == SectionKind.PARAGRAPH]
        assert len(paragraphs) == 2

    def test_merge_preserves_original_input(self):
        s1 = make_section("Some text without terminal")
        s2 = make_section("continuation here")
        original_text = s1.text
        structure_sections([s1, s2], has_title=True)
        assert s1.text == original_text


class TestBodySizeDetection:
    def test_larger_font_detected_as_heading(self):
        sections = [
            make_section("body text", font_size=10.0),
            make_section("more body text", font_size=10.0),
            make_section("A Heading", font_size=14.0),
        ]
        _, result = structure_sections(sections, has_title=True)
        headings = [s for s in result if s.kind == SectionKind.HEADING]
        assert len(headings) >= 1

    def test_uniform_font_no_headings(self):
        sections = [
            make_section("body text", font_size=10.0),
            make_section("more body text", font_size=10.0),
            make_section("still body text", font_size=10.0),
        ]
        _, result = structure_sections(sections, has_title=True)
        headings = [s for s in result if s.kind == SectionKind.HEADING]
        assert len(headings) == 0


class TestExtractMetadataKey:
    def test_document_number_produces_document_key(self):
        """Regression: _extract_metadata must write 'document', not 'doc-number'."""
        sections = [
            make_section("Document Number: P1234R0"),
            make_section("Some body text here."),
        ]
        meta, _ = structure_sections(sections, has_title=True)
        assert "document" in meta or meta == {}
        assert "doc-number" not in meta

    def test_document_key_not_doc_number(self):
        """The merged front matter must never contain the legacy doc-number key."""
        sec = make_section("Document Number: P9999R2")
        meta, _ = structure_sections([sec], has_title=True)
        assert "doc-number" not in meta


class TestExtractMetadataMutation:
    def test_does_not_mutate_input_sections(self):
        """Regression: _extract_metadata must not mutate its input Sections.

        Callers rely on helpers in this module producing new objects,
        consistent with _merge_paragraphs.
        """
        sec = make_section(
            "Document Number: P1234R0\nSome leftover\nBody content",
            kind=SectionKind.PARAGRAPH,
        )
        original_text = sec.text
        _extract_metadata([sec])
        assert sec.text == original_text

    def test_returns_stripped_section_copy(self):
        """The returned section has the metadata lines removed."""
        sec = make_section(
            "Document Number: P1234R0\nSome leftover",
            kind=SectionKind.PARAGRAPH,
        )
        meta, remaining = _extract_metadata([sec])
        assert meta.get("document") == "P1234R0"
        assert len(remaining) == 1
        assert "Document Number" not in remaining[0].text
        assert "Some leftover" in remaining[0].text


class TestBlockFontSize:
    def test_line_count_voting(self):
        """Block.font_size uses line-count voting, not character weighting."""
        from conftest import make_span
        block = Block(lines=[
            Line(spans=[make_span(
                "word word word word word word word word", font_size=11.0)]),
            Line(spans=[make_span("short", font_size=14.0)]),
            Line(spans=[make_span("short", font_size=14.0)]),
        ])
        # Lines: two at 14, one at 11 -> 14 wins by line count.
        # Character count would favor 11.
        assert block.font_size == 14.0
