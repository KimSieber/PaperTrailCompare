# Sprint PTC-S3 Task B: split_wide_blocks()

## Problem

PyMuPDF returns different block boundaries for visually identical multi-column
areas (footers, headers, address blocks) depending on how the source PDF's
content stream orders text-showing operations:

- **Old formatter (reference):** emits text row by row across columns →
  PyMuPDF merges all columns at the same y-band into one wide block, each
  column-cell becomes a separate "line" within that block.
- **New formatter (candidate):** emits text column by column → PyMuPDF keeps
  each column as a separate narrow block.

Result: identical visual content produces different extracted text, causing
hundreds of false deltas.

## Solution

Implement `split_wide_blocks()` — a pure function that splits blocks spanning
multiple visual columns into per-column sub-blocks, based on rawdict line
geometry. Inserted between `filter_blocks_by_regions()` and
`sort_blocks_columns()` in the extraction pipeline.

## Do NOT commit. Kim commits manually after verification.

## Constants (in engine/pdf_extractor.py, near existing _COLUMN_BUCKET_PT)

```python
_SPLIT_THRESHOLD_PT = 300    # blocks wider than this are candidates for splitting
_SPLIT_GROUP_TOLERANCE_PT = 10  # lines with x0 within this range belong to same column
```

## Function signature

```python
def split_wide_blocks(
    blocks: List[TextBlock], page: "fitz.Page"
) -> List[TextBlock]:
```

- **Input:** list of TextBlock tuples (as returned by `get_text_blocks()` or
  `get_text_blocks_reconstructed()`), plus the fitz.Page for rawdict access.
- **Output:** list of TextBlock tuples — narrow blocks pass through unchanged,
  wide blocks are replaced by per-column sub-blocks.
- The function is **pure** (no side effects) and works identically for native
  and reconstructed paths.

## Algorithm

For each block in the input list:

1. **Width check:** if `x1 - x0 <= _SPLIT_THRESHOLD_PT`, pass through unchanged.

2. **Look up rawdict lines:** use `block_no` (index 5 of the TextBlock tuple)
   to find the corresponding block in `page.get_text("rawdict")["blocks"]`.
   Get its `"lines"` list with individual line bboxes.

3. **Group lines by x0 anchor:** round each line's `bbox[0]` to the nearest
   `_SPLIT_GROUP_TOLERANCE_PT` and group. Each group = one visual column.

4. **Decision:**
   - If ≤1 group → block has no multi-column structure, pass through unchanged.
   - If ≥2 groups → split into sub-blocks.

5. **Create sub-blocks:** for each group (sorted by x0 anchor):
   - `sub_x0, sub_y0, sub_x1, sub_y1` = bounding box of all lines in group.
   - Text: take the corresponding line texts from the original TextBlock's text
     (split by `"\n"`). Match lines by index — rawdict lines and TextBlock text
     lines are in the same order.
     IMPORTANT: the TextBlock text (index 4) may have a trailing `"\n"` which
     produces an extra empty string when split. Strip empty trailing entries.
   - `block_no` = original block's block_no (index 5).
   - `block_type` = 0 (text block).

6. **Return** the complete list with wide blocks replaced by their sub-blocks.

## Text line matching (critical detail)

The TextBlock tuple's text field (index 4) contains line texts joined by `"\n"`.
These correspond 1:1 to the rawdict block's `"lines"` array (same order, same
count). To get the text for a specific rawdict line at index `i`, split the
TextBlock text by `"\n"` and take element `i`.

This works for BOTH paths:
- Native: `get_text_blocks()` uses `page.get_text("blocks")` where PyMuPDF
  joins rawdict lines with `"\n"`.
- Reconstructed: `get_text_blocks_reconstructed()` explicitly joins
  `_reconstruct_line_text()` results with `"\n"`.

## Integration (3 call sites)

### 1. `_extract_page_text_columns()` in engine/pdf_extractor.py

Current:
```python
blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
return join_block_text(sort_blocks_columns(blocks))
```

Change to:
```python
blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
blocks = split_wide_blocks(blocks, page)
return join_block_text(sort_blocks_columns(blocks))
```

### 2. `_extract_page_text_columns_reconstructed()` in engine/pdf_extractor.py

Current:
```python
blocks = filter_blocks_by_regions(
    get_text_blocks_reconstructed(page, calibration), page_num, regions
)
return join_block_text(sort_blocks_columns(blocks))
```

Change to:
```python
blocks = filter_blocks_by_regions(
    get_text_blocks_reconstructed(page, calibration), page_num, regions
)
blocks = split_wide_blocks(blocks, page)
return join_block_text(sort_blocks_columns(blocks))
```

### 3. `extract_pages_excluding_regions()` in engine/region_filter.py

Current:
```python
blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
blocks = sort_blocks_columns(blocks)
pages_text.append(join_block_text(blocks))
```

Change to:
```python
blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
blocks = split_wide_blocks(blocks, page)
blocks = sort_blocks_columns(blocks)
pages_text.append(join_block_text(blocks))
```

Import `split_wide_blocks` from `engine.pdf_extractor` in region_filter.py
(add to existing import list).

## Tests (TDD — write tests FIRST, then implement)

Add tests in `tests/test_pdf_extractor.py`. Use ReportLab to create fixture
PDFs programmatically (consistent with existing test patterns in the file).

### Test 1: Narrow blocks pass through unchanged

Create a PDF with 4 narrow text blocks (each <150pt wide, positioned at
different x-coordinates to simulate 4 columns). Call `split_wide_blocks()`.
Assert: output == input (same number of blocks, same content).

### Test 2: Wide block with multiple x0-groups is split

Create a PDF with one wide block that contains lines at different x-positions.
Use ReportLab Canvas to draw text at x=70, x=200, x=330 on the same y-line,
then more text at the same x-positions on the next y-line. PyMuPDF may or may
not merge these into one wide block — verify with `get_text_blocks()` first.

If PyMuPDF does merge them: assert `split_wide_blocks()` produces 3 sub-blocks,
one per x-anchor.

If PyMuPDF does NOT merge them (they stay as separate blocks): this test won't
trigger splitting. In that case, construct the TextBlock tuple manually with a
wide bbox and multi-column line structure to test the function in isolation.

IMPORTANT: To construct a testable scenario, it may be necessary to build the
TextBlock tuples manually AND create a matching PDF whose rawdict has the right
line geometry. The key is that `split_wide_blocks()` uses `block_no` (index 5)
to look up rawdict lines from the page. So the manually constructed TextBlock's
`block_no` must match the rawdict block index.

### Test 3: Wide block with single x0-group passes through

Create a block that is >300pt wide but all lines have the same x0 (e.g., a
wide heading). Assert: block passes through unchanged (no splitting).

### Test 4: TC-T-007 regression — multi-column layout still works

Run the existing `test_tc_t_007_mehrspaltiger_text_korrekte_lesereihenfolge`
test. It must still pass. The split should not interfere with already-narrow
column blocks.

### Test 5: Integration — split + sort produces column-ordered text

Create a PDF where text at 3 x-positions is emitted row by row (all x-positions
at y=100, then all at y=120, etc.) so PyMuPDF creates wide blocks. Extract
text with `_extract_page_text_columns()`. Assert: the resulting text is ordered
by column (all column-1 text, then column-2, then column-3), not by row.

## Workflow

1. Read existing code in `engine/pdf_extractor.py` to understand the current
   TextBlock type, constants, and function signatures.
2. Write the test cases (Red phase).
3. Implement `split_wide_blocks()` and the constant definitions.
4. Run tests — make them green.
5. Integrate at the 3 call sites.
6. Run the FULL test suite (`pytest`) to verify no regressions.
7. Do NOT commit.

## Edge cases to handle

- Blocks where rawdict lookup by `block_no` fails (e.g., image blocks were
  filtered out, shifting indices): fall back to passing block through unchanged.
- Empty lines after splitting text by `"\n"`: skip them when constructing
  sub-block text, but maintain correct index mapping to rawdict lines.
- Blocks with `block_no` that doesn't match rawdict (paranoid guard): pass
  through unchanged. Never crash.
