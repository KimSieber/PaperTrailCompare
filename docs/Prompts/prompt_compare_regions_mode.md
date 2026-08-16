# Claude Code Prompt: compare_regions — Rename, Per-Region Mode, Delta Sorting

## Context

PaperTrail Compare, local desktop PDF comparison app (Tauri + React/TS + Python
engine). 222 tests green. The `table_regions` feature works: regions matching a
`condition` are separated from the page text and compared as a whole via
character multiset (order- and whitespace-independent).

**Do NOT commit** — Kim commits manually after pytest + a manual GUI check.
**Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.**

---

## Problem (verified on real customer documents)

The character-multiset comparison was built for ONE specific problem: the page
footer is emitted as row-major wide blocks in the reference but column-major
narrow blocks in the candidate, so no ordered comparison can work there.

Applying the same treatment to ALL regions is too coarse. Example: the
sender/info block at the top right ("Es betreut Sie / Es schreibt Ihnen /
date"). Its blocks ARE recognised consistently on both sides — the only reason
it needs a region at all is that the sequential full-page pass interleaves it
with the recipient address on the left. For such a region the multiset produces
ONE delta containing the entire block text, which:
- hides the actual differences (`Tel.:` → `Tel.`, date `15.06.2026` →
  `03.07.2026`) inside one long string,
- makes the report highlight the whole block instead of the changed words
  (`report_generator._find_delta_rects` locates deltas via `page.search_for()`
  on the delta text — a long text highlights everything).

So the comparison strategy must be selectable per region.

**Second, independent bug found in the same run:** region deltas are appended
AFTER all sequential deltas, so a page-1 region delta appears at the very end
of the delta list, behind page-17 deltas. Testers do not find them. The delta
list must be sorted by page.

---

## Task 1 — Rename `table_regions` → `compare_regions`

The name is obsolete: these regions are no longer about tables, but about
"compare this area in isolation from the rest of the page". Rename throughout
the codebase:

- Profile JSON key: `table_regions` → `compare_regions`
- Dataclass `TableRegion` → `CompareRegion` (profile_loader)
- All functions/variables/parameters carrying the `table_region` name, e.g.:
  - `check_table_region_condition` → `check_compare_region_condition`
  - `separate_table_region_blocks` → `separate_compare_region_blocks`
  - `merge_table_region_comparison` → `merge_compare_region_comparison`
  - `table_region_texts` → `compare_region_texts`
  - module `engine/table_region_comparator.py` →
    `engine/compare_region_comparator.py`
  - test file names/test function names accordingly
- Report labels and German user-facing texts: use "Vergleichsbereiche"
  (instead of any "Tabellenbereiche"/"table region" wording).

**No backwards compatibility**: the old key `table_regions` must NOT be
accepted. If a profile still uses it, the loader raises a clear German
validation error naming the new key, so Kim notices immediately.

Kim updates his own profiles manually; test fixtures/profiles in the repo must
be updated by you.

---

## Task 2 — Per-region `mode` parameter

New optional field per region: `"mode": "sequential" | "unordered"`.

- **Default when absent: `"sequential"`.**
- `"unordered"` = current behaviour (character multiset over the whole region,
  exactly one delta per region on mismatch, `_NO_POSITION`).
- `"sequential"` = NEW: the region's text is compared with the normal
  sequential comparison, in isolation from the rest of the page.

Validation: unknown values raise a clear German error naming the two allowed
values.

### Behaviour of `"sequential"`

1. Blocks matching the region (and its `condition`) are separated from the page
   text exactly as today — that part is unchanged and is what prevents the
   interleaving with surrounding text.
2. Instead of building the `(text_nows, text_display)` pair for a multiset
   comparison, the region's display text is kept per page and per region.
3. Reference and candidate region texts of the SAME page and the SAME region
   index are then compared using the existing sequential comparison from
   `engine/text_comparator.py` (the same code path the normal document
   comparison uses).
4. The resulting deltas are re-mapped to the real page number of that page.
5. Result: `Tel.:` → `Tel.`, `Fax:` → `Fax` and the date each become their own
   small delta with their own short texts — which also makes the report
   highlighting precise again.

### Comparison parameters

The sequential region comparison uses the SAME profile parameters as the main
comparison (`case_sensitive`, `compare_mode`, `normalize_whitespace`,
`merge_hyphenation`, `normalize_orphan_hyphens`, …).

IMPORTANT for future extensibility: thread these parameters through ONE single
place (e.g. one helper that builds the comparison settings for a region), so
that per-region overrides can later be added at exactly that spot without
restructuring. Do NOT implement per-region overrides now.

### One-sided condition match

While you are in this code: if a region's `condition` matches on ONE side only,
the blocks are separated on that side and not on the other, which silently
produces large asymmetric deltas. Do not change the behaviour in this prompt,
but add a `# TODO:` comment at the relevant place describing the risk, so it is
visible for the planned follow-up task.

---

## Task 3 — Sort delta list by page

Deltas from region comparisons are currently appended after all sequential
deltas. Sort the final delta list of a comparison **stably by page number
only** (`sorted(deltas, key=lambda d: d.page)` — Python's sort is stable).

Deliberately do NOT use `position` as a secondary key: region-internal
positions have a different frame of reference than document positions, and with
columns, tables and landscape pages the reading order does not match the
viewer's visual impression anyway. Stable sorting by page keeps the natural
generation order within a page, which is the most robust option.

Apply this at the point where the complete delta list is assembled (single
comparison AND batch path), so report, JSON output and GUI all see the sorted
list.

---

## Tests (TDD: write/adjust tests first, watch them fail, then implement)

1. **Rename**: adjust all existing tests to the new names/keys. They must stay
   green with unchanged semantics (mode `"unordered"` explicitly set where a
   test relies on multiset behaviour).
2. **Loader**: `compare_regions` parsed correctly incl. `mode`; default is
   `"sequential"` when the field is absent; invalid `mode` value raises a
   German error; old key `table_regions` raises a clear German error.
3. **Sequential mode (core test, models the real document)**: a region whose
   reference text is `"Tel.: 0611 178-49830 Wiesbaden, 15.06.2026"` and whose
   candidate text is `"Tel. 0611 178-49830 Wiesbaden, 03.07.2026"` yields
   SEVERAL small deltas (`Tel.:`/`Tel.` and the two dates) rather than one
   large delta — assert the delta count is > 1 and that no delta text contains
   the whole block.
4. **Unordered mode unchanged**: existing multiset tests pass with
   `mode: "unordered"` (row-major vs column-major → no delta; changed digit →
   exactly one delta).
5. **Isolation**: a page where the region text would otherwise interleave with
   surrounding text produces deltas only for the genuinely changed region
   content, not for the neighbouring text.
6. **Sorting**: a comparison where a region delta belongs to page 1 while
   sequential deltas exist up to page 5 → the page-1 region delta appears
   before the page-2 deltas in the final list. Also assert stability: two
   deltas on the same page keep their relative generation order.
7. **Integration** (`test_main.py`, `test_batch_processor.py`): the existing
   TC-TR-001/002 cases must keep working under the new names; add one case
   asserting the JSON output list is page-sorted.

Real customer PDFs must never become test fixtures — synthetic strings /
ReportLab fixtures only.

---

## Workflow

Work in TWO steps, then STOP and report:

- **Step 1**: Task 1 (rename, mechanical, no behaviour change) + Task 3
  (sorting). Run the full suite, report. WAIT for Kim's confirmation.
- **Step 2**: Task 2 (mode parameter incl. sequential comparison). Run the full
  suite, report. WAIT for Kim's confirmation.

Do NOT commit at any point. If a test fails in a way that suggests the design
above is wrong for the real code structure, STOP and report instead of
improvising.
