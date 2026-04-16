# Code Review: tomd

- **Date:** Wednesday Apr 15, 2026
- **Model:** kimi-k2.5
- **Scope:** lib/, lib/html/, lib/pdf/ (15 Python modules, ~2,900 lines)

Well-architected dual-path PDF converter with clean separation between HTML and PDF layers, though minor duplication in whitespace handling and some leaky abstractions around metadata extraction pathways.

## Executive Summary

The tomd project demonstrates solid architectural decisions with its dual-extraction confidence mechanism and clear layering (lib/ for shared utilities, lib/pdf/ and lib/html/ for format-specific logic). The 15 Python files show good modularity with the PDF pipeline broken into focused phases (extract, cleanup, structure, emit). Cross-file analysis reveals primarily surface-level issues: some whitespace normalization logic duplicated across renderers, multiple metadata extraction pathways that require careful merging, and naming inconsistencies between monospace-related functions. The codebase successfully avoids deeper structural problems—no circular dependencies, minimal API leakage, and good type cohesion in lib/pdf/types.py. The HTML layer correctly reuses shared utilities (ascii_escape, format_front_matter) rather than duplicating them.

## Codebase Profile

### Core Types and Constants

Central type definitions (Span, Line, Block, Section) and threshold constants used across the PDF layer. All PDF modules depend on this; changes here have wide impact. Good use of dataclasses and enums.

- `lib/pdf/types.py`

### PDF Pipeline - Extraction Phase

Dual-path extraction (MuPDF dict API + spatial rawdict) and related preprocessing. The spatial path uses closure-based state management for character-to-span grouping. Monospace detection uses a triple-signal analysis (font name, glyph width uniformity, glyph spacing uniformity).

- `lib/pdf/extract.py` - Dual-path extraction with MuPDF and spatial paths
- `lib/pdf/mono.py` - Triple-signal monospace detection
- `lib/pdf/wording.py` - HSV color analysis for ins/del markup detection
- `lib/pdf/spans.py` - Style boundary snapping to word edges

### PDF Pipeline - Cleanup Phase

Header/footer detection via repeating pattern analysis, dehyphenation, cross-page paragraph joining, hidden region stripping. The cleanup module contains pure functions with explicit types and focused responsibilities.

- `lib/pdf/cleanup.py`

### PDF Pipeline - Structure and Output

Geometric table detection, WG21-specific metadata extraction, and Markdown emission. Table detection uses x-gap heuristics for columnar layout identification.

- `lib/pdf/table.py` - Geometric table detection
- `lib/pdf/wg21.py` - WG21-specific metadata extraction

### PDF Orchestration

Pipeline coordinator with 14-stage processing. Merges three metadata pathways and orchestrates dual-extraction confidence scoring.

- `lib/pdf/__init__.py` - Main convert_pdf entry point

### HTML Converter

Complete separate HTML-to-Markdown converter with its own parse/extract/render phases. The DOM-to-Markdown renderer uses recursive descent with 17 tag-specific handlers.

- `lib/html/__init__.py` - HTML converter entry point
- `lib/html/extract.py` - Generator detection and metadata extraction
- `lib/html/render.py` - Recursive DOM-to-Markdown renderer

### Shared Utilities

Format-agnostic helpers used by both PDF and HTML converters. The similarity module provides dual-algorithm fuzzy matching; toc detection uses string similarity for heading matching.

- `lib/__init__.py` - Text utilities and YAML front-matter formatting
- `lib/similarity.py` - SequenceMatcher + Jaccard fuzzy matching
- `lib/toc.py` - Table of Contents detection

### File Profiles

**lib/__init__.py** - Shared text utilities (ascii_escape, strip_format_chars, format_front_matter) and base regex patterns. Acts as the shared kernel for both converters.

**lib/similarity.py** - Dual-algorithm fuzzy matching with circuit breaker for long strings. Clean, focused, no dependencies on PDF types.

**lib/toc.py** - Table of Contents detection using fuzzy heading matching. Correctly format-agnostic, operates only on strings.

**lib/pdf/types.py** - Central type definitions and constants. All PDF modules depend on this; good use of dataclasses and enums.

**lib/pdf/extract.py** - Dual-path extraction (MuPDF dict API + spatial rawdict). Contains closure-based state machine for spatial parsing.

**lib/pdf/mono.py** - Triple-signal monospace detection with clear signal definitions and acceptance rules.

**lib/pdf/spans.py** - Style boundary normalization. Uses dataclasses.replace for immutable updates. Clean single-responsibility module.

**lib/pdf/cleanup.py** - Header/footer detection, dehyphenation, cross-page joining, hidden region stripping.

**lib/pdf/table.py** - Geometric table detection from MuPDF block positions using x-gap heuristics.

**lib/pdf/wording.py** - HSV color analysis + drawing decoration correlation for ins/del markup detection.

**lib/pdf/wg21.py** - WG21-specific metadata extraction from PDF blocks. Reply-to continuation logic may over-consume.

**lib/pdf/__init__.py** - Pipeline orchestrator with 14-stage processing. Merges three metadata pathways.

**lib/html/__init__.py** - HTML converter entry point. Reuses ascii_escape and format_front_matter from lib/.

**lib/html/extract.py** - HTML parsing with generator-specific extractors for mpark, Bikeshed, and HackMD formats.

**lib/html/render.py** - DOM-to-Markdown recursive descent renderer with 17 functions. Mutates soup via sub.extract() in _render_list (documented side effect).

## Cross-cutting Analysis

The architecture successfully separates concerns between PDF and HTML conversion while sharing format-agnostic utilities. The PDF pipeline follows a clear phase structure: extraction (dual-path) → cleanup → structure → emit, with each phase having well-defined inputs/outputs using the shared type system.

Module boundaries are generally respected—lib/pdf/ modules import from each other and lib/, but never from lib/html/. The shared utilities in lib/ (similarity, toc) correctly avoid importing PDF-specific types, making them reusable.

The dual-extraction confidence mechanism is the architectural centerpiece and is well-executed. Both MuPDF and spatial paths produce identical Block structures, enabling direct comparison. The monospace propagation pattern (spatial decisions applied to MuPDF spans post-extraction) is a pragmatic solution to the rawdict/dict API asymmetry.

Metadata extraction follows a three-pathway design: structure._extract_metadata (section scan), wg21.extract_metadata_from_blocks (block scan), and html.extract.extract_metadata (DOM scan). The merge precedence is documented but distributed across files—understanding the full flow requires reading multiple locations.

Whitespace handling shows the most duplication: _collapse_spaces in cleanup.py, _collapse_whitespace in html/render.py, and _MULTI_SPACE_RE in structure.py. The HTML renderer needs its own version because it operates on DOM text nodes rather than PDF spans, but the regex patterns and logic overlap significantly.

Bounding box computation appears in extract.py as _compute_bbox and inline in cleanup.py's _join_cross_page. The inline version computes min/max across four lines manually rather than calling a helper—a minor readability issue.

## Findings

### Must fix

1. `lib/pdf/extract.py:17` - Add guard for empty bboxes list before calling min/max
   (min/max on empty list raises ValueError at runtime)

### Should fix

2. `lib/pdf/__init__.py:133` - Add guard for empty font_counts before calling most_common(1)[0][0]
   (IndexError when PDF has no text spans with non-whitespace content)

3. `lib/pdf/types.py:145`, `lib/__init__.py:154` - Document distinction between DOC_NUM_RE and DOC_FIELD_RE
   (two patterns with different semantics but similar names; naming doesn't convey distinction at call sites)

4. `lib/pdf/types.py:25`, `lib/pdf/mono.py:60` - Align monospace terminology
   (Span field is 'monospace' but detector uses 'classify_monospace' naming; returns bool which is slightly surprising)

5. `lib/pdf/wg21.py:162-179` - Add limit to reply-to continuation block consumption
   (may over-consume body content as reply-to authors on malformed PDFs)

### Nice to have

6. `lib/pdf/cleanup.py:182`, `lib/html/render.py:117`, `lib/pdf/structure.py:23` - Consolidate whitespace collapse regex patterns
   (three modules define similar multi-space collapse patterns independently)

7. `lib/pdf/extract.py:17`, `lib/pdf/cleanup.py:166-171` - Consider using _compute_bbox helper in cleanup.py
   (minor code duplication for bbox computation)

8. `lib/pdf/__init__.py:171-177`, `lib/pdf/structure.py:249-254`, `lib/pdf/wg21.py:81-88` - Consolidate metadata pathway documentation
   (three extraction pathways documented across three files)

9. `lib/pdf/structure.py:50-60`, `lib/similarity.py:31-46` - Consider sharing multiset similarity logic
   (both use multiset/Counter intersection but implemented independently)

10. `lib/pdf/wording.py:121-123` - Replace bare `except Exception:` with specific MuPDF exception types
    (silent exception swallowing masks extraction failures from caller)

15 files / 105 functions reviewed. The majority of the codebase is clean and well-structured.
