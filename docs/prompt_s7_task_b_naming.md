# Claude Code Prompt: PTC-S7 Task B — Unified Output File Naming

## Context

PaperTrail Compare v0.2.1, Sprint PTC-S7. This task unifies the output file
naming scheme across single comparison and batch processing to ensure
consistent, predictable filenames with built-in overwrite protection via
minute-precision timestamps.

Project principles: TDD, synthetic fixtures only, `pytest` from project root
with `PYTHONPATH=.`, full suite green before commit. **Do not run `git commit`
or `git push`.**

Current state: 254 tests passing after Tasks A/D.

---

## Current naming (to be replaced)

- Single comparison: `PTC-Vergleich_{RefStem}_{CndStem}_{YYYY-MM-DD_HH-MM}.pdf`
  (timestamp AFTER filenames)
- Batch individual reports: `PTC-Vergleich_{RefStem}_{CndStem}.pdf`
  (NO timestamp, `_1`/`_2` suffix on collision)
- Batch report: `PTC-Batch-Report_{YYYY-MM-DD_HH-MM}.pdf`

## New unified naming scheme

- **Single comparison:** `PTC-Vergleich_YYYY-MM-DD_HH-MM_{RefStem}_{CndStem}.pdf`
- **Batch individual reports:** `PTC-Vergleich_YYYY-MM-DD_HH-MM_{RefStem}_{CndStem}.pdf`
  (timestamp = batch start time, identical format to single comparison)
- **Batch report:** `PTC-Batch-Report_YYYY-MM-DD_HH-MM_{CSVStem}.pdf`
  (CSVStem = stem of the CSV file path, e.g. `filelist.csv` → `filelist`)

### Key rules

1. **Timestamp position:** BEFORE the document names (more natural sort order).
2. **Timestamp source — single:** `datetime.now()` at comparison start
   (before extraction begins).
3. **Timestamp source — batch:** single `datetime.now()` at batch start,
   shared across the batch report AND all individual reports in that batch.
4. **No collision suffixes:** the `_1`/`_2`/`_3` append logic in
   `_unique_report_path()` is removed. Overwrites within the same minute
   are accepted.
5. **Identical filenames:** a single comparison and a batch comparison of the
   same pair in the same minute produce the exact same filename.

---

## Implementation

### Step 1 — Shared filename builder

Create a helper function (in `engine/report_generator.py` or a suitable
shared location):

```python
def build_comparison_report_filename(
    ref_path: Union[str, Path],
    cnd_path: Union[str, Path],
    timestamp: datetime,
) -> str:
    """Builds the unified report filename for a single comparison.
    Used by both standalone single comparison and batch individual reports."""
    ts = timestamp.strftime("%Y-%m-%d_%H-%M")
    ref_stem = Path(ref_path).stem
    cnd_stem = Path(cnd_path).stem
    return f"PTC-Vergleich_{ts}_{ref_stem}_{cnd_stem}.pdf"


def build_batch_report_filename(
    csv_path: Union[str, Path],
    timestamp: datetime,
) -> str:
    """Builds the batch report filename including the CSV stem."""
    ts = timestamp.strftime("%Y-%m-%d_%H-%M")
    csv_stem = Path(csv_path).stem
    return f"PTC-Batch-Report_{ts}_{csv_stem}.pdf"
```

### Step 2 — Single comparison (`engine/__main__.py`)

In `_run_compare()`:

1. Capture `start_time = datetime.now()` before the comparison starts.
2. Use `build_comparison_report_filename(args.ref_pdf, args.cnd_pdf, start_time)`
   to construct the report filename.
3. The output directory logic remains unchanged — only the filename changes.

### Step 3 — Batch processing

#### 3a. `engine/__main__.py` → `_run_batch()`

1. `start_time = datetime.now()` already exists — use it.
2. Replace the batch report filename construction with
   `build_batch_report_filename(args.filelist, start_time)`.
3. Pass `timestamp=start_time` to `batch_compare()` (new parameter).

#### 3b. `engine/batch_processor.py`

1. Add `timestamp: Optional[datetime] = None` parameter to `batch_compare()`.
   If None, use `datetime.now()` as fallback (for backward compatibility
   with tests that don't pass it).
2. Thread `timestamp` through to `_compare_pair()` / `_compare_pair_worker()`.
3. In `_compare_pair()`: replace the current filename construction with
   `build_comparison_report_filename(ref_path, cnd_path, timestamp)`.
4. **Remove `_unique_report_path()`** — it is no longer needed. Replace its
   usage with a simple `report_dir / filename` construction.

### Step 4 — Cleanup

- Remove any imports or code related to the old `_unique_report_path()`.
- Verify no other code references the old naming pattern.

---

## Tests

### Existing tests to update

Search for all tests that assert on report filenames. Common patterns:
- `"PTC-Vergleich_"` followed by `{RefStem}_{CndStem}_{timestamp}`
  → change to `{timestamp}_{RefStem}_{CndStem}`
- `"PTC-Batch-Report_"` without CSV stem → add CSV stem
- Tests using `_unique_report_path` or testing `_1`/`_2` collision behavior
  → remove or replace (collision logic no longer exists)

### New tests

1. **`test_build_comparison_report_filename_format`** — verify the helper
   returns the correct format with timestamp before stems.

2. **`test_build_batch_report_filename_includes_csv_stem`** — verify the
   helper includes the CSV file stem after the timestamp.

3. **`test_batch_individual_reports_use_batch_start_timestamp`** — run a
   batch with 2+ pairs, verify all individual report filenames contain the
   same timestamp (the batch start time), not their individual completion
   times.

4. **`test_single_and_batch_report_filename_identical_for_same_pair`** —
   given the same ref/cnd pair and the same timestamp, both
   `build_comparison_report_filename()` calls produce identical filenames.

Run full test suite. Report results.

---

## Workflow

Work in TWO steps:

- **Step 1**: Implement the filename helpers + single comparison changes
  (Steps 1–2). Run full suite, report.

**STOP and wait for feedback.**

- **Step 2**: Implement batch changes + cleanup + all tests (Steps 3–4).
  Run full suite, report.

**Commit message: `feat: unified output file naming with timestamps (PTC-S7-B)`**
