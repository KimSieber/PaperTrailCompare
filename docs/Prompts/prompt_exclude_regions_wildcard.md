# Prompt: exclude_regions wildcard syntax + report enhancement + GUI profile management

Four blocks, executed sequentially. Pause after each block and wait for confirmation before proceeding.

---

## Block 1 — Data model + validation (Python engine)

### 1a. ExcludeRegion dataclass (`engine/profile_loader.py`)

Change `ExcludeRegion` so that `page` and `page_from` are both optional. Exactly one of the two must be set (enforced in `load_profile`, not in the dataclass itself).

```python
@dataclass
class ExcludeRegion:
    x: float
    y: float
    width: float
    height: float
    page: Optional[int] = None
    page_from: Optional[int] = None
```

Note: all existing call sites use keyword arguments (`ExcludeRegion(page=1, x=0, ...)`), so moving `page` after the coordinate fields does not break anything.

### 1b. Region dataclass (`engine/pdf_extractor.py`)

Add `page_from: Optional[int] = None` to the internal `Region` dataclass (or NamedTuple — check which it is). If it has positional fields without defaults before it, you may need to reorder similarly. Keep backward compatibility with existing `Region(page=..., x=..., y=..., w=..., h=...)` calls.

### 1c. `load_profile` (`engine/profile_loader.py`)

Update the JSON parsing of `exclude_regions` entries to handle three variants:

1. `{"page": 1, ...}` — specific page (existing behavior)
2. `{"page": 0, ...}` — all pages (new)
3. `{"page_from": 2, ...}` — from page N to end of document (new)

Validation rules (raise `ValidationError`):
- Both `page` and `page_from` present in same entry → error
- Neither `page` nor `page_from` present → error
- `page` < 0 → error (0 is valid = all pages, 1+ = specific page)
- `page_from` < 1 → error (page_from=0 makes no sense, pages are 1-based)
- Coordinate fields (`x`, `y`, `width`, `height`) remain mandatory

### 1d. Tests for Block 1

Add to `tests/test_profile_loader.py`:

1. **`test_load_profile_exclude_region_page_zero_all_pages`** — profile with `{"page": 0, "x": 0, "y": 0, "width": 100, "height": 50}` loads successfully, `region.page == 0`, `region.page_from is None`
2. **`test_load_profile_exclude_region_page_from`** — profile with `{"page_from": 2, "x": 0, "y": 0, "width": 100, "height": 50}` loads successfully, `region.page is None`, `region.page_from == 2`
3. **`test_load_profile_exclude_region_page_and_page_from_both_set_raises`** — `{"page": 1, "page_from": 2, ...}` → `ValidationError`
4. **`test_load_profile_exclude_region_neither_page_nor_page_from_raises`** — `{"x": 0, "y": 0, "width": 100, "height": 50}` (no page field) → `ValidationError`
5. **`test_load_profile_exclude_region_page_negative_raises`** — `{"page": -1, ...}` → `ValidationError`
6. **`test_load_profile_exclude_region_page_from_zero_raises`** — `{"page_from": 0, ...}` → `ValidationError`
7. **`test_load_profile_exclude_region_page_from_negative_raises`** — `{"page_from": -1, ...}` → `ValidationError`
8. **`test_load_profile_combined_regions_mixed_page_types`** — profile with three regions (page=1, page=0, page_from=3) loads all three correctly

Run all tests: `pytest tests/test_profile_loader.py -v`, then full suite.

**Commit: `feat: ExcludeRegion wildcard fields (page=0, page_from)`**

---

## Block 2 — Matching logic + wiring + E2E tests (Python engine)

### 2a. `filter_blocks_by_regions` (`engine/pdf_extractor.py`)

Currently checks `region.page == page_num`. Extend the matching logic:

```python
def _region_applies_to_page(region, page_num: int) -> bool:
    if region.page is not None:
        return region.page == 0 or region.page == page_num
    if region.page_from is not None:
        return page_num >= region.page_from
    return False  # should not happen after validation
```

Use this function wherever `region.page == page_num` is currently checked. Search the entire codebase for all places that match on `region.page` — there may be more than just `filter_blocks_by_regions` (e.g., `_warn_if_table_page_has_regions`, OCR masking in `ocr_extractor.py`).

### 2b. Conversion in `extract_pages_for_profile` + `regions_from_profile`

Both convert `ExcludeRegion` → `Region`. Update to pass `page_from`:

```python
Region(page=r.page, x=r.x, y=r.y, w=r.width, h=r.height, page_from=r.page_from)
```

### 2c. E2E tests

Create a synthetic multi-page PDF fixture helper (if not already available) that generates a PDF with N pages, each containing distinct text (e.g., page 1: "Header Page1 Body1", page 2: "Header Page2 Body2", etc.) where "Header" is in a known bounding box region that can be excluded.

Add to `tests/test_pdf_extractor.py` (or `test_region_filter.py` if that is more appropriate):

1. **`test_exclude_region_page_zero_applies_to_all_pages`** — 3-page PDF pair where ref and cnd differ only in a header region. Profile with `ExcludeRegion(page=0, ...)` covering that region. Expected: `has_delta is False` (header excluded on all pages).
2. **`test_exclude_region_page_from_applies_from_given_page`** — 3-page PDF pair, header differs on all pages. Profile with `ExcludeRegion(page_from=2, ...)`. Expected: page 1 header difference IS detected as delta, pages 2+3 header differences are excluded.
3. **`test_exclude_region_page_zero_and_page_from_combined`** — profile with both a `page=0` region (e.g., right margin barcode) and a `page_from=2` region (e.g., footer). Both must apply correctly.

Add E2E CLI test in `tests/test_main.py`:

4. **`test_compare_mit_profile_exclude_region_page_zero_end_to_end`** — full CLI path with JSON profile containing `page: 0`.

Add E2E batch test in `tests/test_batch_processor.py`:

5. **`test_batch_compare_mit_profile_exclude_region_page_from_end_to_end`** — full batch path with `page_from`.

Run full suite after all tests.

**Commit: `feat: exclude_regions wildcard matching (page=0, page_from)`**

---

## Block 3 — Report summary page enhancement (Python engine)

### 3a. Detailed exclude_regions listing on summary page

In `engine/report_generator.py`, find the `_build_summary_page_pdf_bytes` function (or equivalent) that generates the report summary page. Currently it shows a counter like "Ausgeschlossene Regionen: 1 (angewendet)".

Replace with a detailed listing:

**"Profil-Einstellungen"** section showing all active profile fields:
- Profil: `<filename>` (or "Kein Profil" if none)
- Vergleichsmodus: `words` / `chars` / `hybrid`
- Groß-/Kleinschreibung: `Ja` / `Nein`
- Leerzeichen-Toleranz: `Ja` / `Nein`
- Textextraktion: `native` / `reconstruct`
- OCR Referenz: `off` / `fallback` / `force` (only if profile has OCR config)
- OCR Kandidat: `off` / `fallback` / `force` (only if profile has OCR config)

**"Ausgeschlossene Regionen"** section as a small table (only if regions exist):
- Columns: Seitenbereich | x | y | Breite | Höhe
- Page display: "Seite 1", "Alle Seiten", "Ab Seite 2"
- If region_warnings exist, show them below the table

Use ReportLab `Table` with appropriate styling (consistent with existing report design). Keep it compact — this is an overview, not a separate page.

### 3b. Tests for Block 3

Add to `tests/test_report_generator.py`:

1. **`test_summary_page_shows_profile_settings`** — generate report with a profile that has non-default values (case_sensitive=False, compare_mode="hybrid", normalize_whitespace=True), extract text from page 0, assert all settings appear.
2. **`test_summary_page_shows_exclude_regions_detail`** — profile with 3 regions (page=1, page=0, page_from=2), assert the summary text contains "Seite 1", "Alle Seiten", "Ab Seite 2".
3. **`test_summary_page_without_profile_shows_defaults`** — generate report without profile, assert sensible default display.

Run full suite.

**Commit: `feat: detailed profile info on report summary page`**

---

## Block 4 — GUI profile management overhaul (TypeScript/React + Rust)

### 4a. Settings tab overhaul (`src/views/SettingsView.tsx`)

Remove:
- `normalize_whitespace` Toggle
- `compare_mode` RadioGroup
- All related state and `save_settings` calls

Add:
- **Profile directory picker**: a text field showing the currently configured directory path + a "Durchsuchen..." button that opens a native folder picker dialog (`@tauri-apps/plugin-dialog` `open` with `directory: true`)
- The selected directory path is persisted across app restarts (see Rust changes below)
- On startup, load the persisted directory and display it

### 4b. Profile dropdown in Single + Batch tabs

In both `src/views/SingleCompareView.tsx` and `src/views/BatchView.tsx`:

- Add a dropdown (`<select>`) at the top of the view, labeled "Vergleichsprofil"
- The dropdown lists all `.json` files found in the configured profile directory
- Display = filename including `.json` extension (no separate `name` field from inside the JSON)
- First option: "Kein Profil" (no profile selected, uses engine defaults)
- When the user selects a profile, store the full path and pass it to the comparison command

### 4c. Rust backend changes (`src-tauri/src/lib.rs`)

**Remove:**
- `save_settings` command (no longer needed — settings tab no longer writes a profile)
- `load_settings` command (replaced by profile directory management)
- The `Profile` struct in Rust (it was only for the settings tab)

**Add new commands:**

1. `get_profile_directory() -> Option<String>` — reads the persisted profile directory path from a config file in the app config dir
2. `set_profile_directory(path: String)` — persists the profile directory path
3. `list_profiles() -> Vec<String>` — lists all `.json` filenames in the configured profile directory (just filenames, not full paths)

**Modify existing commands:**

4. `compare_documents` — add optional `profile_name: Option<String>` parameter. If set, construct the full profile path from `profile_directory + "/" + profile_name` and pass `--profile <path>` to the sidecar. If not set, do NOT pass `--profile` (engine defaults apply). Remove the old logic that reads `settings_path`.
5. `start_batch_compare` — same change: add `profile_name: Option<String>`, construct path from profile directory + filename.

**Persistence:** Use a simple JSON file (e.g., `app_config.json`) in the app config dir with structure `{"profile_directory": "/path/to/profiles"}`. Do NOT reuse the old `profile.json` (that was an engine profile, not app config).

### 4d. TypeScript types (`src/types.ts`)

- Remove the old `Profile` interface (it was the settings-tab subset)
- Add (if needed): no new types required — the dropdown works with plain strings (filenames)

### 4e. Tests / verification

This block is primarily GUI work. Manual verification:
- Settings tab shows directory picker, persists across restart
- Single + Batch tabs show dropdown with `.json` files from the directory
- Comparison works with selected profile
- Comparison works without profile (dropdown = "Kein Profil")
- Old `normalize_whitespace` / `compare_mode` toggles are gone

No pytest changes needed for this block (it's all Tauri/React). Run `cargo check` and `npm run build` to verify compilation.

**Commit: `feat: profile directory picker + dropdown selection`**

---

## Execution order

1. Block 1 → pause → confirm → commit
2. Block 2 → pause → confirm → commit
3. Block 3 → pause → confirm → commit
4. Block 4 → pause → confirm → commit

After Block 3 is committed, remind me (Kim) about the report enhancement that was deferred from the initial discussion — this is now covered by Block 3 itself, so just confirm it is done.
