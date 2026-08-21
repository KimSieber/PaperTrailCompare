# Claude Code Prompt: H21 — Remove Dead Code `extract_pages_excluding_regions`

## Context

PaperTrail Compare, Sprint PTC-S5 (Housekeeping). 251 tests green.

**Do NOT run `git commit` or `git push`** — Kim commits manually after verification.

---

## Problem

`engine/region_filter.py` contains `extract_pages_excluding_regions()`, which is
not called from any production code path. CLI and Batch both use
`pdf_extractor.extract_pages_for_profile()` exclusively. The function was kept
as a "testable building block" but this rationale is circular — it exists only
to be tested.

## Fix

### Step 1 — Verify no production caller exists

Search the entire codebase for imports or calls of `extract_pages_excluding_regions`.
Expected: only `test_region_filter.py` and the `__all__` list in `region_filter.py`
reference it. If ANY production code (`engine/`, `packaging/`, `tools/`) calls it,
STOP and report — do not remove.

### Step 2 — Remove the function

In `engine/region_filter.py`:

1. Remove the `extract_pages_excluding_regions()` function entirely.
2. Remove it from the `__all__` list.
3. Remove any imports that become unused after the removal (e.g., `pymupdf`,
   `get_text_blocks`, `join_block_text`, `sort_blocks_columns`,
   `split_wide_blocks` — check each one). Keep imports that are still used
   by `regions_from_profile()` or the `Region` re-export.
4. Update the module docstring to reflect that the file now provides the
   `Region` re-export and `regions_from_profile()` only.

### Step 3 — Remove the tests

In `tests/test_region_filter.py`, remove all test functions that test
`extract_pages_excluding_regions()`. Keep any tests that test
`regions_from_profile()` or `Region` if they exist.

If `test_region_filter.py` becomes empty after removal, delete the file entirely.

### Step 4 — Verify

1. Run `PYTHONPATH=. python -m pytest -q` — all remaining tests must pass.
2. Report how many tests were removed and the new total.

---

## Rules

- Do NOT run `git commit` or `git push`.
- Do NOT remove `Region` re-export or `regions_from_profile()`.
- Do NOT modify any other engine, test, or frontend code beyond what is
  specified above.
