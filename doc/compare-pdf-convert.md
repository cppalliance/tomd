# PDF-to-Markdown Converter Comparison

**tomd** vs **CppDigest/wg21-paper-markdown-converter**

---

## Executive Summaries

### tomd

tomd is a deterministic, single-dependency PDF-to-Markdown converter purpose-built for WG21 committee papers. Its core idea is *dual-path extraction with confidence scoring* - every page is processed through two independent text extraction algorithms (MuPDF structured dict and raw spatial character assembly), and their outputs are compared at the word level. When the two paths agree, the result is emitted with high confidence. When they disagree, the MuPDF version goes into the output with an HTML comment warning, and both versions are written to a companion `.prompts.md` file for human-directed LLM reconciliation.

The architecture is a deep pipeline of specialized modules: header/footer stripping, monospace detection via triple-signal analysis, table detection from columnar geometry, heading classification using section numbering + font size + font weight + known section names, dehyphenation, cross-page paragraph joining, and link extraction from PDF annotations. Every structural decision (heading, code, table, list) requires agreement from multiple signals before it earns high confidence. The only external dependency is PyMuPDF.

tomd does not call any LLM or external API. It produces markdown deterministically from PDF geometry and font metadata, and defers ambiguous regions to a separate file the user can feed to any LLM of their choosing.

### CppDigest/wg21-paper-markdown-converter

The CppDigest converter is a URL-oriented batch processing tool designed for CI/CD automation. It accepts a JSON list of URLs, detects whether each is HTML or PDF, and converts them to markdown. For HTML, it uses Pandoc with lxml preprocessing and extensive regex-based post-processing. For PDF, it runs a three-tier fallback chain: docling (a document-understanding ML library), then pdfplumber (simpler text extraction), then OpenRouter Vision API (renders pages to images, sends to GPT-4o or similar model for OCR-style extraction).

The tool's philosophy is *try everything until something works*. Each tier's output is checked by an `is_readable()` heuristic (length, character ratio, slash density), and the first tier that passes is used. No structural analysis, heading detection, or multi-signal classification is attempted in the PDF path - whatever the upstream library or LLM returns is the final output. The project includes GitHub Actions workflow integration, artifact management, and an API-based push mechanism for deploying results to other repositories.

---

## Comparison

| Dimension | tomd | CppDigest converter |
|---|---|---|
| **Input** | Local PDF files (glob patterns) | URLs (JSON list, HTML or PDF) |
| **PDF approach** | Deterministic dual-path extraction with confidence scoring | Three-tier fallback: docling -> pdfplumber -> OpenRouter Vision LLM |
| **HTML support** | Not yet (planned) | Yes, via Pandoc + lxml + post-processing |
| **External dependencies** | PyMuPDF only | docling, pdfplumber, PyMuPDF, Pillow, Pandoc, lxml, pypandoc, requests, python-dotenv |
| **LLM usage** | None (deferred to companion file for human use) | OpenRouter Vision API as last-resort fallback |
| **Structure detection** | Multi-signal: section numbers, font size, font weight, known names, line geometry, dual-path agreement | Delegated entirely to upstream libraries (docling, pdfplumber) or LLM |
| **Heading classification** | Section-number depth + font-size ranking + known-name matching + bold detection, with validated nesting | Whatever upstream produces |
| **Table detection** | Custom columnar geometry analysis on MuPDF blocks | Whatever upstream produces |
| **Code block detection** | Triple-signal monospace analysis (font name, glyph width uniformity, glyph spacing uniformity) | Whatever upstream produces |
| **Confidence tracking** | Four-level enum (HIGH, MEDIUM, LOW, UNCERTAIN) on every section | Binary: `is_readable()` pass/fail per entire document |
| **Uncertain output** | HTML comment markers + companion prompts file with both extraction versions | Silent - no uncertainty signaling |
| **WG21-specific features** | YAML front matter from metadata, known section names, TOC detection and removal | None |
| **CI/CD integration** | None (CLI tool) | GitHub Actions workflow with artifact upload and cross-repo push |
| **Batch processing** | Glob patterns for local files | JSON URL list with result.json summary |
| **Cost** | Free (no API calls) | Free for tiers 1-2; OpenRouter API costs for tier 3 |
| **Reproducibility** | Fully deterministic - same PDF always produces same output | Non-deterministic when LLM fallback is used |
| **Codebase size** | ~12 Python files, ~2000 lines of specialized logic | ~5 Python files, ~600 lines (much delegated to libraries) |

### Philosophical difference

tomd treats PDF conversion as a *precision problem* - it extracts maximum information from the PDF's own metadata (fonts, coordinates, spans) and cross-validates using independent extraction paths. It would rather flag uncertainty than silently produce wrong structure.

The CppDigest converter treats it as a *availability problem* - it tries increasingly expensive methods until one produces readable output, prioritizing "something works" over structural accuracy. It trades precision for breadth (handles HTML too) and operational convenience (CI pipeline, URL-based input).

### Where they complement each other

tomd's deterministic analysis could serve as a quality-assessment layer for the CppDigest pipeline - running tomd on the same PDF and comparing outputs would catch structural errors in docling/pdfplumber results. Conversely, the CppDigest converter's HTML path and CI infrastructure are capabilities tomd doesn't have yet.

---

## Deep Dive: tomd

### Pipeline

```
PDF file
  |
  v
[fitz.open] -- per page:
  |-- extract_mupdf(page)     -- page.get_text("dict"), structured blocks/lines/spans
  |-- extract_spatial(page)   -- page.get_text("rawdict"), raw chars assembled by coordinate rules
  |-- collect_links(page)     -- page.get_links(), filter http/https/mailto
  |-- attach_links            -- match link rects to best-overlap spans in both block lists
  |-- get_edge_items          -- top-3/bottom-3 text items by y-coordinate for header/footer analysis
  v
[detect_repeating]  -- compare edge items across pages, flag items on 50%+ pages as headers/footers
  |
[strip_repeating]   -- remove flagged items from both block lists
  |
[cleanup_text]      -- normalize whitespace, join cross-page paragraphs (no terminal punct + lowercase continuation)
  |
[detect_tables]     -- columnar geometry on MuPDF blocks: 2+ lines, x-gap > threshold, matching column positions
  |
[exclude_table_regions] -- remove spatial blocks that overlap detected table y-ranges
  |
[compare_extractions]   -- per-page word-level similarity (Counter intersection / max)
  |                        >= 0.85: HIGH confidence, use MuPDF blocks
  |                        <  0.85: UNCERTAIN, whole page flagged, both versions preserved
  |
[merge tables back] -- insert table sections by page/y-position
  |
[structure_sections] -- heading classification (multi-signal), list detection, code block merging,
  |                     metadata extraction, title detection, nesting validation
  |
[find_toc_indices]  -- fuzzy-match section texts against detected headings, remove TOC entries
  |
[emit_markdown]     -- YAML front matter + rendered sections with uncertainty markers
[emit_prompts]      -- companion file with both extraction versions for uncertain regions (if any)
```

### Dual extraction - why it matters

MuPDF's `get_text("dict")` returns pre-grouped blocks/lines/spans based on its internal layout analysis. This is usually good but can merge or split text incorrectly, especially with multi-column layouts, footnotes, or complex formatting. The spatial path starts from raw character positions and applies four coordinate rules:

1. Horizontal close -> same word (gap < avg_font_size * WORD_GAP_RATIO)
2. Horizontal far -> word break (insert space)
3. Vertical close + left reset -> line continuation in same paragraph
4. Vertical far -> paragraph break (gap > avg_font_size * PARA_SPACING_RATIO)

When both paths produce the same words in the same order (>= 85% overlap), MuPDF's grouping is trusted. When they disagree, something unusual is happening in the PDF layout - the disagreement itself is the signal that human review (or LLM assistance) is needed.

### Multi-signal heading classification

A heading is never classified from a single feature. The system evaluates:

- **Section numbering** (highest signal): regex match on dotted decimal (`2.1.3` = depth 3 = `####`)
- **Font size** (high signal): sizes ranked relative to detected body size; anything larger than body by HEADING_SIZE_RATIO or TITLE_SIZE_RATIO is a heading candidate
- **Font weight** (medium signal): bold flag from font metadata
- **Known section names** (high for WG21): `Abstract`, `References`, `Wording`, `Motivation`, etc. recognized as `##`
- **Dual-path agreement** (high signal): both extraction paths identifying same boundary

The `_heading_confidence` function combines these into a Confidence level. Nesting validation then checks that no heading jumps more than one level deeper than its predecessor - if it does, the level is corrected and confidence downgraded from HIGH to MEDIUM.

### Monospace / code detection

Three independent signals vote on whether a font run is monospace:

1. **Font name patterns**: stripped of modifiers, checked against `{mono, courier, code, consolas}`
2. **Glyph width uniformity**: coefficient of variation of character widths < 0.15
3. **Glyph spacing uniformity**: coefficient of variation of x-origin spacings < 0.15

Two-of-three agreement, or signal 3 alone (strong), or signal 1 alone (fallback) triggers monospace classification. Consecutive monospace sections are then merged into code blocks, with optional language-label detection from a preceding section.

### Where tomd might fall short

- **No HTML support yet.** Many WG21 papers are published as HTML (especially from newer toolchains like mpark/wg21 or bikeshed). tomd currently handles only PDF.
- **Page-level granularity for uncertainty.** When the two extraction paths disagree, the entire page becomes one UNCERTAIN section. A paragraph-level or block-level comparison would produce more targeted uncertainty markers and less work for the human reviewer.
- **Table detection is geometry-only.** It relies on columnar x-gap patterns in MuPDF blocks. Tables without clear columnar alignment (e.g., tables rendered with ruled lines but no x-gaps between cells) may be missed. Tables with merged cells or complex spans are likely mishandled.
- **No OCR capability.** Scanned PDFs or PDFs with embedded images containing text will produce empty or garbage output. There is no image rendering or vision model fallback.
- **Single-pass TOC removal.** TOC detection uses fuzzy matching of section texts against headings. If section titles are substantially different from their TOC entries (abbreviated, reworded), the TOC may survive as body text.
- **Cross-page paragraph joining is heuristic.** The "no terminal punctuation + lowercase continuation" rule can false-positive on lists, code examples, or tables that happen to span page breaks.
- **No batch URL fetching.** Input must be local files. There is no download, CI integration, or artifact management.
- **v1 LLM integration is manual.** The prompts file is well-structured, but the user must copy it to an LLM interface and paste the result back. The `--llm` auto-resolution flag is deferred to v2.

---

## Deep Dive: CppDigest/wg21-paper-markdown-converter

### Pipeline

```
URL list (JSON)
  |
  v
[detect_type] -- .pdf suffix or Content-Type header
  |
  +-- HTML path:
  |     [fetch_html]
  |     [preprocess_html_for_metadata] -- move body content outside <main> into <main>
  |     [_preprocess_html_content]     -- lxml parse + re-serialize to fix malformed HTML
  |     [pypandoc.convert_text]        -- Pandoc GFM conversion
  |     [post_process_markdown]        -- extensive regex cleanup of Pandoc output
  |     [_convert_html_tables_to_markdown] -- regex-based HTML table -> GFM table conversion
  |
  +-- PDF path:
        [fetch_pdf] -- download to temp file
        |
        +-- Tier 1: [convert_with_docling]
        |     DocumentConverter().convert().export_to_markdown()
        |     check is_readable() -- pass? done. fail? next tier.
        |
        +-- Tier 2: [convert_with_pdfplumber]
        |     pdfplumber.open(), page.extract_text() per page, join with \n\n
        |     check is_readable() -- pass? done. fail? next tier.
        |
        +-- Tier 3: [convert_with_openrouter]
              [_pdf_to_images] -- PyMuPDF renders pages to PNG at 200 DPI
              per page:
                [_send_page_to_openrouter] -- base64 PNG + prompt -> OpenRouter Vision API
                strip ```markdown wrappers
              join pages with --- separator
              check is_readable()
  |
  v
[result.json] -- summary of successes/failures
[zip_folder]  -- zip output directory
[push_via_github_api.py] -- optional: push .md files to target repo via Git blob/tree/commit API
```

### The three PDF tiers in detail

**Tier 1: docling.** The `docling` library (from IBM Research) is a document-understanding system that uses ML models to detect layout regions (text, tables, figures, headers) and extract structured content. It handles multi-column layouts, recognizes tables, and produces markdown with headings and formatting. When it works, it produces the highest-quality output of the three tiers. The `is_readable()` check verifies the output has sufficient readable characters.

**Tier 2: pdfplumber.** A simpler library built on pdfminer.six. It extracts text per page using character-level position analysis. No heading detection, no structural analysis - just raw text with basic word/line grouping. The output is pages joined by double newlines. This tier exists because pdfplumber handles some PDFs (especially those with unusual font encodings) that docling fails on.

**Tier 3: OpenRouter Vision.** Last resort. Each page is rendered to a 200 DPI PNG image, base64-encoded, and sent to a vision model (default: GPT-4o) with a prompt asking it to extract text in markdown format. The model gets per-page images with no cross-page context. Results are joined with `---` separators. This tier handles scanned documents and PDFs with rendering issues but is slow, costs money, and produces non-deterministic output.

### HTML conversion path

The HTML path is more substantial than the PDF path in terms of custom logic:

1. **Preprocessing** handles a specific WG21 HTML pattern where body content sits outside the `<main>` tag, causing Pandoc to skip it. The code moves that content inside `<main>`.
2. **Pandoc** does the heavy lifting of HTML-to-GFM conversion.
3. **Post-processing** is ~200 lines of regex transformations: cleaning up anchor tags from headings, converting residual HTML inline tags (`<strong>`, `<em>`, `<code>`, `<del>`, `<mark>`) to markdown equivalents, fixing code block spacing, removing empty headings, and collapsing excessive blank lines.
4. **Table conversion** handles HTML `<table>` elements that Pandoc left as raw HTML, converting them to GFM pipe tables via regex parsing of `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>` elements.

### CI/CD integration

The GitHub Actions workflow provides:

- `workflow_dispatch` with configurable inputs (URL list, output dir, model choice, target repo)
- Automatic artifact upload (zip + result.json, 90-day retention)
- Optional cross-repo push via the GitHub REST API (git blobs + trees + commits, no git binary needed on runner)
- Partial-failure handling: successful files are pushed even when some URLs fail

### Where the CppDigest converter might fall short

- **No structural analysis for PDFs.** The PDF path does zero custom analysis - no heading detection, no code block recognition, no table parsing, no metadata extraction. Output quality depends entirely on docling, pdfplumber, or the LLM. For WG21 papers specifically, this means no YAML front matter, no section-number-based heading levels, no TOC removal.
- **pdfplumber tier produces raw text.** When docling fails and pdfplumber succeeds, the output is plain text with no markdown formatting at all - no headings, no code fences, no tables, no links. The `is_readable()` check only verifies character ratios, not structural quality.
- **LLM tier has no cross-page context.** Each page is sent independently to the vision model. Paragraphs spanning page breaks will be split. Tables spanning pages will be treated as separate tables. There is no joining, deduplication, or consistency checking across pages.
- **`is_readable()` is a weak quality gate.** It checks character length (>100), alphanumeric ratio (>30%), and slash density (<10%). A document with correct characters but completely wrong structure (mangled headings, merged paragraphs, broken tables) passes this check. There is no semantic or structural quality assessment.
- **OpenRouter tier is expensive and non-deterministic.** Each page requires an API call with a base64-encoded image. A 30-page paper at 200 DPI generates ~30 API calls. The same paper converted twice may produce different markdown. Model availability and pricing are external dependencies.
- **HTML post-processing is regex-heavy and fragile.** The ~200 lines of regex cleanup in `post_process_markdown` handle known Pandoc artifacts, but novel HTML structures will produce novel artifacts. The table conversion regex parser does not handle nested tables, colspan/rowspan, or `<caption>` elements.
- **No header/footer stripping.** Page numbers, running headers, and document numbers from PDF extraction are left in the output. For multi-page papers, this creates noise throughout the document.
- **No dehyphenation.** Words broken across lines with hyphens (common in PDF text extraction) remain broken in the output.
- **No confidence signaling.** The user has no way to know which sections of the output are likely correct vs. likely wrong. The tool either succeeds or fails at the whole-document level.
- **Heavy dependency footprint.** docling pulls in PyTorch and transformer models. A fresh `pip install` can take many minutes and hundreds of megabytes. This is acknowledged in the README but remains a significant operational burden.
