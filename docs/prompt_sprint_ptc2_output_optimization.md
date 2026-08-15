# Claude Code Prompt: Sprint PTC-2 — Output Optimization

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.
Critical requirement: **everything runs exclusively locally** — no cloud, no server,
no network connections during processing.

All changes follow the project principles: TDD (test first), synthetic fixture PDFs
(never customer documents), `pytest` must be green before any commit.

Current state: 164+ tests green, Sprint PTC-1 completed (commits ffec65e–1f47865).

---

## Task A — Processing Duration on Batch Individual Reports

**Observation:** Single-comparison reports show processing duration (seconds) on
the summary page. Individual reports generated during batch processing show
"Verarbeitungsdauer" but always display "--" instead of the actual time.

**Root cause (already diagnosed):** `_compare_pair()` in `batch_processor.py`
does not measure time. The `generate_report()` call (approx. line 101–103) does
not pass `duration_seconds`:

```python
# Current (broken):
generate_report(
    result, ref_file, cnd_file, report_path,
    profile=profile, region_warnings=region_warnings,
    # ← duration_seconds is missing entirely!
)
```

In contrast, `_run_single()` in `__main__.py` (lines 74–87) correctly wraps
extraction+comparison in `time.perf_counter()` and passes the result through.

**Fix (minimal, only `batch_processor.py`):**
1. Add `start = time.perf_counter()` before the extraction/compare block
   (before `extract_pages_for_profile` calls, approx. line 82).
2. Compute `duration_seconds = time.perf_counter() - start` after `compare()`
   returns (approx. line 97).
3. Pass `duration_seconds=duration_seconds` to the existing `generate_report()`
   call (lines 101–103).

**Test:** Add a test that verifies the summary page of a batch-generated
individual report contains a numeric duration value instead of "--". Use
`fitz.open()` to extract text from page 0 and assert a number is present
in the duration field.

**Commit after green tests.**

---

## Task B — Table Header Contrast Fix

**Observation:** All PDF report tables with a dark blue header row
(`#1F4E79`) display **black text** on the dark blue background — very hard
to read. This affects:
- Delta detail table (end of single comparison report)
- Batch main table (batch report)
- Any other table using `#1F4E79` as header background

**Root cause (already diagnosed):** ReportLab `Paragraph` objects override
`TableStyle` `TEXTCOLOR`. The header cells use `Paragraph(..., _CELL_STYLE)`
or `Paragraph(..., _DETAIL_CELL_STYLE)` — neither sets an explicit
`textColor`, so the ReportLab default (black) wins. The `TEXTCOLOR=white`
in `_TABLE_STYLE` is effectively dead code.

**Fix:**
1. Create dedicated header `ParagraphStyle` variants:
   - `_HEADER_CELL_STYLE` (based on `_CELL_STYLE`, with
     `textColor=colors.white`, `fontName="Helvetica-Bold"`)
   - `_DETAIL_HEADER_CELL_STYLE` (based on `_DETAIL_CELL_STYLE`, with
     `textColor=colors.white`, `fontName="Helvetica-Bold"`)
2. Use these styles consistently for **all** header row cells in tables that
   have `BACKGROUND` `#1F4E79`.
3. Also add `("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")` to the
   `TableStyle` definitions (`_TABLE_STYLE`, `_DETAIL_TABLE_STYLE`) for
   consistency — even though the Paragraph style takes precedence, the
   TableStyle should match to avoid confusion.

**Not affected (leave unchanged):**
- The exclude regions table on the summary page — it uses a light grey
  (`_COLOR_HAIRLINE`) background and should remain as-is (secondary
  information, deliberately less prominent).

**Test:** Existing report tests that extract table header text via
`fitz.open()` must remain green. No new color-verification tests needed
(color testing in PyMuPDF would be fragile); visual verification by Kim.

**Commit after green tests.**

---

## Task C — Sum of Deltas + Timestamp Relocation in Batch Report

**Observation:** When using batch processing for profile fine-tuning, the
total number of deltas across all pairs is the key indicator for whether a
re-run improved or worsened results. This sum is currently not shown.

**Changes:**

### C1 — Replace "Zeitpunkt" KPI tile with "Summe Deltas"

The batch report header currently shows 8 KPI tiles. Replace the
"Zeitpunkt" tile with a "Summe Deltas" tile:
- Label: `"Summe Deltas"`
- Value: sum of `len(pair.compare_result.deltas)` across all pairs with
  `status="ok"`
- Use the same accent color logic as the single-report delta tile:
  orange accent if sum > 0, green if sum == 0.

### C2 — Move timestamp to subtitle line

Add a subtitle line between the hairline separator and the KPI tile row:
- Format: `"Batch-Lauf vom DD.MM.YYYY, HH:MM:SS Uhr"`
- Use the existing `_SUBTITLE_STYLE` (grey, understated).
- Position: after `_build_hairline_table()`, before `_build_kpi_tile_row()`.
- The timestamp must include the **start time** with seconds precision
  (HH:MM:SS), not just HH:MM as in the current filename timestamp.

**Data flow:** `generate_batch_report()` already receives `duration_seconds`.
For the timestamp, check if a `datetime` is already available or passed in;
if not, use `datetime.now()` at report generation time (which is
immediately after batch completion, so close enough). If a more precise
"batch start time" is needed, accept an optional `start_time: datetime`
parameter.

**Test:**
- Existing test `test_tc_r_002_batch_report_kopfbereich_dokumentanzahl_laufzeit_zeitpunkt`
  checks for timestamp — adjust to verify the new subtitle format.
- Add a test that verifies "Summe Deltas" and the correct sum value appear
  in the batch report text.

**Commit after green tests.**

---

## Task D — Output File Naming Prefix

**Observation:** When all files (source PDFs + result reports) reside in the
same directory, it is hard to distinguish source files from report files
because the report filename is just a combination of the two source
filenames.

**Changes:**

### D1 — Single comparison reports: prefix "PTC-Vergleich_"

All individual comparison report filenames must start with `PTC-Vergleich_`,
followed by the existing `{RefStem}_{CndStem}` pattern.

**Affected locations:**
- `engine/report_generator.py` or wherever the single-report output filename
  is constructed (check `__main__.py` — the caller may build the path).
- `engine/batch_processor.py` → `_unique_report_path()` — this builds the
  filename for batch-generated individual reports.

**Important:** The prefix applies to **both** standalone single comparisons
**and** individual reports generated during batch processing.

### D2 — Batch report: prefix "PTC-Batch-Report_"

The batch summary report filename changes from
`Batch-Report_{YYYY-MM-DD_HH-MM}.pdf` to
`PTC-Batch-Report_{YYYY-MM-DD_HH-MM}.pdf`.

**Affected location:** `__main__.py` → `_run_batch()`, approx. line 154
where `report_path` is constructed.

Also check the Tauri/Rust side (`lib.rs`) — if the batch report filename is
constructed there as well, update it consistently.

### D3 — Tests

- Update all existing tests that assert on report filenames to expect the
  new prefixes:
  - `test_batch_compare_erzeugt_einzel_reports_im_report_dir` →
    expect `PTC-Vergleich_doc_01_ref_doc_01_cnd.pdf` etc.
  - `test_batch_compare_haengt_zaehler_an_bei_namenskollision` →
    expect `PTC-Vergleich_ref_cnd.pdf` and `PTC-Vergleich_ref_cnd_2.pdf`
  - Any test checking for `Batch-Report_` in the filename → expect
    `PTC-Batch-Report_`
  - CLI/main tests that check `report_path` in JSON output
- Verify the single comparison path also produces the prefix (check if
  the filename is built in `__main__.py` `_run_single()` or passed in by
  the Tauri command — if Tauri builds the path, note this for manual
  verification on the Rust/TS side).

**Commit after green tests.**

---

## Working Instructions

- **Step by step, pause after max 2 steps** and wait for feedback before
  continuing.
- **TDD:** Write/adjust tests first, run `pytest`, then implement.
- Suggested order: A → B → C → D (increasing scope of changes).
- Before starting, verify the current repo state:
  - Run `pytest` to confirm baseline is green.
  - Check that no uncommitted changes from a prior session are pending.
- Commit at meaningful milestones after green `pytest`.
- For pure layout changes (Task B), prepare a sample report for manual
  visual verification.
- At the end, run the full `pytest` suite — all existing + new tests must
  be green.
