# B3 — Migrate `import fitz` → `import pymupdf`

## Context

PyMuPDF deprecated the `import fitz` entry point. The deprecation warning
is printed when the sidecar process starts, corrupting stdout and causing
Tauri's JSON parser to fail with `expected value at line 1 column 1` on
Windows single comparisons (Bug B2). Replacing the import eliminates the
warning at the source and fixes both B2 and B3.

## Goal

Replace every `import fitz` with `import pymupdf` and every `fitz.` call
with `pymupdf.` across the entire codebase. The PyMuPDF API is identical
under both names — this is a pure rename, no behavioral change.

## Steps

### Step 1 — Find all occurrences

Run:
```bash
grep -rn "import fitz" engine/ tests/ tools/ packaging/
grep -rn "fitz\." engine/ tests/ tools/ packaging/
```

Document every file and line that needs changing.

### Step 2 — Replace imports and calls in engine files

For each file in `engine/`:

1. Replace `import fitz` with `import pymupdf`
2. Replace all `fitz.` with `pymupdf.` (e.g. `fitz.open(` → `pymupdf.open(`,
   `fitz.Rect(` → `pymupdf.Rect(`, `fitz.Pixmap(` → `pymupdf.Pixmap(`)

Known files (verify with grep, there may be more):
- `engine/pdf_extractor.py`
- `engine/region_filter.py`
- `engine/ocr_extractor.py`
- `engine/report_generator.py`

### Step 3 — Replace imports and calls in test files

Same pattern for all test files that use fitz:
- `tests/test_report_generator.py`
- `tests/generate_fixtures.py`
- Any other test file found by grep

### Step 4 — Replace in tools

- `tools/diag_deltas.py` (if it uses `import fitz`)
- Any other tool script found by grep

### Step 5 — Update pyproject.toml

In `pyproject.toml`, update the mypy override:

```toml
# Before:
[[tool.mypy.overrides]]
module = ["fitz", "pytesseract"]
ignore_missing_imports = true

# After:
[[tool.mypy.overrides]]
module = ["pymupdf", "pytesseract"]
ignore_missing_imports = true
```

### Step 6 — Run tests

```bash
PYTHONPATH=. python -m pytest -q
```

All 220+ tests must pass. If any test fails, check whether it uses `fitz`
directly (e.g. `fitz.open()` in assertions) and update accordingly.

### Step 7 — Verify no remnants

```bash
grep -rn "import fitz" engine/ tests/ tools/ packaging/
grep -rn "[^a-z]fitz\." engine/ tests/ tools/ packaging/
```

Both greps must return zero results (except possibly comments/docstrings
that mention the old name for historical context — those are acceptable
but should be updated to say "PyMuPDF" or "pymupdf" where possible).

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT change any logic, parameters, or behavior — this is a pure rename.
- Do NOT touch `packaging/papertrail-engine.spec` — it already uses
  `collect_all("pymupdf")`, which is correct.
- Docstrings/comments that say "PyMuPDF (fitz)" can be updated to just
  "PyMuPDF" or "PyMuPDF (pymupdf)" at your discretion.
