# Claude Code Prompt: Bug-Fix — Batch Progress Display Regression

## Context

PaperTrail Compare, local desktop PDF comparison app (Tauri + React/TS + Python
engine). 219+ tests green. The following uncommitted changes are in the working
tree: `table_regions` (Steps 1–4), spacewidth calibration in OCR fallback path,
whitespace-free condition check and comparison.

**Do NOT commit** — Kim commits manually after pytest verification.

---

## Bug Report (from manual GUI testing)

During a batch run via the GUI:
- The batch result list is NOT displayed anymore (previously showed one row per pair)
- The progress counter does NOT increment anymore ("1 von 14", "2 von 14", ...)
- BUT: the comparison itself works — all report files are created, and at the
  end "14 ok" is displayed

This worked correctly before the recent changes. The regression must have been
introduced by one of the uncommitted changes, most likely in
`engine/batch_processor.py` (`_compare_pair` was modified to merge table_region
deltas via `dataclasses.replace()`).

## How the GUI progress mechanism works (investigate and confirm)

The Tauri GUI spawns the Python sidecar for batch processing and parses its
stdout line by line. Progress updates are emitted as JSON lines (one JSON object
per line) during processing, which the GUI uses to update the counter and the
result list incrementally. The final summary is a separate JSON output.

**Investigate:** Read `engine/batch_processor.py` and `engine/__main__.py` to
understand exactly how progress lines are emitted (which function, what format,
when flushed). Then read the recent changes (git diff against HEAD) to find what
broke the emission.

## Likely causes to check (in order of probability)

1. **Exception swallowed per pair:** If the merge logic in `_compare_pair`
   raises an exception (e.g., `TypeError` from the tuple change in
   `table_region_texts`, or `dataclasses.replace()` on an unexpected type),
   and there's a try/except around the pair processing that catches it, the
   progress line might be skipped while the pair still completes via a
   fallback path.

2. **Changed stdout format:** If the merge changed the structure of the
   per-pair progress JSON (new fields, changed types, non-serializable
   objects like tuples where the GUI expects strings), the GUI might fail to
   parse the lines silently and thus not update.

3. **Buffering:** If something in the new code path writes to stdout without
   flushing, or prints non-JSON content to stdout (e.g., a stray debug print,
   a warning), the GUI's line parser might break on the first malformed line
   and stop processing subsequent progress updates.

4. **`ref_tr_texts`/`cnd_tr_texts` unpacking:** The return-arity change of
   `extract_pages_for_profile` (2-tuple → 3-tuple) — check that ALL call
   sites in `batch_processor.py` unpack correctly. A partially-updated call
   site could raise, get caught, and silently degrade.

## Fix procedure

1. **Reproduce first:** Run the batch CLI directly (not through the GUI):
   ```
   python -m engine batch --input-dir <fixture-dir> --profile <profile> --output-dir /tmp/test-batch
   ```
   Use existing test fixtures (e.g., copy TC-TR-001 ref/cnd pairs into a batch
   input structure matching the expected naming convention — check how batch
   pairs are discovered).
   
   Capture stdout completely. Compare the emitted lines against what the GUI
   expects (check the Rust/TS side: `src-tauri/src/lib.rs` for how batch
   stdout is parsed and which events are forwarded to the frontend — READ ONLY,
   do not modify Rust code).

2. **Identify the exact divergence:** malformed JSON line? missing progress
   lines? exception traceback mixed into stdout?

3. **Fix in Python only** (`engine/batch_processor.py` / `engine/__main__.py`).
   Do NOT modify Rust or TypeScript code. If the root cause turns out to be
   in the Rust/TS layer, STOP and report — do not fix it yourself.

4. **Add a regression test** in `tests/test_batch_processor.py` that validates
   the stdout progress contract: run a small batch programmatically, capture
   stdout, assert that:
   - One valid JSON progress line per pair is emitted
   - Progress lines appear BEFORE the final summary
   - Each progress line contains the expected fields (pair index, total,
     status/filename — match the actual contract you discovered in step 1)
   
   This test locks the contract so future engine changes can't silently break
   the GUI again.

## Report requirements

Report BEFORE fixing:
- The exact root cause (with the specific line/change that broke it)
- The stdout diff (what was emitted before vs. now)

Then fix, run pytest, and report the result.

## General Rules

- **Do NOT commit.**
- **Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.**
- **Do NOT change table_regions logic** in this task — only fix the progress
  emission. If the root cause is IN the table_regions merge logic (e.g., an
  exception), fix the exception handling/serialization, not the feature logic.
- Run `pytest` from the project root after changes.
