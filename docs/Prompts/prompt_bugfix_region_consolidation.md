# Claude Code Prompt: Bug-Fix — Region Logic Consolidation

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.
Critical requirement: **everything runs exclusively locally** — no cloud, no server,
no network connections during processing.

All changes follow the project principles: TDD (test first), synthetic fixture PDFs
(never customer documents), `pytest` must be green before any commit.

Current state: 166+ tests green, Sprint PTC-2 completed.

**Do NOT commit** — Kim commits manually after verification.

---

## Bug A — Consolidate `_region_applies_to_page` Duplicate

### Problem

`engine/ocr_extractor.py` contains TWO implementations of `_region_applies_to_page`:

1. **Local copy (~line 56):** A duck-typed standalone function that duplicates the
   logic from `pdf_extractor._region_applies_to_page`. The docstring explicitly says
   "absichtlich ohne Import" — but this rationale is outdated since the same file
   already imports from `pdf_extractor` elsewhere.

2. **Import (~line 160):** Inside `extract_pages_with_ocr_fallback`, the function
   imports `_region_applies_to_page` from `engine.pdf_extractor` and uses it there.

Having two copies is a maintenance risk: if the logic changes (e.g., new region
types for `table_regions` in a future sprint), only one copy might get updated.

### Fix

1. **Investigate first:** Read `engine/ocr_extractor.py` fully. Identify every
   call site that uses the local `_region_applies_to_page` and every call site
   that imports it from `pdf_extractor`. List them before making changes.

2. **Remove the local copy.** Replace all usages of the local function with an
   import from `engine.pdf_extractor`. The import should be at module level if
   there is no circular-import risk, otherwise keep it as a local import inside
   the function that needs it (the existing pattern).

3. **Check for type compatibility:** The local copy uses duck-typing (accepts any
   object with `.page` and `.page_from`). The `pdf_extractor` version expects
   `Region` objects. Verify that the callers in `ocr_extractor.py` pass objects
   compatible with the `pdf_extractor` version. If they pass `ExcludeRegion`
   objects (from `profile_loader`), check whether `Region` and `ExcludeRegion`
   share the same `.page` / `.page_from` interface. If not, the callers in
   `ocr_extractor.py` already convert to `Region` — confirm this.

4. **Run `pytest`** — all existing tests must remain green. No new tests needed
   for this bug (it's pure refactoring, behavior is unchanged).

---

## Bug B — Wire `extract_pages_excluding_regions` into Production Pipeline

### Problem

`engine/region_filter.py` contains `extract_pages_excluding_regions()`, which
applies coordinate-based exclude regions to PDF text extraction. However, this
function is **not called** from the production pipeline:

- `engine/__main__.py` (CLI single comparison) does NOT call it.
- `engine/batch_processor.py` (batch comparison) does NOT call it.

Both use `extract_pages_for_profile()` from `pdf_extractor.py` as their entry
point. That function handles regions via `filter_blocks_by_regions()` internally.

### Investigation required

Before making any changes, answer these questions:

1. **Is `extract_pages_excluding_regions` redundant?** Compare what
   `extract_pages_for_profile` does with regions vs. what
   `extract_pages_excluding_regions` does. Check whether
   `extract_pages_excluding_regions` offers additional functionality
   (e.g., `split_wide_blocks` integration) that `extract_pages_for_profile`
   lacks.

2. **Do the existing wiring tests pass?** Run:
   - `test_exclude_regions_wirkt_ueber_extract_pages_for_profile_tc_e_001`
   - `test_exclude_regions_gilt_nur_fuer_definierte_seite_tc_e_002`
   
   If both pass, the production pipeline already handles `exclude_regions`
   correctly through `extract_pages_for_profile`.

3. **Is `extract_pages_excluding_regions` called from anywhere at all?**
   Search for all import/call sites. If it is only called from its own
   unit tests (`test_region_filter.py`), it may be dead production code
   that is tested in isolation but never used.

### Decision tree

- **If `extract_pages_for_profile` already handles all region logic correctly
  AND the wiring tests pass:** The bug is "won't fix" — document in a code
  comment in `region_filter.py` that `extract_pages_excluding_regions` is a
  lower-level utility tested directly but called indirectly through
  `filter_blocks_by_regions` in the production path. Add a brief note explaining
  the relationship.

- **If `extract_pages_excluding_regions` has functionality NOT covered by the
  production path** (e.g., `split_wide_blocks` is integrated there but not in
  `extract_pages_for_profile`): Wire it in. The exact integration point depends
  on what's missing — report your findings and proposed fix BEFORE implementing.
  Do NOT change the pipeline without confirming the approach.

### Tests

- Run the full test suite after any changes.
- If you add code comments only (documentation fix), no new tests needed.
- If you wire new functionality, add a test that proves the wiring works
  through the production entry point (`extract_pages_for_profile`), not just
  through the direct function call.

---

## General Rules

- **Do NOT commit.** Kim commits manually after pytest verification.
- **Pause after each bug fix** and report what you did, what changed, and
  the pytest result. Do not proceed to the next bug without confirmation.
- **Do not modify any test fixtures** (PDFs in `tests/fixtures/`).
- **Do not touch GUI code** (React/TypeScript/Tauri).
- Run `pytest` from the project root after each change.
