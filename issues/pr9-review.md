# PR #9 Review Findings

Code-quality notes from the review of PR #9 (`fix/pdf-structure-classification`). None were blockers; tracked here so they surface when the surrounding code is touched next.

Each entry names the concern, a concrete example, root cause, and a fix direction (matching the format of `known-issues.md`).

---

## Sibling consolidation may demote legitimate subsection nesting

**Symptom:** `_validate_nesting` now treats consecutive headings that share a font size as siblings and clamps the second to `prev_level`. On papers that express heading depth through section numbering rather than typography (a common pattern for Markdown-origin PDFs), this flattens real nested subsections.

**Example sequence:**

```
## 2 Motivation        (font_size = 14, level = 2)
### 2.1 Background     (font_size = 12, level = 3)
#### 2.1.1 History     (font_size = 12, level = 4)
```

With `_SIBLING_FONT_TOL = 0.1`, `History` is compared to `Background`: same font size, so it is reclassified as a sibling (`level = 3`). The numbering depth (3 dotted parts → level 4) is ignored. Output becomes:

```
## 2 Motivation
### 2.1 Background
### 2.1.1 History        <-- should be ####
```

**Papers likely affected:** any WG21 paper where subsection headings at multiple depths share one font size. Not yet observed in the 52-paper batch as a regression, but the probability rises for papers that pass LOW-confidence heading classification (where section number is the only evidence).

**Root cause:** `lib/pdf/structure.py:_validate_nesting` (lines 912-921). The sibling check fires whenever `abs(sec.font_size - prev_font_size) <= _SIBLING_FONT_TOL` AND `sec.heading_level > prev_level`. It has no awareness of whether the section number supports the deeper level.

**Fix direction:** Let the section-number signal veto sibling clamping. When the incoming heading has a `has_number` match AND its `number_level == sec.heading_level == prev_level + 1`, allow the one-level descent through unchanged. Only clamp when the level would skip (`> prev_level + 1`) or when no numbering is present. In CLAUDE.md terms: dotted-decimal section numbering is higher-reliability than font-size agreement; font agreement should not override numbering agreement.

---

## `_SIBLING_FONT_TOL = 0.1` is very tight for real-world font sizes

**Symptom:** PDFs sometimes specify fractionally different font sizes for the same visual heading tier (e.g. `11.95` and `12.0`, or `14.04` and `14.0`). A tolerance of `0.1` will treat these as different tiers and skip sibling consolidation, reintroducing the cascade this fix was meant to prevent.

**Example:**

```
sec_a.font_size = 11.95
sec_b.font_size = 12.00
abs(12.00 - 11.95) = 0.05   # within tol, sibling
```

```
sec_a.font_size = 11.70
sec_b.font_size = 12.00
abs(12.00 - 11.70) = 0.30   # exceeds tol, NOT sibling
```

Fractions in the 0.1–0.5 range are most common in LaTeX-rendered PDFs and in scanned-then-OCR'd documents. Papers in the 52-doc batch did not happen to hit this, but the test coverage does not guard against it either.

**Root cause:** `_SIBLING_FONT_TOL = 0.1` in `lib/pdf/structure.py` is an absolute point-size tolerance with no relation to the heading size itself. At 12pt body text the tolerance is ~0.8% of the size; at 8pt captions it is ~1.3%. The constant was chosen without a documented rationale.

**Fix direction:** Either (a) widen the absolute tolerance to ~0.5 (covers typical fractional PDF size variance while still discriminating between real 10pt / 11pt / 12pt tiers), or (b) express it as a ratio: `abs(a - b) <= max(0.5, 0.02 * max(a, b))`. The ratio form is more defensible across font-size ranges.

---

## Local import of `Counter` inside `propagate_monospace`

**Symptom:** `lib/pdf/mono.py:195` adds `from collections import Counter` inside the body of `propagate_monospace`. Other modules in the project (e.g. `types.py`, `structure.py`, `cleanup.py`) import `Counter` at module scope. The inline import breaks the project's import-location consistency.

**Impact:** Cosmetic only. No measurable performance difference for a one-shot call per document, and no correctness risk.

**Root cause:** The import was likely added at the point of first use while iterating on the fix and never hoisted.

**Fix direction:** Move the import to the top of `mono.py` alongside `math` and `re`. Zero runtime impact, consistent with the rest of the codebase. Trivial to fold into the next mono.py edit.

---

## Commit 5 bundles two unrelated changes

**Symptom:** Commit `e61a787` ("Treat same-styled consecutive headings as siblings in nesting validation") contains two logically independent changes:

1. **Repetition demotion:** `_demote_repeated_low_confidence_numbers`, a new phase that demotes LOW-confidence headings whose `section_num` repeats ≥3 times.
2. **Sibling consolidation:** a new branch inside `_validate_nesting` that clamps runs of same-font-size headings to `prev_level`.

Either change is independently useful and could be reverted without the other. Bundling them reduces bisect-ability if a future regression traces to one of the two rules.

**Acknowledgement:** The PR description already flags this ("Includes two changes (should have been two commits)").

**Fix direction:** Split before merge via `git rebase -i e61a787` and `git reset HEAD~` + two `git commit -p` rounds. Optional — the description captures the distinction in prose, and the functions themselves are separately named and located.

---

## `_demote_repeated_low_confidence_numbers` leaves `confidence` at LOW on demoted paragraphs

**Symptom:** When a section is demoted from HEADING → PARAGRAPH, only `kind` and `heading_level` are updated. `confidence` remains at `Confidence.LOW`, the value it carried as a heading. Most PARAGRAPH sections elsewhere in the pipeline carry `Confidence.HIGH` (constructed by `_make_paragraph_section`).

**Example:**

```python
sec.kind        == SectionKind.HEADING
sec.confidence  == Confidence.LOW
sec.heading_level == 2

# after _demote_repeated_low_confidence_numbers:
sec.kind        == SectionKind.PARAGRAPH
sec.confidence  == Confidence.LOW          # stays LOW
sec.heading_level == 0
```

**Impact:** None currently observable. A grep for `sec.confidence ==` across `lib/` shows only heading-path consumers inspect confidence (the `HIGH → MEDIUM` downgrade in `_validate_nesting`), and `compare_extractions` has precedent for assigning `Confidence.LOW` to paragraphs (line 182). The emitter ignores `confidence` for PARAGRAPH sections.

**Root cause:** `lib/pdf/structure.py:_demote_repeated_low_confidence_numbers` only resets the two fields it knows the downstream classifier cares about. Not a bug today, but a future consumer that trusts `confidence` on PARAGRAPH sections would be surprised.

**Fix direction:** Either (a) reset `sec.confidence = Confidence.HIGH` on demotion to match the provenance of other paragraphs, (b) leave it as LOW and add a short comment stating that confidence is not meaningful for non-HEADING sections, or (c) drop the field entirely from `Section` for non-HEADING kinds. Option (a) is the least risky and aligns with the "most paragraphs are HIGH" default.
