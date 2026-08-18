# Claude Code Prompt: B16 — Rename German Test Function Names to English

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.

Sprint PTC-S5 (Housekeeping). Code-Review Rule 5 finding: ~165 test functions use
German identifiers. This is the single largest Q-Score impact (Rule 5: 59.4).

**Do NOT run `git commit` or `git push`** — Kim commits manually after verification.

---

## Task

Rename ALL `test_` functions with German names to English across all test files.
This is a mechanical rename — no logic, signatures, assertions, or docstrings
change.

## Rules

### What to rename
- Every `def test_...` function whose descriptive part (after the TC-ID prefix,
  if present) contains German words.

### TC-ID prefix pattern — PRESERVE
Many functions carry a test specification ID as prefix. This MUST be preserved
exactly. Pattern: `test_tc_<letter>_<number>_`

Examples:
- `test_tc_t_001_identischer_text_kein_delta`
  → `test_tc_t_001_identical_text_no_delta`
- `test_tc_x_001_nativen_text_aus_einseitigem_pdf_extrahieren`
  → `test_tc_x_001_extract_native_text_from_single_page_pdf`
- `test_tc_r_001_delta_markierung_im_einzel_report`
  → `test_tc_r_001_delta_marking_in_single_report`

### Functions WITHOUT TC-ID prefix
Translate the entire descriptive name:
- `test_isolierter_gedankenstrich_ergibt_kein_falsches_delta`
  → `test_isolated_dash_produces_no_false_delta`
- `test_batch_compare_erzeugt_einzel_report_pro_ok_paar_im_report_dir`
  → `test_batch_compare_generates_single_report_per_ok_pair_in_report_dir`

### What NOT to change
- **Docstrings** — remain in German, untouched.
- **Helper function names** (e.g., `_write_single_page_pdf`, `_build_synthetic_pages`)
  — already English, do not touch.
- **Variable names, assertions, comments** — do not touch.
- **Any non-test code** — do not touch `engine/`, `tools/`, `packaging/`,
  `src-tauri/`, `src/`.
- **Test logic** — zero behavioral changes.

### Translation quality
- Use natural, idiomatic English (not word-by-word translation).
- Keep names concise — similar length to the German original where possible.
- Use standard Python testing vocabulary: `no_delta`, `produces_delta`,
  `raises_error`, `returns_empty`, `is_ignored`, etc.

## Affected files

Process these files in order:

1. `tests/test_text_comparator.py` (~31 functions — largest file)
2. `tests/test_main.py` (~20 functions)
3. `tests/test_pdf_extractor.py` (~15 functions)
4. `tests/test_profile_loader.py` (~20 functions)
5. `tests/test_report_generator.py` (~25 functions)
6. `tests/test_batch_processor.py` (~20 functions)
7. `tests/test_ocr_extractor.py` (~10 functions)
8. `tests/test_region_filter.py` (~5 functions)
9. `tests/test_page_group_detector.py` (3 functions)
10. `tests/test_privacy_compliance.py` (2 functions)
11. `tests/test_comparison.py` (check for German names)
12. `tests/test_compare_region_comparator.py` (check for German names)

Also check for any other test files not in this list.

## Cross-references

After renaming, search the ENTIRE repository for any string references to the
old function names:
- `conftest.py` (parametrize IDs, fixture references)
- `pytest.ini` / `pyproject.toml` (test markers, filter expressions)
- Any `# see test_...` comments in engine code that reference test names

Update any such references to the new names.

## Verification

After ALL renames are complete:

1. Run `PYTHONPATH=. python -m pytest -q` — all 251 tests must pass.
2. Run `PYTHONPATH=. python -m pytest --collect-only -q | head -20` — confirm
   the first 20 collected test names are now English.
3. Report total number of functions renamed.

---

## General rules

- Do NOT run `git commit` or `git push`.
- Do NOT change any logic, assertions, fixtures, or docstrings.
- Do NOT rename helper functions, classes, or anything outside `def test_...`.
- Process all files in a single pass. If context becomes an issue, continue
  from the last completed file.
