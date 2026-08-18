# B11 + B12 — Shared Comparison Logic and Batch Error Handling

## Context

PaperTrail Compare, Python engine. 246 tests green. Two code review findings:

- **B12 (Rule 2 — Redundancy):** `_compare_pair()` in `batch_processor.py`
  duplicates the extraction→compare→merge→sort sequence from `_run_compare()`
  in `__main__.py`. Both unpack the same profile fields, call the same
  functions in the same order, and assemble results identically.

- **B11 (Rule 11 — Error handling):** `_compare_pair()` does not wrap
  `extract_pages_for_profile()` or `compare()` in try/except. A corrupt PDF
  or unexpected extraction error propagates as an unhandled exception, crashing
  the entire batch run instead of recording the pair as `status="error"`.

Both are fixed together: extract the shared logic into a new module, then add
error handling at the call site.

## Goal

1. Create `engine/comparison.py` with a shared `run_comparison()` function.
2. Refactor `_compare_pair()` and `_run_compare()` to call it.
3. Add try/except in `_compare_pair()` so corrupt PDFs produce
   `PairResult(status="error")` instead of crashing the batch.

## Step 1 — Create `engine/comparison.py`

### New file with file header

```python
# file:    engine/comparison.py
# purpose: Shared comparison logic used by both CLI single comparison
#          (__main__._run_compare) and batch processing
#          (batch_processor._compare_pair). Single source of truth for
#          the extraction→compare→merge→sort pipeline.
# author:  Kim Sieber
# created: 2026-08-17
# changed: 2026-08-17
```

### New dataclass for the return value

```python
@dataclass
class ComparisonOutput:
    """Result of a single ref/cnd comparison including all metadata needed
    by both CLI and batch callers."""
    result: CompareResult
    total_pages: int
    ref_ocr_used: bool
    cnd_ocr_used: bool
    region_warnings: List[str]
    duration_seconds: float
```

### `run_comparison()` function

Extract the shared pipeline from `_run_compare()` / `_compare_pair()`:

```python
def run_comparison(
    ref_path: str,
    cnd_path: str,
    profile: Optional[Profile],
) -> ComparisonOutput:
```

The function does exactly this sequence (taken from the current code in both
callers — verify each step matches the current implementation):

1. `region_warnings: List[str] = []`
2. `start = time.perf_counter()`
3. `extract_pages_for_profile(ref_path, profile, role="reference", warnings=region_warnings)`
   → `ref_pages, ref_ocr_used, ref_tr_texts`
4. `extract_pages_for_profile(cnd_path, profile, role="candidate", warnings=region_warnings)`
   → `cnd_pages, cnd_ocr_used, cnd_tr_texts`
5. `compare(ref_pages, cnd_pages, ...)` with all profile parameters
   (case_sensitive, normalize_whitespace, ocr_used, compare_mode,
   merge_hyphenation, normalize_orphan_hyphens) — use the same
   `if profile else <default>` pattern as the current code.
6. `merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)`
   → merge deltas into result if any.
7. Sort deltas stably by page: `sorted(result.deltas, key=lambda d: d.page)`
8. `duration_seconds = time.perf_counter() - start`
9. `total_pages = max(len(ref_pages), len(cnd_pages))`
10. Return `ComparisonOutput(...)`.

The function does NOT:
- Check file existence (caller's responsibility)
- Handle exceptions (caller's responsibility)
- Generate reports (caller's responsibility)
- Print warnings (caller's responsibility — warnings are returned in the output)
- Do any I/O besides PDF reading

**IMPORTANT:** Before implementing, read the CURRENT code in both
`__main__.py::_run_compare()` and `batch_processor.py::_compare_pair()` line
by line. If they have diverged in any detail (different parameters, different
merge logic, different field unpacking), reconcile them in `run_comparison()`
and document the difference in a code comment.

## Step 2 — Refactor `_run_compare()` in `__main__.py`

Replace the extraction→compare→merge→sort block with:

```python
from engine.comparison import run_comparison

# ... (profile loading stays here) ...

try:
    output = run_comparison(args.ref_pdf, args.cnd_pdf, profile)
except Exception as exc:
    print(str(exc), file=sys.stderr)
    return 1

for warning in output.region_warnings:
    print(f"Warnung: {warning}", file=sys.stderr)

result = output.result
# ... (report generation, JSON output etc. stay here, using output.duration_seconds) ...
```

Keep all CLI-specific logic (argument parsing, JSON output, report generation,
exit codes) in `_run_compare()`. Only the comparison pipeline moves out.

## Step 3 — Refactor `_compare_pair()` in `batch_processor.py`

Replace the extraction→compare→merge→sort block with:

```python
from engine.comparison import run_comparison

def _compare_pair(ref_path, cnd_path, profile, report_dir=None):
    # File existence check stays here (already implemented)
    ref_file = Path(ref_path)
    cnd_file = Path(cnd_path)
    missing = [str(p) for p in (ref_file, cnd_file) if not p.is_file()]
    if missing:
        return PairResult(
            ref_path=ref_path, cnd_path=cnd_path, status="error",
            error=f"Datei(en) nicht gefunden: {', '.join(missing)}",
        )

    # B11: try/except so a corrupt PDF doesn't crash the entire batch
    try:
        output = run_comparison(ref_path, cnd_path, profile)
    except Exception as exc:
        return PairResult(
            ref_path=ref_path, cnd_path=cnd_path, status="error",
            error=str(exc),
        )

    for warning in output.region_warnings:
        print(f"Warnung ({ref_path} / {cnd_path}): {warning}", file=sys.stderr)

    # Report generation stays here
    if report_dir is not None:
        report_path = _unique_report_path(Path(report_dir), ref_file, cnd_file)
        generate_report(
            output.result, ref_file, cnd_file, report_path,
            profile=profile, region_warnings=output.region_warnings,
            duration_seconds=output.duration_seconds,
        )

    return PairResult(
        ref_path=ref_path, cnd_path=cnd_path, status="ok",
        compare_result=output.result, total_pages=output.total_pages,
    )
```

## Step 4 — Tests

### 4a. Unit test for `run_comparison()` in a new `tests/test_comparison.py`

```python
def test_run_comparison_identical_pdfs_no_delta(tmp_path):
    """Basic smoke test: identical PDFs → no delta."""
    # Create two identical single-page PDFs via ReportLab
    # Call run_comparison() without profile
    # Assert: result.has_delta is False, total_pages == 1, duration > 0

def test_run_comparison_different_pdfs_has_delta(tmp_path):
    """Different content → delta detected."""
    # Create ref with "Hallo Welt", cnd with "Hallo Mond"
    # Assert: result.has_delta is True

def test_run_comparison_with_profile(tmp_path):
    """Profile parameters are threaded through correctly."""
    # Create ref "ABC", cnd "abc"
    # With Profile(case_sensitive=False) → no delta
    # Without profile (default case_sensitive=True) → delta
```

### 4b. Batch error handling test in `tests/test_batch_processor.py`

```python
def test_compare_pair_corrupt_pdf_returns_error_status(tmp_path):
    """B11: A corrupt/unreadable PDF must not crash the batch.
    _compare_pair must return PairResult(status='error') with the
    error message, not raise an exception."""
    # Create a valid ref PDF
    # Create a corrupt cnd file (write random bytes to a .pdf file)
    # Call _compare_pair(ref, corrupt, None)
    # Assert: result.status == "error"
    # Assert: result.error is not None and len(result.error) > 0
    # Assert: result.compare_result is None
```

```python
def test_batch_compare_continues_after_corrupt_pdf(tmp_path):
    """B11: A batch with one corrupt PDF among valid pairs must complete
    all other pairs successfully."""
    # Create 3 pairs: pair 1 valid, pair 2 corrupt cnd, pair 3 valid
    # Write filelist CSV
    # Call batch_compare(filelist)
    # Assert: result.ok_count == 2
    # Assert: result.error_count == 1
    # Assert: pairs[1].status == "error"
```

### 4c. Run full suite

```bash
PYTHONPATH=. python -m pytest -q
```

All existing tests must pass. The refactoring must not change any behavior —
same inputs, same outputs, same side effects.

## Step 5 — Cleanup verification

```bash
# Verify no leftover direct compare() calls in __main__ or batch_processor
# (except in run_comparison itself):
grep -n "from engine.text_comparator import" engine/__main__.py engine/batch_processor.py
grep -n "compare(" engine/__main__.py engine/batch_processor.py
```

`__main__.py` and `batch_processor.py` should no longer import or call
`compare()` directly — they go through `run_comparison()`. They may still
import `CompareResult` or `Delta` for type annotations or serialization.

Also verify `merge_compare_region_comparison` is no longer called directly
from `__main__.py` or `batch_processor.py` — it moves into `run_comparison()`.

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT change the function signatures of `_run_compare()`, `_compare_pair()`,
  `batch_compare()`, or any Tauri-facing command.
- Do NOT change report generation logic — it stays in the callers.
- Do NOT change JSON output format or CLI behavior.
- The `_compare_pair_worker()` wrapper for multiprocessing stays unchanged.
- Add the standard file header to `engine/comparison.py` and
  `tests/test_comparison.py`.
