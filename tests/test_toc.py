"""Tests for lib.toc."""

from lib.toc import find_toc_indices
from lib.pdf.types import Span, Line, Block, Section, SectionKind


def test_find_toc_strips_dot_leaders():
    texts = ["Abstract ......... 5", "Introduction", "Motivation"]
    headings = {"abstract", "introduction", "motivation"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices


def test_find_toc_strips_trailing_page_number():
    texts = ["Abstract 42", "Introduction 15", "Motivation 22"]
    headings = {"abstract", "introduction", "motivation"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices


def test_find_toc_strips_section_prefix():
    texts = ["2.1 Introduction", "2.2 Motivation", "2.3 Design"]
    headings = {"introduction", "motivation", "design"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices


def test_find_toc_case_insensitive():
    texts = ["ABSTRACT", "INTRODUCTION", "MOTIVATION"]
    headings = {"abstract", "introduction", "motivation"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices


def test_find_toc_collapses_whitespace():
    texts = ["Some   Entry", "Another   Entry", "Third   Entry"]
    headings = {"some entry", "another entry", "third entry"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices


def test_find_toc_basic_run():
    texts = ["Abstract", "Introduction", "Motivation", "Body text here"]
    headings = {"Abstract", "Introduction", "Motivation"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices
    assert 1 in indices
    assert 2 in indices
    assert 3 not in indices


def test_find_toc_gap_bridging():
    texts = ["Abstract", "non-match", "Introduction", "Motivation"]
    headings = {"Abstract", "Introduction", "Motivation"}
    indices = find_toc_indices(texts, headings)
    assert 1 in indices


def test_find_toc_too_few_matches():
    texts = ["Abstract", "Introduction"]
    headings = {"Abstract", "Introduction"}
    indices = find_toc_indices(texts, headings)
    assert len(indices) == 0


def test_find_toc_duplicate_stops_scan():
    texts = ["Abstract", "Introduction", "Motivation",
             "Abstract"]
    headings = {"Abstract", "Introduction", "Motivation"}
    indices = find_toc_indices(texts, headings)
    assert 3 not in indices


def test_find_toc_label_included():
    texts = ["Table of Contents", "Abstract", "Introduction", "Motivation"]
    headings = {"Abstract", "Introduction", "Motivation"}
    indices = find_toc_indices(texts, headings)
    assert 0 in indices


def test_find_toc_empty_inputs():
    assert find_toc_indices([], set()) == set()
    assert find_toc_indices(["x"], set()) == set()
    assert find_toc_indices([], {"x"}) == set()


# ---------------------------------------------------------------------------
# Structural hints fallback (headingless wording papers)
# ---------------------------------------------------------------------------

def _make_toc_section(title: str, page: str, x: float = 400.0) -> "Section":
    """Build a Section whose text has a bare page number on the second line."""
    page_span = Span(text=page, bbox=(x, 0, x + 20, 10))
    page_line = Line(spans=[page_span])
    title_span = Span(text=title)
    title_line = Line(spans=[title_span])
    return Section(
        kind=SectionKind.WORDING_ADD,
        text=f"{title}\n{page}",
        lines=[title_line, page_line],
    )


def _hints(sections) -> "list[bool]":
    from lib.pdf.__init__ import _toc_structural_hints
    return _toc_structural_hints(sections)


class TestStructuralTocHints:
    def test_basic_run_detected(self):
        secs = [
            _make_toc_section("Introduction", "5"),
            _make_toc_section("Motivation", "8"),
            _make_toc_section("Design", "12"),
        ]
        hints = _hints(secs)
        indices = find_toc_indices(
            [s.text for s in secs], set(), hints)
        assert {0, 1, 2} == indices

    def test_too_few_entries_not_detected(self):
        secs = [_make_toc_section("A", "1"), _make_toc_section("B", "2")]
        hints = _hints(secs)
        indices = find_toc_indices([s.text for s in secs], set(), hints)
        assert len(indices) == 0

    def test_non_toc_section_excluded(self):
        body = Section(kind=SectionKind.PARAGRAPH,
                       text="This is body text with no page number.")
        secs = [
            _make_toc_section("Introduction", "5"),
            _make_toc_section("Motivation", "8"),
            _make_toc_section("Design", "12"),
            body,
        ]
        hints = _hints(secs)
        indices = find_toc_indices([s.text for s in secs], set(), hints)
        assert 3 not in indices

    def test_headings_present_ignores_structural_hints(self):
        """When headings are non-empty the structural fallback is not used."""
        secs = [_make_toc_section("X", "1"), _make_toc_section("Y", "2")]
        # Normally 2 entries would not form a TOC via structural hints.
        # With headings supplied they should also not form a TOC (too few).
        hints = _hints(secs)
        indices = find_toc_indices(
            [s.text for s in secs], {"X", "Y"}, hints)
        assert len(indices) == 0

    def test_outlier_x_position_excluded_from_hints(self):
        """A candidate whose x differs from the cluster is not marked as a hint."""
        from lib.pdf.__init__ import _toc_structural_hints, _TOC_X_TOLERANCE
        normal_x = 400.0
        outlier_x = normal_x + _TOC_X_TOLERANCE + 20.0
        secs = [
            _make_toc_section("A", "1", x=normal_x),
            _make_toc_section("B", "2", x=normal_x),
            _make_toc_section("C", "3", x=outlier_x),
        ]
        hints = _toc_structural_hints(secs)
        assert hints[0] is True
        assert hints[1] is True
        assert hints[2] is False


def test_exact_match_skips_fuzzy_on_large_heading_set():
    """When headings exceed _MAX_FUZZY_HEADINGS, only exact matches are used."""
    headings = {f"Section {i}" for i in range(300)}
    texts = ["Section 0", "Section 1", "Section 2", "Section 3",
             "Body paragraph", "Section 5"]
    result = find_toc_indices(texts, headings)
    assert 0 in result
    assert 1 in result
    assert 2 in result
    assert 3 in result


def test_large_toc_completes_quickly():
    """Performance guard: 1000 sections x 500 headings must finish in < 2s."""
    import time
    headings = {f"Heading {i}" for i in range(500)}
    texts = [f"Heading {i % 500}" for i in range(1000)]
    t0 = time.monotonic()
    find_toc_indices(texts, headings)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"TOC detection took {elapsed:.1f}s, expected < 2s"
