"""Tests for lib.html.render."""

from lib.html.extract import parse_html
from lib.html.render import render_body


class TestHeading:
    def test_atx_level(self):
        soup = parse_html("<h2>Introduction</h2>")
        md = render_body(soup, "mpark")
        assert "## Introduction" in md

    def test_strips_section_number_span(self):
        soup = parse_html(
            '<h1><span class="header-section-number">1</span> Abstract</h1>')
        md = render_body(soup, "mpark")
        assert "# Abstract" in md
        assert "1 " not in md.split("Abstract")[0]

    def test_strips_leading_dotted_number(self):
        soup = parse_html("<h3>2.1.3 Details</h3>")
        md = render_body(soup, "mpark")
        assert "### Details" in md

    def test_bold_suppressed(self):
        soup = parse_html("<h2><strong>Bold Heading</strong></h2>")
        md = render_body(soup, "mpark")
        assert "## Bold Heading" in md
        assert "**" not in md


class TestParagraph:
    def test_collapses_whitespace(self):
        soup = parse_html("<p>Hello   \n  world</p>")
        md = render_body(soup, "mpark")
        assert "Hello world" in md

    def test_inline_code(self):
        soup = parse_html("<p>Use <code>std::vector</code> here.</p>")
        md = render_body(soup, "mpark")
        assert "`std::vector`" in md


class TestCodeBlock:
    def test_fenced(self):
        soup = parse_html('<pre class="sourceCode cpp"><code>int x = 1;</code></pre>')
        md = render_body(soup, "mpark")
        assert "```cpp" in md
        assert "int x = 1;" in md

    def test_language_from_class(self):
        soup = parse_html(
            '<div class="sourceCode"><pre class="sourceCode python">'
            '<code class="sourceCode python">print("hi")</code></pre></div>')
        md = render_body(soup, "mpark")
        assert "```python" in md

    def test_default_cpp_for_mpark(self):
        soup = parse_html("<pre><code>void f();</code></pre>")
        md = render_body(soup, "mpark")
        assert "```cpp" in md

    def test_no_default_for_unknown(self):
        soup = parse_html("<pre><code>void f();</code></pre>")
        md = render_body(soup, "unknown")
        assert "```\n" in md


class TestTable:
    def test_pipe_table(self):
        soup = parse_html("""
        <table>
          <tr><th>A</th><th>B</th></tr>
          <tr><td>1</td><td>2</td></tr>
        </table>
        """)
        md = render_body(soup, "mpark")
        assert "| A | B |" in md
        assert "| --- | --- |" in md
        assert "| 1 | 2 |" in md

    def test_pipe_escaped(self):
        soup = parse_html("""
        <table><tr><td>a|b</td><td>c</td></tr></table>
        """)
        md = render_body(soup, "mpark")
        assert r"a\|b" in md


class TestList:
    def test_unordered(self):
        soup = parse_html("<ul><li>One</li><li>Two</li></ul>")
        md = render_body(soup, "mpark")
        assert "- One" in md
        assert "- Two" in md

    def test_ordered(self):
        soup = parse_html("<ol><li>First</li><li>Second</li></ol>")
        md = render_body(soup, "mpark")
        assert "1. First" in md
        assert "2. Second" in md

    def test_nested(self):
        soup = parse_html("""
        <ul>
          <li>Parent
            <ul><li>Child</li></ul>
          </li>
        </ul>
        """)
        md = render_body(soup, "mpark")
        lines = md.strip().splitlines()
        parent_line = next(l for l in lines if "Parent" in l)
        assert "Child" not in parent_line
        assert "  - Child" in md
        assert md.count("Child") == 1, (
            f"Child appears {md.count('Child')} times, expected 1. md={md!r}")
        assert md.count("Parent") == 1

    def test_nested_three_levels(self):
        soup = parse_html("""
        <ul>
          <li>One
            <ul>
              <li>Two
                <ul><li>Three</li></ul>
              </li>
            </ul>
          </li>
        </ul>
        """)
        md = render_body(soup, "mpark")
        assert md.count("One") == 1
        assert md.count("Two") == 1
        assert md.count("Three") == 1
        assert "- One" in md
        assert "  - Two" in md
        assert "    - Three" in md

    def test_nested_ordered(self):
        soup = parse_html("""
        <ol>
          <li>First
            <ul><li>Bullet</li></ul>
          </li>
          <li>Second
            <ol><li>Sub</li></ol>
          </li>
        </ol>
        """)
        md = render_body(soup, "mpark")
        assert md.count("Bullet") == 1
        assert md.count("Sub") == 1
        assert "1. First" in md
        assert "  - Bullet" in md
        assert "2. Second" in md
        assert "  1. Sub" in md

    def test_nested_mixed_content(self):
        soup = parse_html("""
        <ul>
          <li>Before <strong>emphasis</strong>
            <ul><li>Nested</li></ul>
            after text
          </li>
        </ul>
        """)
        md = render_body(soup, "mpark")
        assert md.count("Nested") == 1
        assert "Before" in md
        assert "**emphasis**" in md
        assert md.count("after text") == 1

    def test_nested_multi_level(self):
        soup = parse_html("""
        <ul>
          <li>A
            <ul>
              <li>B
                <ol><li>C</li></ol>
              </li>
            </ul>
          </li>
        </ul>
        """)
        md = render_body(soup, "mpark")
        lines = md.strip().splitlines()
        a_line = next(l for l in lines if "A" in l and l.strip().startswith("-"))
        assert "B" not in a_line
        assert "C" not in a_line
        b_line = next(l for l in lines if "B" in l)
        assert "C" not in b_line


class TestWording:
    def test_wording_add_fence(self):
        soup = parse_html('<div class="wording-add"><p>New text</p></div>')
        md = render_body(soup, "mpark")
        assert ":::wording-add" in md
        assert ":::" in md.split(":::wording-add")[1]

    def test_wording_remove_fence(self):
        soup = parse_html('<div class="wording-remove"><p>Old text</p></div>')
        md = render_body(soup, "mpark")
        assert ":::wording-remove" in md

    def test_wording_mixed_fence(self):
        soup = parse_html('<div class="wording"><p>Spec text</p></div>')
        md = render_body(soup, "mpark")
        assert ":::wording\n" in md

    def test_ins_del_passthrough(self):
        soup = parse_html("<p><ins>added</ins> and <del>removed</del></p>")
        md = render_body(soup, "mpark")
        assert "<ins>added</ins>" in md
        assert "<del>removed</del>" in md


class TestBlockquote:
    def test_blockquote(self):
        soup = parse_html("<blockquote><p>Quoted text</p></blockquote>")
        md = render_body(soup, "mpark")
        assert "> Quoted text" in md


class TestInlineFormatting:
    def test_bold(self):
        soup = parse_html("<p><strong>bold</strong></p>")
        md = render_body(soup, "mpark")
        assert "**bold**" in md

    def test_italic(self):
        soup = parse_html("<p><em>italic</em></p>")
        md = render_body(soup, "mpark")
        assert "*italic*" in md

    def test_link(self):
        soup = parse_html('<p><a href="https://example.com">link</a></p>')
        md = render_body(soup, "mpark")
        assert "[link](https://example.com)" in md

    def test_anchor_link_plain(self):
        soup = parse_html('<p><a href="#section">section</a></p>')
        md = render_body(soup, "mpark")
        assert "section" in md
        assert "[" not in md

    def test_sub_sup_passthrough(self):
        soup = parse_html("<p>x<sub>2</sub> + y<sup>3</sup></p>")
        md = render_body(soup, "mpark")
        assert "<sub>2</sub>" in md
        assert "<sup>3</sup>" in md


class TestCollapseWhitespace:
    def test_collapses_spaces(self):
        md = render_body(parse_html("<p>hello   world</p>"), "mpark")
        assert "hello world" in md

    def test_strips_format_chars(self):
        md = render_body(parse_html("<p>hello\u200bworld</p>"), "mpark")
        assert "helloworld" in md

    def test_strips_and_trims(self):
        md = render_body(parse_html("<p>  hi  </p>"), "mpark")
        assert md.strip() == "hi"


class TestDocumentShell:
    def test_fragment_without_body(self):
        md = render_body(parse_html("<p>Frag</p>"), "mpark")
        assert "Frag" in md

    def test_full_document_with_body(self):
        html = "<html><head></head><body><p>In body</p></body></html>"
        md = render_body(parse_html(html), "mpark")
        assert "In body" in md


class TestStructuralTags:
    def test_hr(self):
        md = render_body(parse_html("<body><hr/><p>a</p></body>"), "mpark")
        assert "---" in md
        assert "a" in md

    def test_section_flattens(self):
        md = render_body(parse_html("<section><p>in</p></section>"), "mpark")
        assert "in" in md

    def test_main_article(self):
        md = render_body(parse_html("<main><p>m</p></main><article><p>a</p></article>"), "mpark")
        assert "m" in md and "a" in md


class TestHeadingEdgeCases:
    def test_secno_and_self_link_skipped(self):
        html = """<h2><span class="secno">3</span>Sec
        <a class="self-link" href="#x">#</a></h2>"""
        md = render_body(parse_html(html), "mpark")
        assert "## Sec" in md or "## Sec #" in md
        assert "self-link" not in md

    def test_heading_only_skipped_number_span_empty(self):
        soup = parse_html('<h1><span class="header-section-number">1</span></h1>')
        md = render_body(soup, "mpark")
        assert "#" not in md.strip() or md.strip() == ""


class TestCodeBlockExtended:
    def test_pre_without_code(self):
        md = render_body(parse_html("<pre>plain\nlines</pre>"), "mpark")
        assert "```" in md
        assert "plain" in md

    def test_language_hyphen_class(self):
        md = render_body(
            parse_html('<pre><code class="language-rust">let x;</code></pre>'),
            "mpark",
        )
        assert "```rust" in md

    def test_source_code_python_camel_class(self):
        md = render_body(
            parse_html('<pre><code class="sourceCodePython">x=1</code></pre>'),
            "mpark",
        )
        assert "```python" in md

    def test_source_code_on_parent_pre(self):
        md = render_body(
            parse_html(
                '<pre class="sourceCode cpp"><code>int y;</code></pre>'
            ),
            "mpark",
        )
        assert "```cpp" in md

    def test_bikeshed_no_default_lang_without_class(self):
        md = render_body(parse_html("<pre><code>x</code></pre>"), "bikeshed")
        assert md.startswith("```\n") or "\n```\n" in md
        assert "```cpp" not in md


class TestDivDispatch:
    def test_div_source_code_wraps_pre(self):
        html = (
            '<div class="sourceCode"><pre><code class="sourceCode cpp">z();'
            "</code></pre></div>"
        )
        md = render_body(parse_html(html), "mpark")
        assert "```cpp" in md

    def test_div_note_blockquote_style(self):
        md = render_body(
            parse_html('<div class="note"><p>Line one</p><p>Two</p></div>'),
            "mpark",
        )
        assert md.strip().startswith(">")
        assert "Line one" in md

    def test_div_example(self):
        md = render_body(parse_html('<div class="example"><p>ex</p></div>'), "mpark")
        assert "> ex" in md.replace("\n", " ") or "> ex" in md

    def test_plain_div_transparent(self):
        md = render_body(parse_html("<div><p>inner</p></div>"), "mpark")
        assert "inner" in md


class TestTableExtended:
    def test_nested_table_not_in_outer_rows(self):
        html = """
        <table>
        <tr><th>OuterA</th><th>OuterB</th></tr>
        <tr><td>1</td><td><table><tr><td>Inner</td></tr></table></td></tr>
        </table>
        """
        md = render_body(parse_html(html), "mpark")
        lines = [ln for ln in md.splitlines() if ln.startswith("|")]
        assert any("OuterA" in ln for ln in lines)
        assert sum(1 for ln in lines if "Inner" in ln) == 1

    def test_short_row_padding(self):
        html = """
        <table>
        <tr><th>A</th><th>B</th><th>C</th></tr>
        <tr><td>1</td><td>2</td></tr>
        </table>
        """
        md = render_body(parse_html(html), "mpark")
        assert "| 1 | 2 |" in md or "| 1 | 2 | |" in md


class TestDefinitionList:
    def test_dl_dt_dd(self):
        html = "<dl><dt>Term</dt><dd>Def</dd></dl>"
        md = render_body(parse_html(html), "mpark")
        assert "**Term**" in md
        assert ": Def" in md


class TestLinksExtended:
    def test_mailto_link(self):
        md = render_body(
            parse_html('<p><a href="mailto:a@b.co">Mail me</a></p>'),
            "mpark",
        )
        assert "[Mail me](mailto:a@b.co)" in md

    def test_disallowed_scheme_plain_text(self):
        md = render_body(
            parse_html('<p><a href="ftp://x.com">ftp</a></p>'),
            "mpark",
        )
        assert "ftp" in md
        assert "](" not in md

    def test_anchor_no_href_text_only(self):
        md = render_body(parse_html("<p><a>nohref</a></p>"), "mpark")
        assert "nohref" in md


class TestBlockquoteExtended:
    def test_nested_paragraphs(self):
        md = render_body(
            parse_html("<blockquote><p>First</p><p>Second</p></blockquote>"),
            "mpark",
        )
        assert "> First" in md
        assert "Second" in md

    def test_empty_blockquote_omitted(self):
        md = render_body(parse_html("<blockquote></blockquote><p>x</p>"), "mpark")
        assert md.strip() == "x"


class TestListExtended:
    def test_ol_with_nested_ul(self):
        html = "<ol><li>Outer<ul><li>Inner</li></ul></li></ol>"
        md = render_body(parse_html(html), "mpark")
        assert "1. Outer" in md
        assert "  - Inner" in md


class TestTransparentInline:
    def test_mark_kbd_passthrough(self):
        md = render_body(
            parse_html("<p><mark>m</mark> <kbd>k</kbd></p>"),
            "mpark",
        )
        assert "m" in md and "k" in md


class TestHtmlComments:
    def test_comment_content_not_rendered(self):
        """HTML comments must never appear in Markdown output."""
        html = "<p>Visible text.</p><!-- This comment should be invisible -->"
        md = render_body(parse_html(html), "mpark")
        assert "Visible text." in md
        assert "comment" not in md
        assert "invisible" not in md

    def test_comment_with_html_tags_not_rendered(self):
        """Commented-out HTML blocks (e.g. draft sections) must not leak into output."""
        html = (
            "<p>Before.</p>"
            "<!-- <h2>Draft Section</h2><p>Draft content</p> -->"
            "<p>After.</p>"
        )
        md = render_body(parse_html(html), "mpark")
        assert "Before." in md
        assert "After." in md
        assert "Draft Section" not in md
        assert "Draft content" not in md

    def test_comment_with_entities_not_rendered(self):
        """Entities inside comments (e.g. &lt; in commented-out code) must not appear."""
        html = (
            "<p>Intro.</p>"
            "<!-- <pre>template &lt;class T&gt; void f();</pre> -->"
            "<p>Body.</p>"
        )
        md = render_body(parse_html(html), "mpark")
        assert "Intro." in md
        assert "Body." in md
        assert "&lt;" not in md
        assert "&gt;" not in md
        assert "template" not in md

    def test_comment_between_inline_elements_not_rendered(self):
        """Comments inline between spans must not insert text into the output."""
        html = "<p>Hello<!-- drop this --> world</p>"
        md = render_body(parse_html(html), "mpark")
        assert "Hello world" in md
        assert "drop this" not in md

    def test_comment_in_heading_not_rendered(self):
        """Comments inside headings are stripped."""
        html = "<h2>Real Title<!-- draft annotation --></h2>"
        md = render_body(parse_html(html), "mpark")
        assert "## Real Title" in md
        assert "draft annotation" not in md
