# Claude Code Prompt: Spacewidth Calibration in OCR Fallback Path

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.
Critical requirement: **everything runs exclusively locally** — no cloud, no server,
no network connections during processing.

All changes follow the project principles: TDD (test first), synthetic fixture PDFs
(never customer documents), `pytest` must be green before any commit.

Current state: 217+ tests green. Steps 1–4 of `table_regions` implemented (not yet
committed).

**Do NOT commit** — Kim commits manually after pytest verification.

---

## Problem

`engine/ocr_extractor.py::extract_pages_with_ocr_fallback` handles pages with
native text via:

```python
blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
pages_text.append(join_block_text(blocks))
```

`get_text_blocks(page)` uses PyMuPDF's `page.get_text("blocks")`, which relies on
PyMuPDF's built-in space heuristic. For Type3 fonts (Size=1.0, common in mainframe
print output), this heuristic inserts false spaces between syllable fragments:

```
"SV Spa r ka ssen V er si ch eru n g"    ← actual extraction
"SV SparkassenVersicherung"               ← visual/correct
```

The **native extraction path** (`_extract_page_text_columns`) already solves this
via `calibrate_spacewidths(doc)` + `get_text_blocks_reconstructed(page, calibration)`,
which uses rawdict character-level data to detect and remove synthetic spaces and
insert real word boundaries based on calibrated gap thresholds.

The OCR fallback path lacks this calibration entirely — it is the only native-text
extraction path that does NOT benefit from the spacewidth reconstruction.

This also directly impacts `table_regions` (Sprint PTC-S3 Task C): the
condition check `"SV SparkassenVersicherung"` fails because the extracted text
contains `"SV Spa r ka ssen V er si ch eru n g"`.

---

## Fix

In `extract_pages_with_ocr_fallback`, replace `get_text_blocks(page)` with
`get_text_blocks_reconstructed(page, calibration)` for the native-text branch.

### Detailed changes in `engine/ocr_extractor.py`:

1. **Add imports** from `engine.pdf_extractor`:
   - `calibrate_spacewidths` (already public, used by other modules)
   - `get_text_blocks_reconstructed` (already public)
   
   These can go alongside the existing imports from `pdf_extractor`
   (`_region_applies_to_page`, `filter_blocks_by_regions`, `get_text_blocks`,
   `join_block_text`). Check for circular import risk — `pdf_extractor` does
   import from `ocr_extractor`, but only lazily inside functions (not at module
   level), so module-level imports in `ocr_extractor` should be safe. If there
   IS a circular import, keep them as local imports inside
   `extract_pages_with_ocr_fallback`.

2. **Call `calibrate_spacewidths(doc)` once** before the page loop, right after
   `doc = fitz.open(pdf_path)`. This is a read-only analysis of the document's
   font metrics — no side effects, safe to call on any PDF.

3. **Replace in the native-text branch:**

   Before:
   ```python
   blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
   ```

   After:
   ```python
   blocks = filter_blocks_by_regions(
       get_text_blocks_reconstructed(page, calibration), page_num, regions
   )
   ```

   Everything downstream (`separate_table_region_blocks`, `join_block_text`)
   stays identical — `get_text_blocks_reconstructed` returns the same
   `List[TextBlock]` type as `get_text_blocks`, just with cleaner text content.

4. **Do NOT add `sort_blocks_columns` or `split_wide_blocks`** to this path.
   A previous attempt to use `_extract_page_text_columns()` in the fallback path
   worsened results (638→1253 deltas) because `sort_blocks_columns` changed
   reading order on the full page. This fix is ONLY about text quality within
   blocks, not about block ordering.

5. **OCR branch (no native text) stays unchanged** — Tesseract doesn't use
   rawdict, so spacewidth calibration is irrelevant there.

### Performance consideration

`calibrate_spacewidths(doc)` iterates all pages once to collect font metrics.
This adds one pass through the document. For the Windows VDI environment where
performance is already a concern:

- The calibration pass is read-only and lightweight (no rendering, no OCR).
- It runs once per document, not per page.
- The native extraction path already pays this cost — this just brings parity.
- Net effect should be negligible compared to actual text extraction time.

If performance is a concern, the calibration result could be cached and shared
between reference and candidate extraction, but that is a separate optimization —
do not implement caching in this task.

---

## Tests

### Unit test in `tests/test_ocr_extractor.py`:

Add a test that verifies the native-text branch of `extract_pages_with_ocr_fallback`
now uses reconstructed text (spacewidth calibration active). 

The challenge: creating a synthetic PDF with Type3 fonts that trigger the
calibration is complex. Instead, test indirectly:

1. **Monkeypatch approach:** Patch `get_text_blocks_reconstructed` in the
   `ocr_extractor` module namespace to record whether it was called (and with
   a calibration dict). Then call `extract_pages_with_ocr_fallback` on any
   PDF with native text. Assert that `get_text_blocks_reconstructed` was called
   (not `get_text_blocks`) for the native-text branch.

2. **Or use an existing fixture:** If a fixture with Type3-like fonts exists
   (e.g., TC-T-009), use it to verify that extraction produces cleaner text
   through the fallback path than it did before this change.

Choose whichever approach is simpler and more robust.

### Integration test (optional but recommended):

If TC-T-009 fixtures exist: extract via `extract_pages_with_ocr_fallback` and
compare output to `_extract_page_text_columns_reconstructed` output for the
same page. They should now produce identical text (or very similar), since both
use the same calibration + reconstruction.

### Existing tests must pass:

Run the full suite. Pay special attention to:
- `test_ocr_extractor.py` — all existing OCR tests
- `test_pdf_extractor.py` — spacewidth calibration tests
- `test_main.py` and `test_batch_processor.py` — integration tests

No existing test behavior should change. If a test relied on the OLD (uncalibrated)
extraction behavior in the fallback path, it may need its expected values updated —
but this should be rare since most tests use the native path or mock the extraction.

---

## General Rules

- **Do NOT commit.** Kim commits manually after pytest verification.
- **Do NOT add `sort_blocks_columns` or `split_wide_blocks`** to the fallback path.
  This task is ONLY about spacewidth calibration.
- **Do NOT change `pdf_extractor.py`** — all changes go into `ocr_extractor.py`
  (and tests).
- Report what you changed and the pytest result. Pause and wait for confirmation.
- Run `pytest` from the project root after changes.
