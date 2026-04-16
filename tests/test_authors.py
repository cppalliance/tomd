"""Tests for lib.parse_author_lines.

The shared state machine that both `lib/pdf/wg21.py:_parse_authors` and
`lib/html/extract.py:_parse_mpark_authors` delegate to. These tests pin
the helper's own contract: pending-name pairing, multi-line email pairs,
blank-line skipping, trailing-name flush, and the clean_line / skip_line
injection points the callers depend on.
"""

from lib import parse_author_lines


def test_name_and_email_same_line():
    result = parse_author_lines(["Alice Example alice@example.com"])
    assert result == ["Alice Example <alice@example.com>"]


def test_name_then_email_next_line():
    result = parse_author_lines(["Alice Example", "alice@example.com"])
    assert result == ["Alice Example <alice@example.com>"]


def test_email_alone():
    result = parse_author_lines(["alice@example.com"])
    assert result == ["<alice@example.com>"]


def test_multiple_authors_alternating():
    result = parse_author_lines([
        "Alice Example",
        "alice@example.com",
        "Bob Sample",
        "bob@example.com",
    ])
    assert result == [
        "Alice Example <alice@example.com>",
        "Bob Sample <bob@example.com>",
    ]


def test_name_only_no_email_becomes_bare_entry():
    result = parse_author_lines(["Alice Example"])
    assert result == ["Alice Example"]


def test_blank_lines_are_skipped():
    result = parse_author_lines(
        ["", "Alice Example", "  ", "alice@example.com", ""])
    assert result == ["Alice Example <alice@example.com>"]


def test_trailing_pending_name_is_flushed():
    # A name with no following email must still appear in the output.
    result = parse_author_lines([
        "Alice Example", "alice@example.com", "Bob Solo",
    ])
    assert result == [
        "Alice Example <alice@example.com>",
        "Bob Solo",
    ]


def test_empty_input():
    assert parse_author_lines([]) == []


def test_custom_clean_line_strips_brackets():
    # Mirrors how lib/html/extract.py injects angle-bracket stripping.
    import re
    angle = re.compile(r"[<>]")
    result = parse_author_lines(
        ["Alice <Example>", "<alice@example.com>"],
        clean_line=lambda t: angle.sub("", t).strip(),
    )
    assert result == ["Alice Example <alice@example.com>"]


def test_custom_skip_line_rejects_non_author_content():
    # Mirrors how HTML rejects doc-number lines and PDF rejects label lines:
    # the skipped line must neither become a pending name nor appear in output.
    result = parse_author_lines(
        ["P1234R0", "Alice Example", "alice@example.com"],
        skip_line=lambda l: l == "P1234R0",
    )
    assert result == ["Alice Example <alice@example.com>"]
