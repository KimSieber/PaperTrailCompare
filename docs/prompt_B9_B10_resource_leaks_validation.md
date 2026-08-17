# B9 + B10 — Resource Leak Fixes and Input Validation

## Context

Code review findings Rule 12 (input validation) and Rule 13 (resource release).
Both are surgical fixes with no behavioral change — only better error messages
and guaranteed resource cleanup on exceptions.

## B10 — Input Validation: file existence check at system boundary

### Problem

`extract_pages()` and `extract_text_via_ocr()` pass `pdf_path` directly to
`pymupdf.open()` without checking if the file exists. PyMuPDF raises an opaque
`RuntimeError` instead of a clear "file not found" message.

### Fix

Add a `Path(pdf_path).is_file()` check at the top of these two functions,
raising `FileNotFoundError` with a clear German message:

**`engine/pdf_extractor.py` — `extract_pages()`:**
```python
def extract_pages(pdf_path: str, ...) -> List[str]:
    if not Path(pdf_path).is_file():
        raise FileNotFoundError(f"PDF-Datei nicht gefunden: {pdf_path}")
    # ... rest unchanged
```

**`engine/ocr_extractor.py` — `extract_text_via_ocr()`:**
```python
def extract_text_via_ocr(pdf_path: str, ...) -> List[str]:
    if not Path(pdf_path).is_file():
        raise FileNotFoundError(f"PDF-Datei nicht gefunden: {pdf_path}")
    # ... rest unchanged
```

Also add the same check to `_extract_pages_reconstructed()` in
`engine/pdf_extractor.py` (same pattern, same message).

Do NOT add checks to internal functions or functions that receive already-opened
documents. Only the entry points that accept a file path string from outside.

### Tests

Add to `tests/test_pdf_extractor.py`:
```python
def test_extract_pages_raises_on_nonexistent_file():
    with pytest.raises(FileNotFoundError, match="nicht gefunden"):
        extract_pages("/does/not/exist.pdf")
```

Add to `tests/test_ocr_extractor.py`:
```python
def test_extract_text_via_ocr_raises_on_nonexistent_file():
    with pytest.raises(FileNotFoundError, match="nicht gefunden"):
        extract_text_via_ocr("/does/not/exist.pdf")
```

---

## B9 — Resource Leaks: try/finally for pymupdf.open() handles

### Problem 1: `split_batch_pdf()` in `engine/batch_processor.py`

`single_doc = pymupdf.open()` inside the loop has no try/finally. If
`insert_pdf()` or `save()` raises, the handle leaks.

### Fix 1

Wrap the inner document in try/finally:

```python
for index, group in enumerate(groups, start=1):
    # ...
    single_doc = pymupdf.open()
    try:
        single_doc.insert_pdf(src_doc, from_page=..., to_page=...)
        out_path = output_dir / f"{index:03d}_{group.name}.pdf"
        single_doc.save(str(out_path))
    finally:
        single_doc.close()
    output_paths.append(out_path)
```

### Problem 2: `generate_report()` in `engine/report_generator.py`

Four `pymupdf.open()` calls (`ref_doc`, `cnd_doc`, `report_doc`, `side_by_side`)
with sequential `.close()` at the end but no try/finally. If any operation
between open and close raises, up to four handles leak.

### Fix 2

Wrap the entire report generation body in a try/finally that closes all
opened documents. Use a list to track what needs closing, or nest try/finally
blocks. The simplest correct pattern:

```python
ref_doc = pymupdf.open(str(ref_pdf_path))
try:
    cnd_doc = pymupdf.open(str(cnd_pdf_path))
    try:
        # ... all report building logic ...
        # (report_doc and side_by_side are created and closed within this block)
    finally:
        cnd_doc.close()
finally:
    ref_doc.close()
```

For `report_doc` and `side_by_side` (created mid-function), ensure they are
also closed in a finally block or via a cleanup list. The key requirement:
no matter where an exception occurs, every opened document handle gets closed.

Do NOT change the function's return value, parameters, or behavior. Only add
resource safety.

---

## Steps

1. Implement B10 (input validation) + tests. Run `pytest -q`.
2. Implement B9 (try/finally) in `batch_processor.py` and `report_generator.py`.
   Run `pytest -q`. All tests must pass.
3. Verify: `grep -n "pymupdf.open" engine/batch_processor.py engine/report_generator.py`
   — every `pymupdf.open()` call must be inside a try/finally or context manager.

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT change any logic, parameters, or return values.
- Do NOT refactor surrounding code — keep changes minimal and focused.
- `Path` import may need to be added if not already present in affected files.
