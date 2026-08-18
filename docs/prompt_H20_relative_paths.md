# Claude Code Prompt: H20 — Relative Paths in filelist.csv

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.

Sprint PTC-S5 (Housekeeping). `tests/fixtures/TC-B-*/filelist.csv` files contain
absolute paths (`/Users/kim/Dropbox/Dev/GitHub/PaperTrailCompare/...`), making them
non-portable and leaking the developer's local directory structure into the repo.

**Do NOT run `git commit` or `git push`** — Kim commits manually after verification.

---

## Problem

`tests/generate_fixtures.py` writes `str(ref_path)` / `str(cnd_path)` into
filelist.csv files. Since `ref_path` is constructed from `fixture_dir()` which
returns an absolute `Path`, the CSV entries are absolute paths tied to the
machine where the script ran.

---

## Fix

### Step 1 — Investigate

1. Search `tests/generate_fixtures.py` for ALL places that write CSV filelists.
   List each function and the affected TC-ID (e.g., `generate_tc_b_001_003`
   writes `TC-B-001/filelist.csv`, `TC-B-002/filelist.csv`, etc.).
2. List ALL `filelist.csv` files under `tests/fixtures/` — there may be more
   than TC-B-001 through TC-B-003.
3. Check whether any test file reads these CSV files directly (search for
   `filelist.csv` references in `tests/test_*.py`). Report findings.

### Step 2 — Fix generate_fixtures.py

In every function that writes a `filelist.csv`, change the path entries from
absolute to **relative to the CSV file's directory**.

The CSV sits in `tests/fixtures/<TC-ID>/filelist.csv`, and the PDFs sit in
`tests/fixtures/<TC-ID>/pairs/`. So each entry should be:

```
pairs/doc_01_ref.pdf,pairs/doc_01_cnd.pdf
```

Implementation: use `os.path.relpath(ref_path, start=d)` where `d` is the
fixture directory (the directory containing the CSV), or construct the relative
path directly when building `filelist_rows`.

### Step 3 — Regenerate all filelist.csv files

Run `generate_fixtures.py` to regenerate the fixtures:

```bash
PYTHONPATH=. python tests/generate_fixtures.py
```

Then verify:
1. `grep -r "/Users/" tests/fixtures/*/filelist.csv` — must return NO matches.
2. Spot-check one CSV file to confirm the format is `pairs/doc_XX_ref.pdf,...`.

### Step 4 — Check batch_processor.py path resolution

The engine's `batch_compare()` in `engine/batch_processor.py` reads filelist
CSVs at runtime. Check how it resolves the paths from the CSV:
- If it uses the paths as-is (absolute), relative paths would break.
- If it resolves them relative to the CSV's directory or CWD, relative paths
  work.

**If batch_compare uses paths as-is:** Add path resolution so that entries in
the CSV are resolved relative to the CSV file's parent directory. This makes
the filelist portable — it works regardless of where the CSV is stored.

**If batch_compare already resolves relative paths:** No change needed — report
how it works.

### Step 5 — Verify

1. Run `PYTHONPATH=. python -m pytest -q` — all 251 tests must pass.
2. Confirm no absolute paths remain in any `filelist.csv`.

---

## Rules

- Do NOT run `git commit` or `git push`.
- Do NOT change any test logic or assertions.
- Do NOT delete any filelist.csv files.
- Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.
