"""Tests for lib.pdf.qa (Markdown-based QA scoring)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pdf.qa import compute_metrics


_GOOD_MD = """\
---
title: "Test Paper"
document: P1234R0
date: 2025-01-01
audience: LEWG
reply-to:
  - "Author Name <author@example.com>"
---

## 1 Introduction

Some introductory text about the paper.

## 2 Motivation

More text explaining motivation.

```cpp
void foo() {
    return;
}
```

- item one
- item two
- item three

## 3 Conclusion

Final paragraph.
"""


class TestPerfectScore:
    def test_good_markdown_scores_100(self):
        m = compute_metrics(_GOOD_MD, file="test.pdf")
        assert m.score == 100, f"expected 100, got {m.score}: {m.issues}"

    def test_heading_count(self):
        m = compute_metrics(_GOOD_MD)
        assert m.heading_count == 3

    def test_code_block_count(self):
        m = compute_metrics(_GOOD_MD)
        assert m.code_block_count == 1

    def test_front_matter_count(self):
        m = compute_metrics(_GOOD_MD)
        assert m.front_matter_count == 5


class TestEmptyOutput:
    def test_empty_string_scores_zero(self):
        m = compute_metrics("")
        assert m.score == 0
        assert "empty output" in m.issues

    def test_whitespace_only_scores_zero(self):
        m = compute_metrics("   \n\n  ")
        assert m.score == 0


class TestUncertainRegions:
    def test_uncertain_markers_penalized(self):
        md = "## Heading\n\n<!-- tomd:uncertain:L5-L10 -->\n\nSome text.\n"
        m = compute_metrics(md)
        assert m.uncertain_count == 1
        assert m.score < 100

    def test_many_uncertain_regions(self):
        markers = "\n".join(
            f"<!-- tomd:uncertain:L{i}-L{i+5} -->\ntext\n"
            for i in range(10)
        )
        md = f"## Heading\n\n{markers}\n"
        m = compute_metrics(md)
        assert m.uncertain_count == 10
        assert m.score < 60


class TestNoHeadings:
    def test_no_headings_long_doc_penalized(self):
        """A document with 10+ paragraphs and zero headings is penalized."""
        paras = "\n\n".join(f"Paragraph number {i} with some content." for i in range(15))
        m = compute_metrics(paras)
        assert m.heading_count == 0
        assert m.score < 80
        assert any("no headings" in i for i in m.issues)

    def test_no_headings_short_doc_ok(self):
        """A short document (few paragraphs) with no headings is fine."""
        md = "Just a paragraph.\n\nAnother one.\n"
        m = compute_metrics(md)
        assert not any("no headings" in i for i in m.issues)


class TestUnfencedCode:
    def test_cpp_in_paragraphs_penalized(self):
        lines = [
            "## Heading\n",
            "template<class T> void foo();",
            "#include <vector>",
            "auto x = std::move(y);",
            "int main() {",
            "  return 0;",
            "}",
            "void bar();",
        ]
        md = "\n\n".join(lines) + "\n"
        m = compute_metrics(md)
        assert m.unfenced_code_lines > 5
        assert m.score < 100

    def test_inline_code_not_penalized(self):
        md = "## Heading\n\nUse `std::vector` and `nullptr` in your code.\n"
        m = compute_metrics(md)
        assert m.unfenced_code_lines == 0


class TestMetadata:
    def test_no_front_matter_long_doc_penalized(self):
        """Zero front matter on a long document is penalized."""
        paras = "\n\n".join(f"Paragraph {i} about something." for i in range(15))
        md = f"## Heading\n\n{paras}\n"
        m = compute_metrics(md)
        assert m.front_matter_count == 0
        assert any("no front matter" in i for i in m.issues)

    def test_no_front_matter_short_doc_ok(self):
        """Zero front matter on a short document is fine."""
        md = "## Heading\n\nSome text here.\n"
        m = compute_metrics(md)
        assert m.front_matter_count == 0
        assert not any("front matter" in i for i in m.issues)

    def test_partial_front_matter_ok(self):
        """Having any front matter fields is acceptable."""
        md = "---\ntitle: Test\n---\n\n## H\n\nText.\n"
        m = compute_metrics(md)
        assert m.front_matter_count >= 1
        assert not any("front matter" in i for i in m.issues)


class TestLowVariety:
    def test_long_doc_only_paragraphs_penalized(self):
        """10+ paragraphs with no headings/code/lists/tables is penalized."""
        paras = "\n\n".join(f"Paragraph {i}." for i in range(15))
        m = compute_metrics(paras)
        assert any("low variety" in i for i in m.issues)

    def test_short_doc_only_paragraphs_ok(self):
        """A short doc with only paragraphs is not penalized for variety."""
        md = "One.\n\nTwo.\n\nThree.\n"
        m = compute_metrics(md)
        assert not any("low variety" in i for i in m.issues)


class TestWordingExemption:
    def test_ins_del_paragraphs_not_counted_as_unfenced(self):
        """Paragraphs with <ins>/<del> tags should not trigger unfenced code."""
        md = (
            "## Wording\n\n"
            "<ins>constexpr void* memcpy(void* s1, const void* s2, size_t n);</ins>\n\n"
            "<ins>constexpr void* memmove(void* s1, const void* s2, size_t n);</ins>\n\n"
            "<del>void* memcpy(void* s1, const void* s2, size_t n);</del>\n\n"
            "<ins>constexpr int strcmp(const char* s1, const char* s2);</ins>\n\n"
            "<ins>constexpr size_t strlen(const char* s);</ins>\n\n"
            "<ins>constexpr void* memset(void* s, int c, size_t n);</ins>\n\n"
            "Some normal text.\n"
        )
        m = compute_metrics(md)
        assert m.unfenced_code_lines == 0

    def test_plain_code_still_counted(self):
        """Paragraphs without wording markup that look like code are counted."""
        md = (
            "## Section\n\n"
            "void foo(int x);\n\n"
            "int bar() {\n\n"
            "return 0;\n\n"
            "}\n\n"
            "#include <vector>\n\n"
            "void baz();\n\n"
            "int qux();\n"
        )
        m = compute_metrics(md)
        assert m.unfenced_code_lines > 5


class TestTableDetection:
    def test_pipe_tables_counted(self):
        md = "## Heading\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nText.\n"
        m = compute_metrics(md)
        assert m.table_count == 1

    def test_no_tables(self):
        md = "## Heading\n\nJust text.\n"
        m = compute_metrics(md)
        assert m.table_count == 0
