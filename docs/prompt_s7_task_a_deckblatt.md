# Claude Code Prompt: PTC-S7 Task A — Deckblatt-Optimierung

## Context

PaperTrail Compare v0.2.1, Sprint PTC-S7. This task modifies **only** the
single-comparison report cover page layout in `engine/report_generator.py`.

**No functional changes** to comparison logic, profile loading, batch
processing, GUI, or any other module. This is a purely cosmetic change to
report PDF output.

All changes follow project principles: TDD (test first), synthetic fixtures
only, `pytest` from project root with `PYTHONPATH=.`, full suite green before
any commit. **Do not run `git commit` or `git push`.**

---

## Task 1 — Move "Vergleichsdatum" from meta table to subtitle line

### 1a. Implementation

In `_build_summary_page_pdf_bytes()`:

1. **Remove** the `["Vergleichsdatum", ...]` row from the `meta_rows` list
   (currently the second-to-last entry).

2. **Add a subtitle line** between `_build_hairline_table()` and the KPI tile
   row, using the **exact same pattern** as the batch report in
   `generate_batch_report()`:

   ```python
   story.append(Spacer(1, 6))
   story.append(Paragraph(
       f"Vergleich vom {datetime.now().strftime('%d.%m.%Y, %H:%M:%S')} Uhr",
       _SUBTITLE_STYLE,
   ))
   story.append(Spacer(1, 6))
   ```

   This replaces the current `Spacer(1, 12)` between hairline and KPI tiles.

### 1b. Tests

Adjust existing tests in `tests/test_report_generator.py`:

- Any test that asserts `"Vergleichsdatum"` appears in the meta table text
  must be updated: the string `"Vergleichsdatum"` should **no longer** appear
  in the extracted text. Instead, assert that `"Vergleich vom"` and `"Uhr"`
  appear in the summary page text (subtitle line).

- If no existing test checks for "Vergleichsdatum", add one:
  **`test_summary_page_shows_date_as_subtitle_not_in_meta_table`** —
  generate a report, extract page 0 text, assert `"Vergleich vom"` is
  present and `"Vergleichsdatum"` is absent.

Run full test suite. Report results.

**STOP here and wait for feedback before proceeding to Task 2.**

---

## Task 2 — Compare-Regions table on cover page

### 2a. Helper function `_compare_region_page_label`

Create a helper analogous to `_region_page_label()` for `ExcludeRegion`, but
for `CompareRegion`. The `CompareRegion` dataclass has a `page` field (int,
1-based, no `page_from` or `page=0` wildcards). Return `f"Seite {region.page}"`.

### 2b. Implementation

In `_build_summary_page_pdf_bytes()`, **after** the existing exclude-regions
block (after the `region_warnings` loop), add a new block:

```python
if profile is not None and profile.compare_regions:
    story.append(Spacer(1, 14))
    story.append(Paragraph("Vergleichs-Regionen", _TILE_LABEL_STYLE))
    story.append(Spacer(1, 4))
    # Build the compare-regions table (see layout below)
    ...
    story.append(cr_table)
```

### 2c. Table layout — two-row groups

The table uses **7 fixed columns** with this width distribution (total 170mm):

| #   | Comment (colspan 5, merged with cols 1–5) | Mode       |
|-----|-------------------------------------------|------------|
|     | Condition        | Seite  | x    | y    | Breite | Höhe  |

Column widths (7 columns):
- Col 0 (`#`): 8mm
- Col 1 (`Comment` / `Condition`): 52mm
- Col 2 (`Seite`): 22mm
- Col 3 (`x`): 18mm
- Col 4 (`y`): 18mm
- Col 5 (`Breite`): 18mm (comment row: merged with cols 1–4 via SPAN)
- Col 6 (`Höhe` / `Mode`): 34mm

**Row structure for N compare_regions:**

- **Row 0 — Column headers for detail rows:**
  Cells: `""`, `"Condition"`, `"Seite"`, `"x"`, `"y"`, `"Breite"`, `"Höhe"`
  (The `#` and detail-column headers. No header for the comment/mode row
  since those are self-explanatory.)

- **For each region i (0-based), two rows:**
  - **Row 1 + 2*i — Comment row:**
    Cell 0: `f"#{i+1}"` (region number)
    Cells 1–5: comment text, **SPAN (1, row) to (5, row)** to merge into
    one wide cell. If `comment` is empty or None, display `"—"`.
    Cell 6: mode value (`"sequential"` or `"unordered"`)

  - **Row 2 + 2*i — Detail row:**
    Cell 0: empty `""`
    Cell 1: condition string
    Cell 2: `_compare_region_page_label(region)`
    Cells 3–6: `x`, `y`, `width`, `height` (formatted with `:g`)

**TableStyle:**

```python
cr_style_commands = [
    # Header row background (same grey as exclude-regions table)
    ("BACKGROUND", (0, 0), (-1, 0), _COLOR_HAIRLINE),
    # Font size 8 throughout
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    # Padding
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    # Vertical alignment
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
]

# Add SPAN and visual grouping for each region:
for i in range(len(profile.compare_regions)):
    comment_row = 1 + 2 * i
    detail_row = 2 + 2 * i
    # Merge comment across columns 1-5
    cr_style_commands.append(("SPAN", (1, comment_row), (5, comment_row)))
    # Separator line ABOVE each comment row (except the first group,
    # which already has the header row above it)
    if i > 0:
        cr_style_commands.append(
            ("LINEABOVE", (0, comment_row), (-1, comment_row), 0.75, _COLOR_HAIRLINE)
        )
    # Light bottom border under each detail row for subtle grouping
    cr_style_commands.append(
        ("LINEBELOW", (0, detail_row), (-1, detail_row), 0.25, _COLOR_HAIRLINE)
    )

cr_table = Table(cr_rows, colWidths=[...])
cr_table.setStyle(TableStyle(cr_style_commands))
```

Use `Paragraph` with a style derived from `_CELL_STYLE` at fontSize 8 for
all cells that might need text wrapping (comment, condition). Numeric cells
can be plain strings.

### 2d. Tests

Add to `tests/test_report_generator.py`:

1. **`test_summary_page_shows_compare_regions_table`** — Profile with 2
   compare_regions (different pages, one sequential, one unordered, one with
   comment, one without). Generate report, extract page 0 text:
   - Assert `"Vergleichs-Regionen"` appears
   - Assert `"#1"` and `"#2"` appear
   - Assert both condition strings appear
   - Assert `"sequential"` and `"unordered"` appear
   - Assert coordinate values appear
   - Assert `"—"` appears (for the region without comment)

2. **`test_summary_page_without_compare_regions_shows_no_table`** — Profile
   with empty `compare_regions` list (or no compare_regions at all). Generate
   report, extract page 0 text:
   - Assert `"Vergleichs-Regionen"` does NOT appear

3. **`test_summary_page_shows_both_exclude_and_compare_regions`** — Profile
   with both `exclude_regions` and `compare_regions`. Generate report, extract
   page 0 text:
   - Assert both `"Ausgeschlossene Regionen"` and `"Vergleichs-Regionen"` appear
   - Assert exclude region details appear before compare region details

Run full test suite. Report results.

**Commit message: `feat(report): compare_regions table on cover page, date as subtitle (PTC-S7-A)`**

---

## Constraints

- **Only modify** `engine/report_generator.py` and `tests/test_report_generator.py`.
- **No changes** to profile loading, comparison engine, batch processor, GUI,
  or any Rust/TypeScript code.
- **No new dependencies.**
- All `Paragraph` text must be `html.escape()`d for safety.
- Verify that existing tests still pass — especially:
  - `test_summary_page_shows_profile_settings`
  - `test_summary_page_shows_exclude_regions_detail`
  - `test_excluded_regions_shows_warning_on_incomplete_application`
  - All batch report tests (unchanged module, but run full suite)
