# tomd: Algorithmic Sophistication Outpacing Operational Discipline

**A PDF-to-Markdown converter whose dual-extraction architecture surpasses its competitors' deterministic approaches, yet lacks the testing and error contracts to match.**

April 2026, by Vinnie Falco

---

## 1. Executive Summary

tomd's core design is smarter than anything else in the rule-based PDF-to-Markdown space. Dual extraction paths with multi-signal confidence scoring, companion prompt files for selective LLM escalation, and WG21-specific metadata intelligence represent a genuine advance over the single-pipeline approaches used by PyMuPDF4LLM and similar tools.<sup>1</sup> The architecture document reveals a developer who thinks carefully about the hard problem - structural analysis of ambiguous PDF content.

The dominant dynamic shaping tomd's design quality is a failure-signaling deficit that pervades the API surface and cascades into four compound weaknesses. `convert_pdf` returns `("", None)` for both empty documents and unreadable PDFs<sup>3</sup> - two fundamentally different conditions collapsed into identical output. This overloaded return value combines with bare `except Exception` handling and non-atomic output writes to create a tool that silently produces ambiguous results when it fails - the opposite of the structural honesty the architecture document demands.

The most important finding is the complete absence of tests. For a tool that performs complex multi-signal structural analysis on variable PDF input, every public interface is an unverified promise. Combined with no CI and an unpinned PyMuPDF dependency, this creates a verification vacuum where the dual-extraction algorithm's correctness is defended only by manual inspection.

Against six competitors (Marker, Docling, MinerU, Unstructured, PyMuPDF4LLM, Nougat), tomd occupies a unique position: the only rule-and-geometry-first converter with explicit confidence scoring and WG21-specific targeting. Its nearest structural cousin, PyMuPDF4LLM, shares the MuPDF foundation but lacks tomd's architectural depth. The quality verdict is **Promising** - a tool whose core algorithm deserves better infrastructure.

---

## 2. The Project

tomd is a Python CLI tool that converts PDF files to Markdown.<sup>1</sup> Written by Vinnie Falco, it lives as a subdirectory within the `wg21-papers` repository - a personal workspace for C++ standards committee work. The tool targets WG21 papers specifically: it recognizes committee metadata fields (Document Number, Date, Reply-to, Audience), parses known section names (Abstract, Wording, References), and defaults fenced code blocks to C++.<sup>1</sup>

The architecture is a seven-stage pipeline: header/footer stripping, dual extraction (MuPDF dict + spatial coordinate rules), link collection, dual-path comparison with confidence scoring, text cleanup (dehyphenation, cross-page joining, whitespace normalization), structural classification (headings, paragraphs, lists, tables, code), and Markdown emission.<sup>3</sup> A companion `.prompts.md` file is generated for regions where the dual extraction paths disagree, providing context for manual LLM resolution.<sup>1</sup>

The codebase spans 12 Python source files organized in a pipeline-shaped layout: `main.py` (CLI), `lib/` (format-agnostic utilities), and `lib/pdf/` (PDF-specific pipeline stages).<sup>1</sup> `types.py` serves as the shared model layer, defining data classes (`Block`, `Span`, `Section`), confidence enums, named constants, and precompiled regex patterns.<sup>5</sup> The single external dependency is PyMuPDF, unpinned.<sup>4</sup>

The project is early-stage and personal-use. There are no tests, no CI, no versioning, no license, and no user-facing README. The author has stated plans to add testing infrastructure and intends batch processing of many papers as a primary use case.

---

## 3. The Domain

PDF-to-Markdown conversion exists because PDFs encode geometry and paint order, not logical document structure. Every converter operates in the gap between what a PDF says (coordinates, fonts, glyphs) and what a human sees (headings, paragraphs, tables, code blocks).

Five stress points shape this domain:

1. **Structural honesty.** Tables, multi-column layouts, and reading order are high-risk outputs where plausible-but-wrong Markdown is worse than flagged uncertainty. The domain demands that tools make ambiguity visible rather than silently producing broken structure.

2. **Automation contracts.** The audience is developers integrating tools into repositories and pipelines. Predictable CLI behavior - stable exit semantics, machine-friendly diagnostics, batch-safe operation - is the de facto integration standard.

3. **Semantic limits documentation.** Markdown cannot faithfully represent full PDF semantics. When output looks readable but is semantically wrong, operators need documented limits to calibrate trust.

4. **Parser security surface.** PDF parsing has a long vulnerability history across implementations. Dependencies that process documents must be version-controlled and maintained.

5. **Diff-friendly output.** Developer workflows lean on plain-text diffs and search. Noisy or unstable text conventions undermine these workflows even when conversion succeeds.

---

## 4. The Landscape

Six open-source competitors operate in PDF-to-Markdown conversion, spanning rule-based, hybrid, and pure-neural approaches:

1. **Marker** (~33k GitHub stars, GPL-3.0) - hybrid pipeline combining PDF primitives with learned layout models and optional LLM assist
2. **Docling** (~50k stars, MIT) - IBM-backed layout-model-centric parser optimized for reading order and rich structure in gen-AI workflows
3. **MinerU** (~50k stars, AGPL-3.0) - multi-backend pipeline emphasizing complex PDFs (tables, math, scans) for LLM-ready output
4. **Unstructured** (~14k stars, Apache-2.0) - general document ETL partitioning many formats into structured elements for RAG
5. **PyMuPDF4LLM** (~1-2k stars, AGPL-3.0) - lightweight MuPDF-native Markdown extraction for RAG-friendly output; closest structural cousin
6. **Nougat** (~10k stars, MIT) - Meta's pure vision model rendering PDF pages to Markdown with math emphasis

tomd differentiates on four axes: explicit dual-path extraction with confidence composition (absent elsewhere as a first-class design), companion prompt files for region-scoped LLM resolution (a novel workflow), WG21-specific metadata and section intelligence (unmatched), and triple-signal monospace detection (more explicit than competitors' heuristics).

The gaps are structural but reflect scope choices: no vision/VLM capability for scan-like pages (strong in Docling, MinerU, Nougat), no multi-format ingestion (Marker, Docling, MinerU, Unstructured), and no LaTeX/math reconstruction (Nougat, Marker). tomd targets native-text WG21 papers, not the general document extraction problem.

---

## 5. Design Assessment

### 5.1 The Failure-Signaling Deficit

The most pervasive compound dynamic in tomd's design is the absence of structured failure signaling. `convert_pdf` returns `("", None)` for both zero-page documents and unreadable/encrypted PDFs<sup>3</sup> - two fundamentally different conditions collapsed into identical output. A caller cannot distinguish "this PDF has no content" from "this PDF exists but I cannot read it" (Bloch 2006).

This overloaded return value combines with the CLI's bare `except Exception` handling<sup>2</sup> to create a double layer of silent failure. When extraction fails mid-pipeline, the exception is caught, printed as a string, and the file is counted as failed - but the failure mode (corrupt PDF? encrypted? PyMuPDF bug? I/O error?) is lost. Programmatic callers of `convert_pdf` receive no structured error information at all.<sup>3</sup>

The finding is elevated by two domain stress points. Structural honesty demands that tools make ambiguity visible - yet the API makes failure invisible. Automation contracts demand machine-friendly diagnostics for batch processing - yet the diagnostics are string messages on stderr.

This deficit persists because it is reinforced by two other findings. The `convert_pdf` docstring does not document return-value semantics for failure modes<sup>3</sup>, so the ambiguous return shape is not acknowledged as a design choice (Cwalina and Abrams 2009). And without tests, the ambiguity cannot be pinned down by assertions that would force differentiated outcomes.

### 5.2 Batch Reliability Without Contracts

tomd's stated goal of batch processing many WG21 papers creates a reliability demand that the current error design cannot meet. Output writes use `Path.write_text` directly<sup>2</sup> without atomic temp-and-rename. If the process crashes mid-write - an out-of-memory error processing a large PDF, a PyMuPDF segfault, a disk-full condition - a partial `.md` file remains on disk, indistinguishable from a complete one.

This non-atomic write combines with the error design deficit to create a specific batch-processing hazard: a run converting 200 papers that crashes on paper 150 leaves 149 complete files and one partial file, with no programmatic mechanism to identify which file is partial. The CLI prints "FAIL" to stderr for files that raise exceptions<sup>2</sup>, but a crash during `write_text` produces no such message - the partial file appears to be a success.

The absence of tests means this crash-safety property is never verified. Even if atomic writes were added, no test would prove the fix works or catch regressions (Boost Contributor Checklist).

### 5.3 The Documentation Inversion

tomd has extensive architecture documentation in `CLAUDE.md`<sup>1</sup> - a 125-line design contract covering the dual extraction philosophy, confidence scoring rules, file map, heading rules, and cleanup semantics. This document is sophisticated and thoughtful. It is also written for AI agents, not human operators.

No user-facing README exists. A developer encountering tomd for the first time has no explanation of what the tool does, how to install it, what its approach is, or what its limitations are. The `main.py` docstring provides three CLI usage examples<sup>2</sup>, but these are discoverable only after reading the source.

The inversion is specific: the project has invested in documentation, but directed it at agent consumers rather than human operators. The `CLAUDE.md` represents genuine design thinking that would directly serve as the foundation for a README - the gap is not in the author's ability to document, but in the target audience of the existing documentation.

This compounds with the undocumented `convert_pdf` error semantics. When detailed docs omit failure-mode behavior and overview docs target agents, the tool's operational contract becomes tribal knowledge - viable for a single-user personal tool, but a barrier the moment a CI pipeline or a future-self six months from now needs to understand what the tool promises.

### 5.4 The Unpinned Dependency Gap

`requirements.txt` contains a single line: `pymupdf`.<sup>4</sup> No version pin. PyMuPDF has undergone API changes between major versions, and tomd's dual-extraction architecture depends on specific output structures from `page.get_text("dict")` and `page.get_text("rawdict")`.<sup>6</sup> A PyMuPDF major version upgrade could silently change the dict structure that the spatial extraction path relies on.

Without tests, a dependency upgrade that breaks the extraction path produces no signal until the output Markdown is manually inspected. Without CI, there is no version matrix that would expose incompatibilities across PyMuPDF releases. The unpinned dependency, absent tests, and absent CI form a compound where the tool's most critical external contract - the format of PyMuPDF's text extraction output - is defended by nothing (Rust API Guidelines, C-STABLE; OpenSSF Scorecard).

The tool is also not packaged for installation. No `pyproject.toml`, `setup.py`, or entry point declaration exists<sup>1</sup> - it must be run via `python tomd/main.py` from the parent directory. For the stated batch-processing goal, this fragile invocation path adds friction to pipeline integration.

---

## 6. Design Maturity

**Promising.** tomd's core architecture - dual-extraction with multi-signal confidence scoring, companion prompt files for selective LLM escalation, and pipeline-shaped physical modularity - represents genuine design intelligence that no competitor matches in the deterministic converter space. The API surface is maximally minimal (`convert_pdf` plus CLI), naming is consistent, cognitive load is low, and the single-dependency approach keeps the supply chain clean (Bloch 2006). Eighteen of thirty-eight diagnostic tests produced clean results, concentrated in the Legibility, Correctness of Use (excepting error signaling), and Architecture clusters.

The gap is operational. Error design, testing, CI, dependency pinning, packaging, and documentation form a compound deficit that prevents the algorithmic sophistication from translating into operational trust. Every compound dynamic identified in this Review traces back to infrastructure the project has not yet built - infrastructure the author has acknowledged as planned. The trajectory is sound: the hard problem (PDF structural analysis) is solved with care, and the remaining work (error types, tests, packaging, documentation) is conventional software engineering that does not require architectural redesign.

---

## 7. Audit Trail

**Sources consulted:** All 12 Python source files in `wg21-papers/tomd/`, `requirements.txt`, `CLAUDE.md`. Web research for domain context and competitive analysis.

**Cache status:** No prior cache. Domain brief and competitive map collected fresh 2026-04-14.

**Supplementary documents imported:** None.

**Findings challenged and outcomes:**

- 20 candidate findings from 38 tests
- 11 killed by Challenge: Test 11 (Python exception model; critical cleanup handled), Test 18 (sample outputs exist), Test 20 (no external importers), Test 23 (not claimed as extensible), Test 28 (requirements.txt handles install), Test 31 (subsumed by Test 30), Test 33 (no performance claims), Test 34 (expected for personal tool maturity), Test 36 (personal tool, no distribution), Test 37 (processes trusted WG21 papers), Test 38 (expected for personal tool)
- 9 survived: Tests 8, 10, 12, 16, 17, 24, 26, 30, 32
- 9 compound dynamics identified by Coupling Analysis; 3 killed by Coupling Challenge (generic truisms); 6 survived representing 4 distinct interaction mechanisms

**Prior reports imported:** None.

---

## 8. References

<sup>1</sup> `CLAUDE.md` - tomd architecture and design rules

<sup>2</sup> `main.py` - CLI entry point, usage documentation

<sup>3</sup> `lib/pdf/__init__.py` - pipeline implementation, `convert_pdf` function

<sup>4</sup> `requirements.txt` - dependency declaration

<sup>5</sup> `lib/pdf/types.py` - data model, constants, enums

<sup>6</sup> `lib/pdf/extract.py` - dual extraction implementation

---

Bloch, J. "How to Design a Good API and Why it Matters." *Companion to OOPSLA*, 2006.

Boost Contributor Checklist.

Cwalina, K. and Abrams, B. *Framework Design Guidelines.* Addison-Wesley, 2009.

OpenSSF Scorecard. Open Source Security Foundation.

Rust API Guidelines, C-STABLE. https://rust-lang.github.io/api-guidelines/

---

*April 2026 - Opus 4.6*
