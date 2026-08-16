# Claude Code Prompt: table_regions — Character-Multiset Comparison

## Context

PaperTrail Compare, local desktop PDF comparison app (Tauri + React/TS + Python
engine). 220 tests green. The `table_regions` feature (whitespace-free condition
check + whitespace-free string comparison) is committed and working.

**Do NOT commit** — Kim commits manually after pytest verification and a manual
GUI check.

**Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.**

---

## Problem (root cause verified against real customer documents)

Diagnosis on the real reference/candidate pair (2026-08-16) proved:

1. The whitespace-free **condition check works correctly on BOTH sides**
   (matches on the letter pages carrying the footer). The blocks ARE separated.
   The earlier assumption "condition does not activate" is refuted.

2. The whitespace-free **string comparison** in `compare_table_region`
   (`ref_nows == cnd_nows`) produces a FALSE delta per region, because the two
   print systems deliver the same footer with different block geometry:
   - Reference: one wide block **per line** spanning all 4 footer columns
     (row-major concatenation order)
   - Candidate: one narrow block **per column** (column-major concatenation
     order)

   Both region texts contain the exact same 659 characters — in completely
   different order. String equality can never hold here.

3. Verified fix: a **character multiset** comparison
   (`Counter(ref_nows) == Counter(cnd_nows)`) is `True` on the real pair for
   the identical footers, and it precisely detected a genuine content
   difference in a control experiment (an extra body-text block produced
   exactly its own characters as the multiset difference).

Design history for the docstring: the original word-Counter comparison failed
on Type3 syllable fragmentation (unreliable word boundaries); the
whitespace-free string comparison that replaced it fails on divergent block
order. The character multiset is order-independent AND whitespace-independent
— the combination this document class requires.

---

## Fix (single, small change)

### File: `engine/table_region_comparator.py`, function `compare_table_region`

Replace the equality check

```python
if ref_nows == cnd_nows:
    return []
```

with a character-multiset check:

```python
from collections import Counter  # module-level import

if Counter(ref_nows) == Counter(cnd_nows):
    return []
```

Everything else stays byte-identical:
- Still exactly **one** Delta per region on mismatch, with the readable
  `*_display` texts and `_NO_POSITION` (= 0) as position.
- `check_table_region_condition` (pdf_extractor) — UNCHANGED. The condition is
  a substring match and needs contiguity; it works on both block layouts
  because the condition phrase sits inside a single block on each side.
- `merge_table_region_comparison` — UNCHANGED.
- Signatures — UNCHANGED.

### Docstring updates

Update the module docstring of `table_region_comparator.py` and the
`compare_table_region` docstring (German, matching existing style):
- Explain WHY character multiset: block order diverges between formatters
  (row-major wide blocks per line vs. column-major blocks per column), so
  neither sequential diff, nor word Counter (Type3 fragmentation), nor string
  equality (order) works — only an order- and whitespace-independent
  character multiset covers this document class.
- Document the known limitation honestly: two texts that are character
  anagrams of each other would compare equal. For the footer use case this is
  practically irrelevant (any changed digit, amount, or missing word changes
  the multiset), but it must be stated.

---

## Tests (TDD: write/adjust tests first, watch them fail, then implement)

### File: `tests/test_table_region_comparator.py`

1. **Invert** `test_andere_wortreihenfolge_gleiche_woerter_liefert_deltas`:
   word/segment reordering with identical characters must now yield **NO**
   delta. Rename to reflect the new intent, e.g.
   `test_andere_blockreihenfolge_gleiche_zeichen_liefert_keine_deltas`, and
   rewrite the docstring: this is now the CORE behavior (row-major vs.
   column-major block order on real mainframe footers), referencing this
   prompt file. The previous behavior (reorder = delta) was intentional at the
   time but is refuted by the real documents.

2. **New test — real-world shape:** ref text simulating row-major line
   concatenation vs. cnd text simulating column-major column concatenation of
   the SAME footer content (same characters, different order) → no delta.
   Keep it small (2×2 grid of short words is enough).

3. **New test — genuine change detected:** same setup as (2), but one digit
   changed in the candidate (e.g. a phone number) → exactly ONE delta,
   `ref_text`/`cnd_text` carry the readable display versions.

4. **Review remaining tests:** the existing identity/empty/one-side-empty
   tests should pass unchanged (empty vs. non-empty multisets differ). Adjust
   only where the expectation text mentions "string comparison" semantics.

### Integration tests

`tests/test_main.py` / `tests/test_batch_processor.py` (TC-TR-001/002): the
key assertions must still hold —
- TC-TR-001 (same content, different blocks): `has_delta is False`
- TC-TR-002 (genuinely changed phone number): `has_delta is True`, exactly one
  delta containing both numbers.
These should pass without fixture changes (a changed digit changes the
multiset). If anything fails, STOP and report before touching fixtures.

---

## Workflow

Single step (the change is small): adjust/add tests, watch them fail, apply the
fix, run the FULL pytest suite, report results. Do NOT commit. WAIT for Kim's
confirmation after reporting.

## General rules

- Do NOT commit.
- Do NOT modify Rust or TypeScript code.
- Do NOT touch `check_table_region_condition`, `separate_table_region_blocks`,
  `merge_table_region_comparison`, or any extraction code.
- Real customer PDFs must never become test fixtures — synthetic strings /
  ReportLab fixtures only.
