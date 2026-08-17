# Code Review Report

**Project:** PaperTrail Compare  
**Scope:** Repository root (engine/, tests/, tools/, packaging/, src/, src-tauri/)  
**Date:** 2026-08-09  
**Mode:** Snapshot  
**Instruction version:** 1.0  
**Completeness:** partial — Five frontend view/layout files excluded from detailed review by agreement (SingleComparisonView.tsx, BatchView.tsx, Sidebar.tsx, MainPanel.tsx, PlaceholderPanel.tsx). Line numbers are from metrics.json where available; otherwise approximate from project knowledge snippets. Findings in the excluded files may exist but are not counted.

## 1. Scope

| Metric | Value |
|---|---|
| Files reviewed | 47 (42 detailed, 5 excluded from findings) |
| Logical LoC | 6 166 |
| KLoC | 6.166 |
| Functions | 355 |
| Declarations | 419 |
| Languages | Python (29 files / 5 195 LoC), TypeScript (17 / 934), JavaScript (1 / 37) |
| Excluded paths | `vendor/`, `node_modules/`, `.git/`, `build/`, `dist/`, `out/`, `__pycache__/`, `.venv/`, `*.lock`, `*.min.js`, `tests/fixtures/` (generated PDFs) |

**Assumptions**

- `tests/fixtures/` content (generated PDFs and README.md files) is excluded as machine-generated test data, not first-party source.
- `tools/diag_deltas.py` and sibling tool scripts are treated as first-party development/diagnostic code, not third-party.
- `.gitattributes` is a configuration file, not source code; it is excluded from file header and documentation rules but included in encoding checks.
- German test function names are a deliberate project convention documented in CLAUDE.md ("Discussion and design in German"). They are still counted as naming violations per the rule's "English throughout" requirement, but flagged as an architectural decision rather than accidental non-compliance.
- `conftest.py` at root level (0 LoC per metrics.json) is assumed to be an empty placeholder; it is counted as a file but contributes no findings beyond Rule 7.
- Rust code in `src-tauri/src/lib.rs` is reviewed as first-party code; the Tauri framework itself is excluded.

## 2. Score

| # | Rule | Type | F | N / d_max | Score | Weight | Weighted |
|---|---|---|---|---|---|---|---|
| 1 | Dead code | B | 2 | 5 / KLoC | 93.5 | 2 | 187.1 |
| 2 | Redundancy | B | 1 | 3 / KLoC | 94.6 | 2 | 189.2 |
| 3 | Single responsibility | A | 8 | 355 | 97.7 | 3 | 293.2 |
| 4 | I/O separation | A | 5 | 355 | 98.6 | 3 | 295.8 |
| 5 | Naming conventions | A | 170 | 419 | 59.4 | 2 | 118.8 |
| 6 | Function documentation | A | 25 | 355 | 93.0 | 3 | 278.9 |
| 7 | File header | A | 0 | 47 | 100.0 | 2 | 200.0 |
| 8 | Why-comments | B | 1 | 4 / KLoC | 95.9 | 1 | 95.9 |
| 9 | Configuration | B | 4 | 10 / KLoC | 93.5 | 3 | 280.6 |
| 10 | Secrets | C | 0 | — | PASS | gate | — |
| 11 | Error handling | A | 2 | 20 | 90.0 | 4 | 360.0 |
| 12 | Input validation | A | 2 | 10 | 80.0 | 4 | 320.0 |
| 13 | Resource release | A | 2 | 12 | 83.3 | 4 | 333.3 |
| 14 | Security | C + A | 0 | 0 | PASS / n/a | 4 | n/a |
| 15 | Logging | B | 4 | 5 / KLoC | 87.0 | 1 | 87.0 |
| 16 | Critical-path tests | A | 2 | 18 | 88.9 | 3 | 266.7 |
| 17 | Dependencies | B | 0 | 2 | 100.0 | 1 | 100.0 |
| 18 | Encoding | A | 0 | 47 | 100.0 | 1 | 100.0 |

**Gates**

| # | Rule | Result | Findings |
|---|---|---|---|
| 10 | Secrets | PASS | No credentials, API keys, or key material in versioned files or visible history. Application is fully offline by design. |
| 14 | Injection | PASS | No database access, no string-concatenated SQL, no shell command concatenation. Tauri sidecar uses argument array (no shell interpolation). `html.escape()` used for report table cells. |

**Composite index**

```
Q = Σ weighted / Σ weights = 3506.5 / 39 = 89.9
```

Rule 14 ratio portion is n/a (N = 0 endpoints; desktop application with no externally reachable handlers). Weight 4 excluded from denominator: Σ weights = 43 − 4 = 39.

**Q = 89.9 — green**

## 3. Profile

| # | Rule | Score |
|---|---|---|
| 1 | Dead code | 93.5 |
| 2 | Redundancy | 94.6 |
| 3 | Single responsibility | 97.7 |
| 4 | I/O separation | 98.6 |
| 5 | Naming conventions | **59.4** |
| 6 | Function documentation | 93.0 |
| 7 | File header | 100.0 |
| 8 | Why-comments | 95.9 |
| 9 | Configuration | 93.5 |
| 10 | Secrets | PASS |
| 11 | Error handling | 90.0 |
| 12 | Input validation | 80.0 |
| 13 | Resource release | 83.3 |
| 14 | Security | PASS / n/a |
| 15 | Logging | 87.0 |
| 16 | Critical-path tests | 88.9 |
| 17 | Dependencies | 100.0 |
| 18 | Encoding | 100.0 |

**Three weakest rules**

1. **Rule 5 — Naming conventions (59.4):** ~165 test function names use German identifiers (e.g. `test_tc_t_009_ocr_wort_trennfehler_wird_bei_normalize_whitespace_ignoriert`). This is a deliberate project convention documented in CLAUDE.md but violates the rule's "English throughout" requirement. Additionally, five boolean parameters/fields lack the `is`/`has`/`should` prefix (`normalize_whitespace`, `case_sensitive`, `enabled`, `checking`, `ocr_was_used`). This single rule costs Q approximately 2 points.

2. **Rule 12 — Input validation (80.0):** `extract_pages()` and `extract_text_via_ocr()` accept file paths from external callers without upfront existence/readability checks. PyMuPDF raises an opaque `RuntimeError` on invalid paths instead of a clear, context-carrying error message.

3. **Rule 13 — Resource release (83.3):** `split_batch_pdf()` and `generate_report()` open PyMuPDF document handles without try/finally or context managers. An exception between open and close leaks up to four handles in the report generator.

## 4. Findings

### Rule 1 — Dead code (2 findings)

| File | Line | Category | Finding |
|---|---|---|---|
| src-tauri/src/lib.rs | ~10 | Rule 1 | `greet()` is the Tauri template function; no caller in the application. Remove it. |
| engine/profile_loader.py | ~130 | Rule 1 | `apply_overrides()` is implemented and tested but never called from any production code path (`__main__.py`, `batch_processor.py`). Same unwired pattern as the previously found `region_filter` bug. |

### Rule 2 — Redundancy (1 finding)

| File | Line | Category | Finding |
|---|---|---|---|
| engine/batch_processor.py | ~80 | Rule 2 | `_compare_pair()` duplicates the extraction→compare→report sequence from `__main__.py::_run_compare()` (profile field unpacking, `extract_pages_for_profile` calls with role, `compare()` call with identical parameter assembly, warning iteration, `generate_report` call). Extract a shared `run_single_comparison()` function. |

### Rule 3 — Single responsibility (8 findings)

| File | Line | Category | Finding |
|---|---|---|---|
| engine/__main__.py | ~35 | Rule 3 | `_run_compare()` handles profile loading, PDF extraction, text comparison, report generation, JSON serialization, and human-readable summary output. Split into orchestration and formatting. |
| engine/__main__.py | ~95 | Rule 3 | `_run_batch()` handles profile loading, progress callback setup, batch execution, timing, report generation, and JSON output. Same pattern as `_run_compare`. |
| engine/profile_loader.py | ~75 | Rule 3 | `load_profile()` reads the file, parses JSON, validates top-level fields, constructs `ExcludeRegion` objects, constructs `PageGroupPattern` objects, validates OCR config, and assembles the `Profile`. At ~100 logical lines, it exceeds the 50-line guide value. Extract validation helpers. |
| engine/report_generator.py | — | Rule 3 | `_build_summary_page_pdf_bytes()` builds the entire page-1 layout (badge, KPI tiles, progress bar, metadata table, region info) in a single function. Likely >80 lines. |
| engine/batch_processor.py | ~80 | Rule 3 | `_compare_pair()` mixes file-existence validation, profile field unpacking, PDF extraction, text comparison, report generation, and result assembly. |
| tools/diag_deltas.py | ~878 | Rule 3 | `main()` is a large dispatcher handling >10 sub-modes via sequential `if` branches. |
| tools/diag_deltas.py | ~599 | Rule 3 | `_inspect_rawdict()` produces five analysis sections (rawdict chars, get_text comparison, space counting, bbox analysis, TEXT_INHIBIT_SPACES cross-check) in one function. |
| tools/diag_deltas.py | ~846 | Rule 3 | `_calibration_report()` mixes data collection, statistics computation, and formatted output in one function. |

### Rule 4 — I/O separation (5 findings)

| File | Line | Category | Finding |
|---|---|---|---|
| engine/__main__.py | ~35 | Rule 4 | `_run_compare()` mixes business decisions (profile field access, comparison logic) with I/O (file reading, stdout/stderr). |
| engine/__main__.py | ~95 | Rule 4 | `_run_batch()` same pattern. |
| engine/batch_processor.py | ~80 | Rule 4 | `_compare_pair()` mixes file-existence checks, extraction I/O, comparison logic, warning output, and report I/O in one function. The comparison parameters could be assembled by a pure function. |
| engine/page_group_detector.py | ~35 | Rule 4 | `extract_page_groups()` calls `extract_pages()` (file I/O) and then performs pattern matching (pure logic). Accept pages as a parameter instead. |
| engine/profile_loader.py | ~75 | Rule 4 | `load_profile()` reads the file (I/O) and validates its content (logic) in the same function. Split reading from validation. |

### Rule 5 — Naming conventions (170 findings)

**German test function names (165 findings):** All test files use German function names. Representative examples per file; each file's full count is noted.

| File | Line | Category | Finding |
|---|---|---|---|
| tests/test_text_comparator.py | various | Rule 5 | 31 test functions use German identifiers (e.g. `test_tc_t_001_identischer_text_kein_delta`, `test_normalize_text_silbentrennung_wird_zusammengefuehrt`). |
| tests/test_main.py | various | Rule 5 | ~20 test functions use German identifiers (e.g. `test_compare_json_ohne_delta`, `test_compare_mit_ungueltigem_profile_liefert_fehler_und_exit_code`). |
| tests/test_pdf_extractor.py | various | Rule 5 | ~15 test functions use German identifiers (e.g. `test_tc_x_001_nativen_text_aus_einseitigem_pdf_extrahieren`). |
| tests/test_profile_loader.py | various | Rule 5 | ~20 test functions use German identifiers (e.g. `test_tc_p_001_valides_json_profil_laden`). |
| tests/test_report_generator.py | various | Rule 5 | ~25 test functions use German identifiers (e.g. `test_tc_r_001_delta_markierung_im_einzel_report`). |
| tests/test_batch_processor.py | various | Rule 5 | ~20 test functions use German identifiers (e.g. `test_batch_compare_erzeugt_einzel_report_pro_ok_paar_im_report_dir`). |
| tests/test_page_group_detector.py | various | Rule 5 | 3 test functions use German identifiers (e.g. `test_tc_g_001_seitengruppe_per_such_pattern_identifizieren`). |
| tests/test_privacy_compliance.py | various | Rule 5 | 2 test functions use German identifiers (e.g. `test_tc_s_001_keine_netzwerkverbindung_waehrend_verarbeitung`). |
| tests/test_ocr_extractor.py | various | Rule 5 | ~10 test functions use German identifiers (estimated). |
| tests/test_region_filter.py | various | Rule 5 | ~5 test functions use German identifiers (estimated). |
| tests/generate_fixtures.py | various | Rule 5 | ~14 generator functions use English names ✓ (no finding). |

**Boolean naming violations (5 findings):**

| File | Line | Category | Finding |
|---|---|---|---|
| engine/text_comparator.py | ~45 | Rule 5 | Parameter `normalize_whitespace` is boolean but lacks `is`/`has`/`should` prefix. |
| engine/text_comparator.py | ~45 | Rule 5 | Parameter `case_sensitive` is boolean but lacks `is`/`has`/`should` prefix. |
| engine/profile_loader.py | ~55 | Rule 5 | Field `OcrConfig.enabled` is boolean but lacks `is`/`has`/`should` prefix. |
| engine/text_comparator.py | ~30 | Rule 5 | Field `CompareResult.ocr_was_used` uses `was` instead of `is`/`has`/`should`. |
| src/views/SettingsView.tsx | ~38 | Rule 5 | State variable `checking` is boolean but lacks `is`/`has`/`should` prefix. |

### Rule 6 — Function documentation (25 findings)

Functions without the required documentation header (docstring / JSDoc). Counts are per file where individual identification is not possible from the snapshot.

| File | Line | Category | Finding |
|---|---|---|---|
| engine/pdf_extractor.py | various | Rule 6 | ~5 internal helper functions lack docstrings (e.g. `_flatten_line_chars`, `get_text_blocks`, `join_block_text`). |
| engine/text_comparator.py | various | Rule 6 | `_words_with_pages()` has no docstring. |
| engine/page_group_detector.py | ~30 | Rule 6 | `_match_group_name()` has no docstring. |
| tests/test_main.py | ~20 | Rule 6 | `_write_single_page_pdf()` has no docstring. |
| tests/test_text_comparator.py | ~351 | Rule 6 | `_build_synthetic_pages()` has no docstring. |
| tests/test_text_comparator.py | ~371 | Rule 6 | `edit_page()` (nested helper, appears twice) has no docstring. |
| tests/test_batch_processor.py | ~25 | Rule 6 | `_write_single_page_pdf()` has no docstring. |
| src/App.tsx | 1 | Rule 6 | `App` component has no JSDoc. |
| src/views/SettingsView.tsx | various | Rule 6 | `handleNormalizeWhitespaceChange()`, `handleCompareModeChange()`, `checkEngine()` lack JSDoc. |
| src/types.ts | — | Rule 6 | File contains only type declarations; interfaces lack JSDoc (5 interfaces without documentation). |
| packaging/prepare_sidecar.mjs | various | Rule 6 | 4 functions lack JSDoc comments. |

*Note: ~25 is an estimate. Production engine code is well-documented; most findings are in test helpers, frontend components, and utility scripts.*

### Rule 7 — File header (0 findings — resolved)

All 47 source files now carry the required header block (file name, purpose, author, creation date, last-change date). Headers were added on 2026-08-09 based on the initial review findings. Recommendation: set up a pre-commit hook to keep the `changed` date current on future edits.

### Rule 8 — Why-comments (1 finding)

| File | Line | Category | Finding |
|---|---|---|---|
| engine/report_generator.py | — | Rule 8 | `# mehrfach als Form-XObject referenziert` is a fragment that narrates what the code does rather than explaining why `garbage=4` was chosen. |

*Note: The codebase has exceptionally thorough why-comments overall. References to diagnosis sessions, architectural decisions, and specific TC_REAL findings are pervasive and valuable.*

### Rule 9 — Configuration (4 findings)

| File | Line | Category | Finding |
|---|---|---|---|
| engine/profile_loader.py | ~58 | Rule 9 | `confidence_threshold: float = 0.85` — the default threshold is hard-coded in the dataclass. Extract to a named constant (e.g. `_DEFAULT_OCR_CONFIDENCE_THRESHOLD`). |
| engine/profile_loader.py | ~62 | Rule 9 | `dpi: int = 200` — the default DPI is hard-coded in the dataclass. There is `_DEFAULT_DPI = 200` in `ocr_extractor.py` but the profile default does not reference it. |
| engine/report_generator.py | — | Rule 9 | Report margins `20 * mm` appear in multiple places (`SimpleDocTemplate` calls). Extract to a named constant (e.g. `_PAGE_MARGIN_MM`). |
| packaging/build_sidecar.py | — | Rule 9 | `0o755` permission value is a magic number. Extract to a named constant. |

### Rule 10 — Secrets (0 findings)

PASS. No secrets in versioned files. The application has no cloud services, no API keys, no credentials by design.

### Rule 11 — Error handling (2 findings)

Judgment-based denominator: N = 20 error paths (try/except blocks, error-returning calls, file operations that can fail).

| File | Line | Category | Finding |
|---|---|---|---|
| engine/batch_processor.py | ~80 | Rule 11 | `_compare_pair()` does not wrap `extract_pages_for_profile()` or `compare()` in try/except. A corrupt PDF or unexpected extraction error will propagate as an unhandled exception, crashing the entire batch run instead of recording the pair as `status="error"`. |
| engine/batch_processor.py | ~120 | Rule 11 | `split_batch_pdf()` calls `single_doc.save()` and `single_doc.close()` without try/except inside the loop. A write failure on one split document would leave `src_doc` open (the outer `finally` handles it) but skip remaining groups without error reporting. |

### Rule 12 — Input validation (2 findings)

Judgment-based denominator: N = 10 entry points (functions accepting data from outside the process: CLI args, file paths, JSON profiles, Tauri IPC).

| File | Line | Category | Finding |
|---|---|---|---|
| engine/pdf_extractor.py | — | Rule 12 | `extract_pages(pdf_path)` does not validate that `pdf_path` exists or is a readable file before passing it to `fitz.open()`. The resulting `RuntimeError` from PyMuPDF is opaque compared to a clear "file not found" message. |
| engine/ocr_extractor.py | — | Rule 12 | `extract_text_via_ocr(pdf_path)` same issue — no upfront validation of `pdf_path`. |

### Rule 13 — Resource release (2 findings)

Judgment-based denominator: N = 12 resource acquisitions (fitz.open, pdfplumber.open, io.BytesIO, PIL.Image.open across production code).

| File | Line | Category | Finding |
|---|---|---|---|
| engine/batch_processor.py | ~105 | Rule 13 | `split_batch_pdf()`: `single_doc = fitz.open()` followed by `single_doc.save()` and `single_doc.close()` without try/finally. If `insert_pdf()` or `save()` raises, the document handle leaks. |
| engine/report_generator.py | — | Rule 13 | `generate_report()` opens `ref_doc`, `cnd_doc`, `report_doc`, and `side_by_side` via `fitz.open()` and closes them sequentially at the end without try/finally. If any operation between open and close raises, up to four document handles leak. Use context managers or a try/finally block. |

### Rule 14 — Security (0 findings)

Gate: PASS (see Gates table).

Ratio: n/a — the application has no externally reachable endpoints. All IPC is local (Tauri sidecar process, no network sockets). N = 0.

### Rule 15 — Logging (4 findings)

| File | Line | Category | Finding |
|---|---|---|---|
| engine/__main__.py | ~55 | Rule 15 | `print(f"Warnung: {warning}", file=sys.stderr)` — ad-hoc warning output without log levels. |
| engine/__main__.py | ~75 | Rule 15 | `print(str(exc), file=sys.stderr)` — error output without structured logging. |
| engine/batch_processor.py | ~95 | Rule 15 | `print(f"Warnung ({ref_path} / {cnd_path}): {warning}", file=sys.stderr)` — same ad-hoc pattern. |
| packaging/build_sidecar.py | — | Rule 15 | `print(f"[build_sidecar] ...")` — ad-hoc prefixed output instead of a logging framework. |

*Note: The sidecar architecture uses stdout for structured JSON IPC (intentional, not a finding). The issue is that warnings and errors go to stderr via raw `print` without log levels, timestamps, or a unified mechanism.*

### Rule 16 — Critical-path tests (2 findings)

Judgment-based denominator: N = 18 critical business-logic paths and boundary conditions.

| File | Line | Category | Finding |
|---|---|---|---|
| engine/profile_loader.py | ~130 | Rule 16 | `apply_overrides()` (TC-P-003 integration) is tested at unit level but never exercised through the production CLI or batch path. The integration path (CLI `--case-sensitive` flag overriding a profile value) has no coverage. |
| engine/batch_processor.py | ~80 | Rule 16 | `_compare_pair()` has no test for corrupt/unreadable PDF input. A corrupt file will raise an unhandled exception (see Rule 11), and this error path has no dedicated test case. |

### Rule 17 — Dependencies (0 findings — corrected)

Initial review reported `@tauri-apps/plugin-opener` as potentially unused. **Correction:** the package is used in `SingleComparisonView.tsx` and `BatchView.tsx` (import `openPath` for opening generated PDF reports) and correctly permitted in `src-tauri/capabilities/default.json` (`opener:allow-open-path`). Finding withdrawn.

All npm dependencies are version-locked via `package-lock.json`. Rust dependencies are pinned via `Cargo.lock`. Python dependency pinning (pyproject.toml) was not in the snapshot but is not counted as a finding.

### Rule 18 — Encoding (0 findings)

All 47 files are valid UTF-8 without BOM. Line endings are consistently LF across the project, enforced by `.gitattributes` (`* text=auto eol=lf`). `metrics.json` `rule_18_candidates` is empty.

## 5. Remediation order

Ranked by Q-impact per unit of effort. The three actions that would raise Q the most from the current 89.9:

1. **Add try/finally or context managers to resource acquisitions (Rule 13).** Current score: 83.3. Target: 100.0. ΔQ = +1.7. Effort: low — wrap `fitz.open()` calls in `split_batch_pdf()` and `generate_report()` with try/finally blocks. Two localized edits, no behavioral change, immediately testable.

2. **Validate file paths at system boundary (Rule 12).** Current score: 80.0. Target: 100.0. ΔQ = +2.1. Effort: low — add `Path(pdf_path).is_file()` checks with clear error messages at the top of `extract_pages()` and `extract_text_via_ocr()`. Two edits, no architectural change.

3. **Translate test function names to English (Rule 5).** Current score: 59.4. Target: ~97. ΔQ = +1.9. Effort: medium — ~165 renames across 10 test files. Can be partially automated (the TC-ID prefix stays, only the German description suffix changes). Combined with fixing 5 boolean parameter names (low effort), this yields the full improvement.

**Combined effect of all three:** Q ≈ 89.9 + 1.7 + 2.1 + 1.9 = **95.6 — green**, without architectural changes.
