# Claude Code Prompt: table_regions — Whitespace-Free Condition & Comparison

## Context

PaperTrail Compare, local desktop PDF comparison app. 217+ tests green.
Steps 1–4 of `table_regions` and spacewidth calibration in the OCR fallback path
are implemented but **not yet committed**.

**Do NOT commit** — Kim commits manually after pytest verification.

---

## Problem

The `table_regions` feature (Steps 1–4) works correctly on synthetic fixtures,
but fails on real-world documents with Type3 fonts from mainframe print systems.

Type3 fonts with `Size=1.0` cause PyMuPDF to fragment words into syllables with
inserted pseudo-spaces. The spacewidth calibration (`calibrate_spacewidths`)
returns `criterion_met=False` for these fonts because the character gaps are
uniformly distributed — no distinguishable word boundary. So
`get_text_blocks_reconstructed` falls back to the native extraction, preserving
the fragmentation.

**Result on real documents:**

Extracted reference text:
```
SV Spa r ka ssen V er si ch eru n g Sitz Stuttgar t, ...
```

Extracted candidate text:
```
SV SparkassenVersicherung
```

The current condition check normalizes whitespace to single spaces but keeps
them — so `"SV SparkassenVersicherung"` (condition) is NOT a substring of
`"SV Spa r ka ssen V er si ch eru n g"` (extracted text). The condition fails
on the reference side, the `table_region` is not activated, and the footer
blocks remain in the normal sequential comparison, producing hundreds of
false deltas.

The Counter-based comparison has the same problem: even if the condition
somehow matched, `Counter(["Spa", "r", "ka", "ssen", ...])` would differ
completely from `Counter(["SparkassenVersicherung"])`.

---

## Fix: Two Changes

### Change 1: Whitespace-free Condition Check

**File: `engine/pdf_extractor.py`**, function `separate_table_region_blocks`

When checking whether the condition matches the extracted region text:

Before (current):
```python
# normalize whitespace to single spaces
normalized = " ".join(text.split())
if condition in normalized:
    ...
```

After:
```python
# For condition matching: remove ALL whitespace from both sides
text_nows = "".join(normalized.split())        # or re.sub(r'\s+', '', text)
condition_nows = "".join(condition.split())
if condition_nows in text_nows:
    ...
```

The profile still contains the human-readable condition with spaces
(`"SV SparkassenVersicherung"`). The whitespace removal happens only
internally during the match. This is transparent to the user.

**Important:** The normalized text that is STORED in `table_region_texts`
(for later comparison) should keep whitespace removed too — because the
comparison in Change 2 also operates whitespace-free. Store the
whitespace-free version: `table_region_texts[region_idx] = text_nows`.

### Change 2: Whitespace-free String Comparison

**File: `engine/table_region_comparator.py`**, function `compare_table_region`

Replace the Counter-based word comparison with a whitespace-free string
comparison:

Before (current):
```python
ref_words = ref_text.split()
cnd_words = cnd_text.split()
ref_counter = Counter(ref_words)
cnd_counter = Counter(cnd_words)
missing = ref_counter - cnd_counter
extra = cnd_counter - ref_counter
# generate deltas from missing/extra
```

After:
```python
ref_nows = "".join(ref_text.split())
cnd_nows = "".join(cnd_text.split())

if ref_nows == cnd_nows:
    return []  # identical content, no deltas

# Content differs — produce a single delta for the region
return [Delta(
    page=page_num,
    position=_NO_POSITION,
    ref_text=ref_text,      # keep readable version with spaces for report
    cnd_text=cnd_text,
)]
```

**Wait — the readable version:** Since Change 1 stores the whitespace-free
text in `table_region_texts`, the `ref_text` and `cnd_text` passed to
`compare_table_region` will already be whitespace-free. For the delta
output (which the user sees in the report), we want readable text.

Two options:
- **Option A:** Store BOTH versions in `table_region_texts` — whitespace-free
  for comparison, whitespace-normalized (single spaces) for display.
- **Option B:** Store only whitespace-free. In `compare_table_region`, if a
  delta is produced, the ref/cnd text is the whitespace-free string. Not
  ideal for readability but functional.

**Choose Option A** — readability in reports matters for testers who don't
know the profile settings (Kim's requirement). The simplest implementation:
change `table_region_texts` value type from `str` to a tuple `(str, str)`
where `[0]` = whitespace-free (for comparison) and `[1]` = whitespace-
normalized with single spaces (for display in deltas).

Update `merge_table_region_comparison` and `compare_table_region` signatures
accordingly.

### Impact on `merge_table_region_comparison`

In `engine/table_region_comparator.py`, the shared helper
`merge_table_region_comparison` currently passes `ref_text` and `cnd_text`
from `table_region_texts` dicts to `compare_table_region`. Update it to
unpack the tuple: use `[0]` (whitespace-free) for comparison, pass `[1]`
(readable) to `compare_table_region` for delta display.

Update `compare_table_region` signature to accept both:

```python
def compare_table_region(
    ref_text_nows: str,       # whitespace-free, for comparison
    cnd_text_nows: str,       # whitespace-free, for comparison
    ref_text_display: str,    # readable, for delta output
    cnd_text_display: str,    # readable, for delta output
    page_num: int,
    region_index: int,
) -> List[Delta]:
```

---

## Tests to Update

### `tests/test_table_region_comparator.py`

All 10 existing tests need updating because:
- `compare_table_region` signature changes (4 text params instead of 2)
- Comparison logic changes from Counter to string comparison
- Some test cases may need different expectations

**Update each test:**
- Pass both `_nows` and `_display` versions of the text
- "Word order different but same words" test: still expects no deltas
  (whitespace-free strings are identical regardless of word order)
- "One word missing" test: now produces ONE delta (with the full region text),
  not per-word deltas
- Adjust expected delta content accordingly

### `tests/test_pdf_extractor.py`

Tests for `separate_table_region_blocks` need updating:
- Return value changes from `Dict[int, str]` to `Dict[int, Tuple[str, str]]`
- Add a test with Type3-like fragmented text where condition matches only
  after whitespace removal

### `tests/test_main.py` and `tests/test_batch_processor.py`

Integration tests (TC-TR-001, TC-TR-002) may need expected value adjustments
if the delta format changed. The key assertions remain:
- TC-TR-001 (same content, different blocks): `has_delta: False`
- TC-TR-002 (genuinely different content): `has_delta: True`

### New test: Fragmented Text Condition Match

Add a test in `test_pdf_extractor.py` that creates a synthetic PDF with
fragmented text (multiple small `drawString` calls for syllables of one word)
in a footer region, and verifies that the condition `"SV SparkassenVersicherung"`
matches despite the extraction producing `"SV Spa r ka ssen V er si ch eru n g"`.

Use ReportLab's `canvas.drawString()` to place individual syllable fragments
at slightly spaced x-positions to simulate Type3 fragmentation:

```python
c.drawString(50, 50, "SV")
c.drawString(70, 50, "Spa")
c.drawString(85, 50, "r")
c.drawString(90, 50, "ka")
c.drawString(100, 50, "ssen")
# ... etc.
```

This may or may not produce the exact same fragmentation as real Type3 PDFs
(depends on PyMuPDF's block merging heuristic), so validate the fixture's
extracted text first before asserting. If the fragments get merged by PyMuPDF,
adjust spacing until they don't, or use a different approach (e.g., multiple
text objects with invisible separators).

If creating a realistic fixture proves too complex, a monkeypatch test is
acceptable: mock `get_text_blocks_reconstructed` to return blocks with
pre-fragmented text, then verify `separate_table_region_blocks` matches
the condition correctly.

---

## General Rules

- **Do NOT commit.** Kim commits manually after pytest verification.
- **Do NOT change** `pdf_extractor.py` beyond `separate_table_region_blocks`
  and its direct callers within that file.
- **Do NOT change** block ordering, `sort_blocks_columns`, or
  `split_wide_blocks` behavior.
- **Backward compatibility:** Profiles without `table_regions` continue
  to work unchanged.
- Report what you changed and the pytest result. Pause and wait for
  confirmation before Kim does a GUI test.
- Run `pytest` from the project root after changes.
