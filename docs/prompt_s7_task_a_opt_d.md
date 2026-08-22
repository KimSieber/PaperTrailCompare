# Claude Code Prompt: PTC-S7 Tasks A-Opt + D — Cover Page Refinements

## Context

PaperTrail Compare v0.2.1, Sprint PTC-S7. Continuation of Task A (cover page
layout) plus Task D (KPI tile change). All changes are in
`engine/report_generator.py` and `tests/test_report_generator.py` only.

**No functional changes** to comparison logic, profile loading, batch
processing, GUI, or any other module. Purely cosmetic report output changes.

Project principles: TDD, synthetic fixtures only, `pytest` from project root
with `PYTHONPATH=.`, full suite green before commit. **Do not run `git commit`
or `git push`.**

Current state: 251 tests passing after Task A (Task 1 + Task 2).

---

## Task A-Opt — Compare-Regions table refinements

### A-Opt-1: Two-row column header

The compare-regions table currently has a single header row for the detail
columns only. Change to a **two-row header**, both rows with grey background
(`_COLOR_HAIRLINE`), mirroring the two-row data groups:

**Header row 1:** `#` | `Kommentar` (SPAN cols 1–5) | `Modus`
**Header row 2:** (empty) | `Bedingung` | `Seitenbereich` | `x` | `y` | `Breite` | `Höhe`

**No line between the two header rows** — just like the data row pairs have no
internal separator line. The GRID around the table provides the outer borders.

All column headers in **German**: `Kommentar`, `Modus`, `Bedingung`,
`Seitenbereich`.

### A-Opt-2: GRID lines (vertical + horizontal)

Replace the current line-based styling with a full `GRID` — identical to the
exclude-regions table:

```python
("GRID", (0, 0), (-1, -1), 0.5, _COLOR_HAIRLINE),
```

Remove all individual `LINEABOVE` / `LINEBELOW` commands that were previously
used for visual grouping — the GRID handles all borders now.

Keep the header background for both header rows:
```python
("BACKGROUND", (0, 0), (-1, 1), _COLOR_HAIRLINE),
```

### A-Opt-3: "Seitenbereich" column + "Alle Seiten" for page=0

1. Rename the column header from `"Seite"` to `"Seitenbereich"`.

2. `CompareRegion` supports `page=0` (all pages) and `page_from` (from page N),
   just like `ExcludeRegion`. The existing `_region_page_label()` handles
   `ExcludeRegion` which has the same fields. Either:
   - Reuse `_region_page_label()` by making it accept both types (duck typing
     on `.page` and `.page_from` attributes), OR
   - Create `_compare_region_page_label()` with identical logic.

   The display must be:
   - `page=0` → `"Alle Seiten"`
   - `page=N` (N>0) → `"Seite N"`
   - `page_from=N` → `"Ab Seite N"`

   Update the existing `_compare_region_page_label()` helper (created in
   Task 2) to match this logic — it currently only handles concrete pages.

### Implementation notes

The data rows remain as implemented in Task 2 (two-row groups per region).
The only change is that the header now also has two rows, the styling uses
GRID, column labels are German, and the page display handles wildcards.

Adjust row index calculations: with a 2-row header, data rows start at
index 2 (not 1). For N regions, the comment row is at `2 + 2*i` and the
detail row at `3 + 2*i`.

---

## Task D — Replace "Vergleiche" KPI tile with "Dauer"

### D-1: Change KPI tile

In `_build_summary_page_pdf_bytes()`, the KPI tiles are currently:

```python
tiles = [
    _build_kpi_tile("Seiten", str(total_pages), ...),
    _build_kpi_tile("Vergleiche", str(comparisons), ...),
    _build_kpi_tile("Deltas", str(...), ...),
    _build_kpi_tile("Übereinstimmung", f"{...:.0f} %", ...),
]
```

Replace the `"Vergleiche"` tile with `"Dauer"`:

```python
_build_kpi_tile("Dauer", _format_duration_mmss(duration_seconds), _COLOR_TILE_NEUTRAL),
```

### D-2: Duration format helper

Create a helper function:

```python
def _format_duration_mmss(seconds: Optional[float]) -> str:
    """Format duration as MM:SS (whole seconds, no decimals).
    Returns '—' if seconds is None."""
    if seconds is None:
        return "—"
    total = int(round(seconds))
    minutes = total // 60
    secs = total % 60
    return f"{minutes:02d}:{secs:02d}"
```

### D-3: Remove "Verarbeitungsdauer" from meta table

Remove the row `["Verarbeitungsdauer", ...]` from `meta_rows`. The duration
is now shown in the KPI tile, so the meta table entry is redundant.

### D-4: Remove unused `comparisons` parameter

The `comparisons` parameter of `_build_summary_page_pdf_bytes()` is no longer
used (it was only displayed in the "Vergleiche" tile). Check all call sites:

- If `comparisons` is passed by callers, remove it from the call sites too.
- If removing the parameter would affect too many files, keep it but add a
  `# TODO: remove unused parameter` comment.

**Important:** Only remove if it does not require changes outside
`engine/report_generator.py`. If callers are in other files, leave the
parameter and add the TODO.

---

## Tests

### Adjusted existing tests

- Tests asserting `"Vergleiche"` appears in report text → remove that
  assertion or change to assert it does NOT appear.
- Tests asserting `"Verarbeitungsdauer"` appears in meta table → remove
  that assertion.
- Tests that pass `comparisons=` to `_build_summary_page_pdf_bytes` →
  adjust if the parameter is removed.

### New / updated tests

1. **`test_summary_page_shows_duration_tile_mmss_format`** — Generate report
   with `duration_seconds=125.7`. Extract page 0 text. Assert `"Dauer"`
   appears. Assert `"02:06"` appears (125.7 rounds to 126 = 2min 6sec).
   Assert `"Vergleiche"` does NOT appear. Assert `"Verarbeitungsdauer"` does
   NOT appear in meta table section.

2. **`test_summary_page_duration_tile_none_shows_dash`** — Generate report
   with `duration_seconds=None`. Assert `"Dauer"` appears and `"—"` appears
   in the tile area.

3. **`test_summary_page_duration_tile_zero_seconds`** — Generate report with
   `duration_seconds=0.4`. Assert `"00:00"` appears (rounds to 0).

4. **Update `test_summary_page_shows_compare_regions_table`** — Verify
   German column headers (`"Kommentar"`, `"Modus"`, `"Bedingung"`,
   `"Seitenbereich"`). Verify `"Alle Seiten"` appears for a region with
   `page=0`. Verify two-row header structure is present.

5. **Update `test_summary_page_shows_both_exclude_and_compare_regions`** —
   Add a compare_region with `page=0` and verify `"Alle Seiten"` appears in
   the compare-regions section.

Run full test suite. Report results.

---

## Workflow

Work in TWO steps:

- **Step 1**: Task A-Opt (all three sub-tasks). Run full suite, report.

**STOP and wait for feedback.**

- **Step 2**: Task D (all four sub-tasks). Run full suite, report.

**Commit message (after both steps approved):**
`feat(report): compare-regions table polish + duration tile (PTC-S7-A/D)`
