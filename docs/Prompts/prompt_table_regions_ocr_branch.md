# Claude Code Prompt: table_regions in the OCR Branch

## Context

PaperTrail Compare, local desktop PDF comparison app (Tauri + React/TS + Python
engine). 220 tests green. Uncommitted in the working tree: `table_regions`
(Steps 1–4), spacewidth calibration in the OCR fallback path, whitespace-free
condition check/comparison, batch progress sentinel fix (`_NO_POSITION = 0`).

**Do NOT commit** — Kim commits manually after pytest verification.

---

## Problem (root cause found via real-document diagnosis)

Kim's real reference PDFs are **pure bitmap PDFs**: 0 fonts, 0 native text,
~1800 image blocks per page (each glyph/syllable is a small embedded image —
classic mainframe print output). These pages inevitably go through the **OCR
branch** of `extract_pages_with_ocr_fallback`.

The `table_regions` feature (Step 2) was only implemented in the **native-text
branch**. The OCR branch deliberately returns an empty dict:
"OCR'd pages (no native text) get an empty dict."

Consequence: on the reference side, `table_region_texts` is never populated →
the condition can never match on both sides → the feature is completely
inactive for Kim's real documents. All GUI tests failed for this reason, not
because of coordinates (verified: candidate footer blocks sit at y=739–811,
x=70–553 on A4 595×842 — Kim's region coordinates are fine).

## Goal

Implement `table_region` separation in the OCR branch of
`extract_pages_with_ocr_fallback` so that image-based pages participate in the
feature exactly like native-text pages:

- For each applicable `table_region` (page/page_from rules): obtain the text
  inside the region via OCR
- Whitespace-free condition check (same semantics as the native path)
- On match: exclude the region's content from the page's main OCR text and
  store the `(text_nows, text_display)` tuple in `table_region_texts`
- On no-match: page text stays complete, nothing stored

## Recommended design: crop + mask (investigate, then confirm or propose better)

The OCR branch already has region machinery: `_mask_regions_on_image` masks
exclude regions on the rendered page image before OCR (with PDF-point → pixel
coordinate scaling via the render zoom factor). Reuse this pattern:

1. **Render the page once** to a pixmap (as the OCR branch already does).
2. For each applicable `table_region`:
   a. **Crop** the region rectangle from the rendered image (scale PDF points
      → pixels with the same zoom factor `_mask_regions_on_image` uses).
   b. **OCR the crop** (same Tesseract config/lang as the main OCR call).
   c. Normalize the crop text (single spaces) → `display`; strip all
      whitespace → `nows`; run the whitespace-free condition check.
   d. On match: record `(nows, display)` under the region index AND **mask the
      region on the main page image** (same mechanism as
      `_mask_regions_on_image`) so the subsequent full-page OCR does not
      contain the region text.
3. **Run the main full-page OCR** on the (possibly masked) image, as before.

Why crop+mask instead of `image_to_data` word-box bookkeeping:
- Reuses existing, tested masking machinery and coordinate scaling
- No fragile word-to-region assignment on OCR word boxes
- The extra OCR call per region is cheap (small crop) — acceptable even on
  the slow Windows VDI target

**Before implementing:** read the OCR branch and `_mask_regions_on_image`
carefully. If the actual code structure suggests a materially better approach
(e.g., a single `image_to_data` pass is already available), STOP and report
your alternative with reasoning before writing code.

## Shared condition-check helper

The whitespace-free condition check currently lives inline in
`separate_table_region_blocks` (`pdf_extractor.py`). Extract it into a small
shared helper so both paths use identical semantics, e.g. in `pdf_extractor.py`:

```python
def check_table_region_condition(text: str, condition: str) -> Optional[Tuple[str, str]]:
    """Whitespace-free condition check. Returns (text_nows, text_display)
    when the condition matches, else None."""
```

Use it from both `separate_table_region_blocks` and the new OCR-branch code.
Keep behavior byte-identical to the current implementation (case-sensitive,
substring on whitespace-free strings; display = single-space-normalized).

## Constraints & details

- **Coordinate scaling:** `table_region` coordinates are PDF points. The
  rendered image is in pixels. Use the exact same zoom/scale computation as
  `_mask_regions_on_image` — do not introduce a second, slightly different
  scaling path.
- **Order of operations:** exclude_regions masking runs FIRST (existing
  behavior), table_region crops are taken from the already-exclude-masked
  image. This preserves the agreed rule: exclude wins first, a table_region
  overlapping an exclude region sees reduced text and produces deltas —
  never silent ignoring.
- **`ocr_used` flag:** unchanged semantics. Do not touch the GUI-facing
  "OCR: Nein" display bug (separate backlog item).
- **Tesseract config:** use the same language/config as the existing main
  OCR call (German, vendored tessdata). Do not add new Tesseract parameters.
- **Do NOT change** the native-text branch, `sort_blocks_columns`,
  `split_wide_blocks`, or the comparison/merge logic — they already work.
- **Performance:** one page render, N small crop OCRs (N = matching regions,
  typically 0–1), one full-page OCR. Do not render the page twice.

## Tests

Follow the existing test patterns in `tests/test_ocr_extractor.py` for
Tesseract availability (check how existing OCR tests are marked/skipped when
Tesseract is missing, and follow the same convention).

1. **Fixture:** create a bitmap-PDF fixture pair (new TC, e.g. TC-TR-003):
   render a text page (body + footer with known multi-word footer text) to an
   image and embed it as a full-page image in a PDF (ReportLab `drawImage` or
   PyMuPDF `insert_image`). The page must have NO native text — verify
   `page.get_text() == ""` in the generator or test. The candidate side can be
   a native-text PDF with the same footer wording (mixed bitmap-ref /
   native-cnd — exactly Kim's real-world constellation).
2. **Unit test:** OCR branch populates `table_region_texts` when the condition
   matches inside the region (use the fixture; assert the tuple shape and that
   the footer words appear in `display`).
3. **Unit test:** condition not matching → empty dict entry for that region,
   full page text unchanged (contains the footer words).
4. **Integration test** (`test_main.py` or `test_batch_processor.py`): the
   mixed pair (bitmap ref, native cnd) with a matching `table_region` and
   identical footer wording → `has_delta: False` for the footer. With a
   genuinely different word in the candidate footer → `has_delta: True`.
   (OCR noise caveat: if Tesseract output on the synthetic fixture is not
   stable enough for a strict `has_delta: False` assertion, report this
   honestly and propose how to make the fixture OCR-stable — e.g., larger
   font size, higher contrast — rather than weakening the assertion.)
5. **Regression:** full suite green; the stdout-contract test from the batch
   progress fix must still pass.

## Workflow

Work in two steps with a pause between:
- **Step 1:** Investigation report (OCR branch structure, masking/scaling
  reuse points, confirm or challenge the crop+mask design) + shared helper
  extraction + fixture generator. Run pytest, report, WAIT.
- **Step 2:** OCR-branch implementation + tests. Run pytest, report.

## General Rules

- **Do NOT commit.**
- **Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.**
- Report findings and pytest results after each step; wait for confirmation.
