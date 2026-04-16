"""Tests for lib.toc."""

from lib.toc import find_toc_indices


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
