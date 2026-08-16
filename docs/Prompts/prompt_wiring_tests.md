# Prompt: E2E wiring tests for all Profile options

## Goal

Add missing end-to-end wiring tests so that every behavior-relevant field in the `Profile` dataclass (`engine/profile_loader.py`) is covered by at least one test that exercises the **full production path** — not just the function in isolation.

Background: The project had a wiring bug where `exclude_regions` was loaded/validated in the profile and displayed as a counter on report page 1, but had zero effect on text extraction because the function was never called. Unit tests were green because they tested the function directly. This pattern must be prevented for all fields.

## Rules

- **TDD**: Write the test first, verify it collects (`pytest --collect-only`), then run it.
- Run each new test individually with `pytest tests/<file>.py::<testname> -v` before writing the next one.
- At the end run the full `pytest` suite — all 139+ existing tests must remain green.
- Do not modify or delete any existing tests.
- Target files: `tests/test_main.py` (CLI path) and `tests/test_batch_processor.py` (batch path).
- Every test generates its own synthetic PDF fixtures via ReportLab (`reportlab.pdfgen.canvas`). Do not access `tests/fixtures/TC_REAL/`.

## Existing patterns to follow

Use these already-existing tests as templates:

### CLI E2E (test_main.py)
- `test_compare_mit_profile_compare_mode_chars_end_to_end` — creates two synthetic PDFs, writes a JSON profile to `tmp_path`, calls `main(["compare", ...])`, asserts on `payload["has_delta"]`.
- `test_compare_mit_profile_exclude_regions_end_to_end_tc_e_001` — same pattern with `exclude_regions`.

### CLI Spy (test_main.py)
- `test_compare_ruft_compare_mit_profile_compare_mode_auf` — patches `compare` via `monkeypatch.setattr`, asserts the parameter arrives.

### Batch E2E (test_batch_processor.py)
- `test_batch_compare_mit_profile_exclude_regions_end_to_end_tc_e_002` — writes a CSV with one pair, calls `batch_compare(filelist, profile=...)`, asserts on `pair.compare_result`.
- `test_batch_compare_reicht_profile_compare_mode_an_compare_durch` — spy test at batch level.

## Tests to create

### Block 1: `case_sensitive` (CLI + Batch)

**Test logic:** Two PDFs with identical content except for capitalization.
- ref.pdf: `"Die Rechnung wurde versendet."`
- cnd.pdf: `"die rechnung wurde versendet."`
- Profile: `{"version": "1.0", "case_sensitive": false}`
- Expected: `has_delta is False`, `deltas == []`
- Counter-check (optional, same test or separate): without `case_sensitive: false` (default = true) a delta must be detected.

**Tests:**
1. `test_compare_mit_profile_case_sensitive_false_end_to_end` in `test_main.py`
2. `test_batch_compare_mit_profile_case_sensitive_false_end_to_end` in `test_batch_processor.py`

### Block 2: `normalize_whitespace` (Batch, possibly CLI)

First check whether `test_compare_mit_profile_normalize_whitespace_end_to_end` already exists in `test_main.py`. If yes, only add the batch test. If no, add both.

**Test logic:**
- ref.pdf: `"Die Vertragsbedingungen gelten sofort."`
- cnd.pdf: `"Die Vertrags bedingungen gelten sofort."` (extra space)
- Profile: `{"version": "1.0", "normalize_whitespace": true}`
- Expected: `has_delta is False`

**Tests:**
3. (only if missing) `test_compare_mit_profile_normalize_whitespace_end_to_end` in `test_main.py`
4. `test_batch_compare_mit_profile_normalize_whitespace_end_to_end` in `test_batch_processor.py`

### Block 3: `text_extraction` (CLI E2E + CLI Spy + Batch Spy)

**E2E test logic:** Same text in both PDFs, profile with `text_extraction: "reconstruct"`, result must be `has_delta is False`.
- ref.pdf: `"Der Vertrag gilt ab sofort."`
- cnd.pdf: `"Der Vertrag gilt ab sofort."` (identical)
- Profile: `{"version": "1.0", "text_extraction": "reconstruct"}`
- Expected: `has_delta is False`, `deltas == []`

**Spy test logic (CLI + Batch):** Patch `extract_pages_for_profile` via monkeypatch and assert that the received `profile` object has `text_extraction == "reconstruct"`.

**Tests:**
5. `test_compare_mit_profile_text_extraction_reconstruct_end_to_end` in `test_main.py`
6. `test_compare_reicht_text_extraction_reconstruct_an_extract_pages_for_profile` in `test_main.py` (spy)
7. `test_batch_compare_reicht_text_extraction_reconstruct_durch` in `test_batch_processor.py` (spy)

### Block 4: `ocr.mode_reference` / `ocr.mode_candidate` (CLI + Batch)

**Synthetic image-PDF helper:**

Create a helper function `_write_image_pdf(path: Path, text: str)` that:
1. Uses Pillow (`PIL.Image`, `PIL.ImageDraw`) to create a white image (e.g. 800×200 px)
2. Renders the given text in black at large font size (~36pt) so Tesseract can read it reliably
3. Embeds the image as a PDF page via ReportLab (`canvas.drawImage` with `ImageReader`)

Place this helper in `test_main.py` and duplicate it in `test_batch_processor.py` (keep test files independent).

**Test logic:**
- ref.pdf: Image-PDF with text `"Tesseract OCR Pruefung"` (no umlauts, simple words for reliable recognition)
- cnd.pdf: Normal text-PDF with `"Tesseract OCR Pruefung"` (identical text via `canvas.drawString`)
- Profile: `{"version": "1.0", "ocr": {"enabled": true, "mode_reference": "force", "mode_candidate": "off", "dpi": 300}}`
- Expected: `has_delta is False` — the OCR-read reference text must match the native candidate text
- Note: use `dpi: 300` for higher OCR quality

**Tests:**
8. `test_compare_mit_ocr_mode_reference_force_end_to_end` in `test_main.py`
9. `test_batch_compare_mit_ocr_mode_reference_force_end_to_end` in `test_batch_processor.py`

## Technical notes

- `_write_single_page_pdf(path, text)` already exists in both test files — use it for text-PDFs.
- Imports you will likely need (check what is already imported in each file):
  - `from engine.__main__ import main` (test_main.py)
  - `from engine.batch_processor import batch_compare` (test_batch_processor.py)
  - `from engine.profile_loader import Profile, OcrConfig` (for spy tests with Profile objects)
  - `from PIL import Image, ImageDraw` (for image-PDF generation)
  - `from reportlab.lib.utils import ImageReader` (for embedding image in PDF)
  - `import json, io`
- OCR tests may take a few seconds longer — that is OK.
- Tesseract with `deu` language pack is installed on the development machine.
- All test data is created under `tmp_path` (pytest fixture).
- Image text for OCR test deliberately kept simple: no umlauts, no special characters, large font, simple words.

## Execution order

1. Block 1 (case_sensitive) — both tests
2. Block 2 (normalize_whitespace) — batch test (check CLI first)
3. Block 3 (text_extraction) — E2E + spy tests
4. Block 4 (OCR) — both tests
5. Final step: run full `pytest` suite

## Expected outcome

All new tests green, all existing 139 tests still green. Total count after completion: approx. 148–150 tests.
