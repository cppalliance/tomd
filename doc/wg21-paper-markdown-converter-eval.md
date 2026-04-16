# A Well-Scoped Conversion Workflow With a Failure-Handling Void

**A personal CLI tool that converts WG21 committee papers from HTML and PDF to Markdown, with strong operator documentation but no mechanism to detect, diagnose, or prevent silent document corruption.**

April 2026, by Vinnie Falco

---

## 1. Executive Summary

wg21-paper-markdown-converter is a thin Python orchestrator that fetches committee paper URLs and converts them to Markdown through two pipelines: HTML via Pandoc, PDF via a progressive fallback (docling, pdfplumber, OpenRouter vision). The tool ships a GitHub Actions workflow for batch operation and optional cross-repository publishing. Its scope is clear, its modules are sensibly separated, and its README is uncommonly thorough for a four-commit personal project.

The dominant finding is a failure-handling void. The progressive fallback architecture - the tool's central design decision - depends on classifying failures to choose the right recovery stage, but broad `except Exception` blocks erase failure type, and result.json discards diagnostic detail. When HEAD-based type detection fails silently, a PDF can enter the HTML pipeline and produce corrupted Markdown without any mechanism raising an alarm. No automated tests exist to guard against this or any other regression.

Against the competitive landscape, the tool occupies a genuine niche: no other open-source project combines batch URL fetching, committee-paper preprocessing, progressive PDF conversion, and CI-integrated publishing in one package. The architecture is sound for its purpose. The gaps cluster around operational observability, not core conversion quality.

The verdict is **Promising**: a sound core design with identifiable gaps - all addressable without redesign - that cluster in the failure path rather than the success path.

---

## 2. The Project

wg21-paper-markdown-converter<sup>1</sup> is a Python CLI tool authored by Daniel Li (CppDigest organization), consisting of six modules in a flat script layout with no installable package structure. The tool accepts a JSON list of document URLs, detects each URL's type via file extension and HEAD request, and routes to the appropriate converter. HTML documents pass through Pandoc's GFM writer with committee-specific preprocessing. PDF documents attempt conversion through three stages: docling (ML-based extraction), pdfplumber (rule-based extraction), and OpenRouter vision API (LLM-based OCR fallback).

The project includes a GitHub Actions workflow (`convert.yml`) triggered by `workflow_dispatch` that runs the converter, uploads artifacts, and optionally pushes successful conversions to a target repository via the GitHub REST API<sup>2</sup>. The repository has four commits, one contributor, zero stars, and one fork as of April 2026<sup>1</sup>. No LICENSE file is present. No automated tests exist, though `.gitignore` contains patterns for pytest and coverage tooling<sup>2</sup>.

---

## 3. The Domain

Converting standards-committee papers to Markdown serves a specific operational need: making dense technical documents reviewable in Git-based workflows where line-level diffs, pull request annotations, and plain-text search are the native tools. The domain imposes five stress points on any tool operating in it.

**Diff-stable output.** Markdown emitted for version control must stay stable across repeated runs and minor source edits so that PR diffs reflect real content changes, not converter noise. This elevates verification and consistency demands.

**Structural fidelity.** Committee papers mix prose, code blocks, tables, and nested lists where layout carries technical meaning. Flattening or reordering during conversion loses information that implementers and reviewers rely on.

**CI reproducibility.** A conversion pipeline integrated into repository automation must produce identical output from identical input across developer machines and headless runners, with pinned runtimes and declared system dependencies.

**Explicit failure visibility.** Normative and pre-normative text is audited for accidental edits. Silent omission or corruption during conversion is a known class of incident in document pipelines. The tool must report what it could not convert, not silently drop content.

**Heterogeneous upstreams.** WG21 paper corpora accumulate years of generator and stylesheet variation. A conversion tool must isolate parser and renderer logic so fixes for one upstream template do not break another.

---

## 4. The Landscape

No open-source tool occupies the exact niche of batch WG21 paper ingest-to-Markdown with CI publishing. The subject is a thin orchestrator that glues together established conversion engines, and its competitors are those engines themselves and adjacent tools.

- **Pandoc**<sup>3</sup> (Haskell, GPL-2.0, ~43k stars) is the universal markup converter and the subject's HTML conversion engine. It handles the heavy lifting; the subject adds committee-specific preprocessing and batch workflow automation.
- **Docling**<sup>4</sup> (Python, MIT, ~58k stars) is IBM's document parsing framework with unified intermediate representation. The subject uses it as first-try PDF extraction but does not leverage Docling's structured IR - conversion outputs are flat Markdown.
- **Marker**<sup>5</sup> (Python, GPL-3.0, ~34k stars) offers ML-powered PDF-to-Markdown with optional LLM assist. It covers a superset of the subject's PDF capabilities with higher adoption and more active maintenance, though it lacks URL fetching and CI workflow integration.
- **python-markdownify**<sup>6</sup> (Python, MIT, ~2.2k stars) and **Turndown**<sup>7</sup> (JavaScript, MIT, ~11k stars) are embeddable HTML-to-Markdown converters that do not require a Pandoc binary. Both are libraries, not workflow tools.
- **mpark/wg21**<sup>8</sup> (Makefile/Python/LaTeX, BSL-1.0, ~146 stars) is the closest WG21-specific peer but solves the inverse problem: authoring papers in Markdown and generating HTML/PDF output. It does not ingest published committee documents.

The subject's gaps relative to the field: no format breadth beyond HTML and PDF, no embeddable conversion without a Pandoc system dependency, no structured document intermediate representation, and no lightweight PDF path that avoids the ML stack. Its differentiators: progressive PDF fallback pipeline, committee-paper preprocessing, and a complete GitHub Actions ops package with cross-repository publishing.

---

## 5. Design Assessment

### 5.1 The Silent Misroute

URL type detection is the first decision point in the pipeline and it fails silently. The tool checks the URL path for `.pdf` and, when ambiguous, issues a HEAD request to examine `Content-Type`. If the HEAD request fails - the server blocks HEAD, times out, or returns an error - the URL is assumed to be HTML<sup>2</sup>. A PDF that arrives through this path enters the Pandoc-based HTML converter, which processes the binary content and produces garbled Markdown (Principle of Least Astonishment).

The corruption compounds in two directions. First, the broad `except Exception` in the progressive fallback treats the resulting parse failure identically to a legitimate conversion error (Abrahams 2001), so the fallback chain cannot distinguish "wrong pipeline" from "right pipeline, bad input." Second, result.json - the tool's only machine-readable output - records "failed" without capturing that the failure was a routing error, not a conversion error<sup>2</sup>. An operator reviewing CI output sees a generic failure where the actual problem was a misclassification five steps earlier.

For a personal tool where the author controls the input URLs, this is a latent risk rather than an active deficiency. It becomes relevant when the URL corpus expands beyond known-good sources - a committee server migration, a new paper host, or a change in server HEAD behavior.

### 5.2 Failure Information Lost in Translation

The progressive PDF fallback - docling, then pdfplumber, then OpenRouter - is the tool's most deliberate architectural decision. It acknowledges that no single converter handles all PDFs well and chains them in decreasing fidelity. The design is sound in concept. The execution strips the failure information the chain needs to function correctly.

Every stage wraps its work in a broad `except Exception` that reduces heterogeneous failures to a boolean<sup>2</sup>. A network timeout in docling, a parse error in pdfplumber, and a rate-limit response from OpenRouter all produce the same signal: `False`. The fallback fires on every failure type, including types where falling back is the wrong response (Abrahams 2001). A network outage should block the pipeline, not cascade through three converters that all fail for the same reason.

result.json compounds this by recording only status strings<sup>2</sup>. When a CI run produces three "failed" entries, the operator cannot determine from the structured output whether the failures were network errors, parsing failures, API rate limits, or pipeline misroutes. The diagnostic path is: download the workflow log, search for the URL, read the console output, infer the failure stage. For a personal workflow this is tolerable. For a tool that processes batches of committee papers in CI, it is the dominant friction point.

### 5.3 Conversion Without a Safety Net

No automated tests exist in the repository<sup>2</sup>. The `.gitignore` anticipates pytest and coverage tooling, suggesting testing was intended but not implemented. The CI workflow runs the converter against user-provided URLs but performs no assertions on output quality, structural preservation, or regression detection<sup>9</sup> - it is a deployment mechanism, not a verification pipeline.

The absence of tests amplifies every other finding. Silent misrouting (Section 5.1) persists because no test asserts that a PDF URL produces PDF-derived Markdown rather than HTML-derived garbage. The opaque failure chain (Section 5.2) evolves without constraint because no test locks down error shape or content in result.json. The heavy docling/torch dependency stack (Pike 2015) can drift across versions without a failing test to signal that conversion output has changed. And the dead BeautifulSoup4 entry in requirements.txt - listed but never imported in any code path<sup>2</sup> - persists because there is no mechanism to detect unused dependencies.

For a four-commit personal tool, absent tests are common and low-urgency. The domain context elevates them: committee-paper conversion demands diff-stable output across tool updates, and untested code cannot guarantee stability.

---

## 6. Design Maturity

**Promising.** The core architecture - a modular orchestrator routing URLs to format-specific converters with a progressive fallback for PDFs - is sound. The module separation (orchestrator, HTML converter, PDF converter, naming utility, push script) follows the shape of the problem. The README is unusually thorough for a project at this stage. The compound dynamics cluster in the failure-handling path, not the success path: when inputs are well-formed and servers cooperate, the tool converts documents correctly.

The gaps are addressable without redesign. Typed exceptions or an error-result type in the fallback chain would break the homogeneous failure surface. A structured error field in result.json (error type, stage, message) would make CI failures diagnosable. A URL-type validation step that refuses ambiguous classifications rather than defaulting to HTML would close the misroute path. A small pytest suite with fixture inputs (known-good HTML, known-good PDF, known-bad URL) would provide the safety net the tool currently lacks.

The project is at the stage where its architecture has outrun its engineering guardrails. The progressive fallback is a design that demands failure classification, but the implementation has not yet caught up with the design's requirements.

---

## 7. Audit Trail

**Subject:** https://github.com/CppDigest/wg21-paper-markdown-converter (cloned at HEAD, April 14, 2026)

**Supplementary imports:** None provided.

**Governing specification:** None identified.

**Cache status:** First run. No prior cache or report existed for this subject.

**Reconnaissance:** Full source read of all 6 Python modules, requirements.txt, .env.example, .gitignore, README.md, and .github/workflows/convert.yml.

**Domain brief:** 5 stress points identified. Elevated tests: 1, 5-12, 16-17, 19, 21, 23, 25-28, 30-32, 34-35, 38.

**Competitive map:** 7 competitors evaluated (Pandoc, Docling, Marker, jzillmann/pdf-to-markdown, Turndown, python-markdownify, mpark/wg21).

**User assumptions resolved:** Adoption posture = personal/internal CI utility. License absence = not actionable.

**Diagnosis:** 38 tests run. 5 findings produced (Tests 8, 10, 11, 25, 30). 33 clean results.

**Challenge outcomes:**
- 5 findings survived all 8 challenge tests
- 3 candidate findings killed: Test 29 (import cost, Challenge Tests 3+7 - common Python pattern), Test 31 (test depth, precondition not met), Test 32 (CI quality, Challenge Test 2 - deployment workflow, not claimed as verification)

**Coupling analysis:** 7 compound dynamics proposed. 6 survived coupling challenge. 1 killed (Fallback opacity blocks targeted tests - Challenge Test 1, constituents co-present but not genuinely amplifying).

**Surviving compounds:**
- Homogeneous failure surface (Tests 10+11)
- Silent wrong-branch failure masking (Tests 8+11)
- End-user surprise meets ops blind spot (Tests 8+10)
- Unobservable regression multiplier (Tests 10+30)
- Silent corruption without a net (Tests 8+30)
- Heavy stack, zero harness (Tests 25+30)

---

## 8. References

1. CppDigest/wg21-paper-markdown-converter. GitHub repository. https://github.com/CppDigest/wg21-paper-markdown-converter
2. Source code inspection: url2md.py, html_converter.py, pdf_converter.py, push_via_github_api.py, output_naming.py, requirements.txt, .gitignore (cloned April 14, 2026)
3. jgm/pandoc. GitHub repository. https://github.com/jgm/pandoc
4. docling-project/docling. GitHub repository. https://github.com/docling-project/docling
5. datalab-to/marker. GitHub repository. https://github.com/datalab-to/marker
6. matthewwithanm/python-markdownify. GitHub repository. https://github.com/matthewwithanm/python-markdownify
7. domchristie/turndown. GitHub repository. https://github.com/domchristie/turndown
8. mpark/wg21. GitHub repository. https://github.com/mpark/wg21
9. .github/workflows/convert.yml (cloned April 14, 2026)

---

Abrahams, D. "Exception Safety in Generic Components." In *Generic Programming*, Lecture Notes in Computer Science, vol. 1766, Springer, 2001.

Pike, R. "Go Proverbs." Gopherfest, November 2015.

---

*April 2026 - Opus 4.6*
