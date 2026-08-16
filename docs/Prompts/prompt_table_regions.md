# Claude Code Prompt: Sprint PTC-S3 Task C — `table_regions` (Multiset Word Comparison)

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.
Critical requirement: **everything runs exclusively locally** — no cloud, no server,
no network connections during processing.

All changes follow the project principles: TDD (test first), synthetic fixture PDFs
(never customer documents), `pytest` must be green before any commit.

Current state: 185+ tests green. Bug-fix sprint (region consolidation) completed.

**Do NOT commit** — Kim commits manually after pytest verification.

---

## Problem

Multi-column footers (e.g., "SV SparkassenVersicherung" 4-column footer blocks)
produce hundreds of false deltas because PyMuPDF delivers different block boundaries
for the same visual content: the reference PDF has one wide block per line spanning
all columns, the candidate PDF has one narrow block per column. The text content is
identical, but sequential comparison fails because word order diverges.

Previous attempts to fix this via block splitting (`split_wide_blocks`) and column
sorting were insufficient — Type3 font fragmentation and rawdict line boundaries
made the problem worse on the actual execution path (`ocr_extractor` fallback).

## Solution: `table_regions`

A new profile-configurable region type that applies **multiset (Counter) word
comparison** instead of sequential diff to defined page areas. The comparison
ignores word order entirely — only word presence and frequency matter. This
eliminates false deltas caused by differing block structures while still catching
genuine content differences (missing words, extra words, changed words).

---

## Architecture Overview

```
Pipeline order (inside extract_pages_for_profile / per page):

  1. get_text_blocks(page)
  2. filter_blocks_by_regions(...)          ← exclude_regions (existing)
  3. separate_table_region_blocks(...)      ← NEW: table_regions
     ├── blocks in matching table_region   → collected separately
     └── remaining blocks                  → continue to step 4
  4. split_wide_blocks → sort_blocks_columns → join_block_text  (existing)

After extraction (both PDFs):

  5. For each page pair where BOTH sides have table_region text:
     → Counter comparison (table_region_comparator)
     → synthetic Delta objects

  6. Remaining page text (without table_region blocks):
     → normal sequential comparison via text_comparator (existing)

  7. Merge deltas from steps 5 + 6 into single result
```

---

## Step 1: Profile Loader — `table_regions` Configuration

### File: `engine/profile_loader.py`

**Add a new dataclass** `TableRegion` with the same coordinate/page fields as
`ExcludeRegion` plus a `condition` string:

```python
@dataclass
class TableRegion:
    x: float
    y: float
    width: float
    height: float
    condition: str            # whitespace-normalized substring match
    page: Optional[int] = None
    page_from: Optional[int] = None
```

**Validation rules** (inside `load_profile`):
- Same `page` / `page_from` mutual-exclusivity rules as `ExcludeRegion`
  (exactly one must be set; `page=0` = all pages; `page_from >= 1`).
- `condition` must be a non-empty string.
- `condition` must be at least 2 words (split by whitespace) — a single word
  is too ambiguous for reliable matching. Raise `ValidationError` if fewer
  than 2 words.
- Coordinates must be non-negative, `width` and `height` must be positive.

**Add `table_regions` to `Profile`:**

```python
@dataclass
class Profile:
    # ... existing fields ...
    table_regions: List[TableRegion] = field(default_factory=list)
```

**JSON format example:**

```json
{
  "version": "1.0",
  "table_regions": [
    {
      "page": 0,
      "x": 50, "y": 750, "width": 500, "height": 80,
      "condition": "SV SparkassenVersicherung"
    }
  ]
}
```

### Tests (in `tests/test_profile_loader.py`):
- Valid `table_regions` loads correctly (single region, multiple regions)
- `page=0` wildcard works
- `page_from` works
- Both `page` and `page_from` set → `ValidationError`
- Neither `page` nor `page_from` set → `ValidationError`
- Empty `condition` → `ValidationError`
- Single-word `condition` → `ValidationError`
- Missing `condition` field → `ValidationError` (KeyError)
- `table_regions` absent from JSON → defaults to empty list (backward compat)

**Pause after Step 1. Run pytest, report result. Wait for confirmation.**

---

## Step 2: Block Separation — Extract Table Region Text

### File: `engine/pdf_extractor.py`

**Add a helper function** `separate_table_region_blocks()`:

```python
def separate_table_region_blocks(
    blocks: List[TextBlock],
    page_num: int,
    table_regions: List[TableRegion],
) -> Tuple[List[TextBlock], Dict[int, str]]:
    """Separates blocks that fall within an active table_region.

    Returns:
        (remaining_blocks, table_region_texts)
        - remaining_blocks: blocks NOT in any active table_region
        - table_region_texts: dict mapping table_region index to the
          whitespace-normalized concatenated text of blocks in that region.
          Only includes regions where the condition matched.
    """
```

**Logic:**

1. For each `table_region` that applies to `page_num` (use `_region_applies_to_page`
   with duck-typing — `TableRegion` has the same `.page` / `.page_from` interface):
   - Collect blocks whose bounding box overlaps the region (same overlap logic
     as `filter_blocks_by_regions`, reuse or mirror the overlap check).
   - Concatenate text of collected blocks (order doesn't matter for Counter,
     but use `join_block_text` for consistency).
   - **Normalize whitespace:** collapse all whitespace variants (spaces, newlines,
     tabs, multiple spaces) to single spaces, then strip.
   - **Check condition:** case-sensitive substring search on the normalized text.
   - If condition matches: include this region's normalized text in
     `table_region_texts` and remove the blocks from the main list.
   - If condition does NOT match: leave blocks in the main list untouched
     (normal comparison will handle them).

2. Return `(remaining_blocks, table_region_texts)`.

**Important:** `_region_applies_to_page` currently accepts `Region` objects. 
`TableRegion` has the same `.page` / `.page_from` attributes, so duck-typing works.
If the function has type hints that reject `TableRegion`, either:
- Add a `Protocol` / structural typing, OR
- Simply check the attributes inline (`.page` and `.page_from`).
Choose whichever approach keeps the code simplest.

### Integration point in `_extract_page_text_columns`:

After `filter_blocks_by_regions` (step 2 in pipeline), before `split_wide_blocks`:

```python
blocks = filter_blocks_by_regions(blocks, page_num, regions)

# NEW: separate table_region blocks
table_region_texts = {}
if table_regions:
    blocks, table_region_texts = separate_table_region_blocks(
        blocks, page_num, table_regions
    )

blocks = split_wide_blocks(blocks, page)
blocks = sort_blocks_columns(blocks)
page_text = join_block_text(blocks)
```

The `table_region_texts` must be transported out of the extraction function and
up through `extract_pages_for_profile`. This requires extending the return value.

### Return value change for `extract_pages_for_profile`:

Currently returns: `Tuple[List[str], bool]` → `(page_texts, ocr_used)`

**Change to return:** `Tuple[List[str], bool, List[Dict[int, str]]]`
→ `(page_texts, ocr_used, per_page_table_region_texts)`

Where `per_page_table_region_texts` is a list (one entry per page) of dicts
mapping table_region index → normalized text. Pages without matching
table_regions have an empty dict.

**Update ALL callers** of `extract_pages_for_profile`:
- `engine/__main__.py` — must accept the new return value
- `engine/batch_processor.py` — must accept the new return value
- All test files that call `extract_pages_for_profile` — update unpacking

For callers that don't need `table_region_texts` yet, they can simply ignore
the third element: `pages, ocr_used, _ = extract_pages_for_profile(...)`.

### Also integrate into `ocr_extractor.extract_pages_with_ocr_fallback`:

This is the actual execution path for Kim's profile (`ocr.mode: "fallback"`).
The native-text branch inside this function currently does:
```python
blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
pages_text.append(join_block_text(blocks))
```

Add `separate_table_region_blocks` between `filter_blocks_by_regions` and
`join_block_text`, same pattern as `_extract_page_text_columns`. The function
must also return `per_page_table_region_texts` as a third element.

### Tests (in `tests/test_pdf_extractor.py`):

Create a synthetic fixture PDF with a known footer region containing multi-word
text (e.g., "ACME Insurance Company | Contact: info@acme.de | Phone: 0800-1234").
Use ReportLab to place this at defined coordinates.

Tests:
- Blocks inside a matching table_region are separated from remaining blocks
- Condition match: table_region_texts contains the normalized text
- Condition no-match: blocks remain in the main text, table_region_texts empty
- `page=0` wildcard applies to every page
- `page_from=2` applies only from page 2 onward
- Multiple table_regions on same page: each matched independently
- Overlapping with prior exclude_region: exclude runs first, table_region
  works on remaining blocks (may have reduced text but doesn't crash)

**Pause after Step 2. Run pytest, report result. Wait for confirmation.**

---

## Step 3: Counter Comparison — `table_region_comparator.py`

### New file: `engine/table_region_comparator.py`

```python
"""Multiset word comparison for table_regions.

Compares two texts by word frequency (collections.Counter) instead of
sequential diff. Designed for page regions where block structure diverges
between PDFs but word content is identical.
"""
```

**Main function:**

```python
def compare_table_region(
    ref_text: str,
    cnd_text: str,
    page_num: int,
    region_index: int,
) -> List[Delta]:
    """Compare two region texts by word frequency.

    Tokenization: split on whitespace after normalization (whitespace
    already collapsed to single spaces by separate_table_region_blocks).

    Returns a list of Delta objects for words that differ:
    - Words in ref but not in cnd → Delta(type="delete", ref_text=word, ...)
    - Words in cnd but not in ref → Delta(type="insert", cnd_text=word, ...)
    - Word count differs → one Delta per excess/missing occurrence

    Delta objects must have the same structure as those produced by
    text_comparator.compare(), so the report renderer treats them
    identically. Check the existing Delta dataclass and reuse it.
    """
```

**Logic:**

```python
from collections import Counter

ref_words = ref_text.split()
cnd_words = cnd_text.split()

ref_counter = Counter(ref_words)
cnd_counter = Counter(cnd_words)

# Words only in reference (missing from candidate)
missing = ref_counter - cnd_counter   # Counter subtraction

# Words only in candidate (extra in candidate)
extra = cnd_counter - ref_counter

# Generate Delta objects for each missing/extra word
```

**Important:** Examine the existing `Delta` dataclass in `text_comparator.py`
before implementing. The synthetic deltas must have:
- `page`: the page number where the region was found
- `type`: "delete" (missing from candidate) or "insert" (extra in candidate)
- `ref_text` / `cnd_text`: the affected word(s)
- Any other required fields — set them to sensible defaults

If the existing `Delta` class has required fields that don't apply to
Counter-based comparison (e.g., line numbers, character positions), set
them to `None` or a sentinel value and document why.

### Tests (in `tests/test_table_region_comparator.py`):

- Identical texts → no deltas
- One word missing in candidate → one "delete" delta
- One extra word in candidate → one "insert" delta
- Multiple occurrences: "Müller Müller Schmidt" vs "Müller Schmidt" → one
  "delete" delta for "Müller"
- Completely different texts → deltas for all words
- Empty texts on both sides → no deltas
- Empty ref, non-empty cnd → "insert" deltas
- Non-empty ref, empty cnd → "delete" deltas
- Word order different but same words → no deltas (this is the key behavior!)
- Deltas have correct `page` attribute

**Pause after Step 3. Run pytest, report result. Wait for confirmation.**

---

## Step 4: Pipeline Integration — Merge Table Region Deltas

### File: `engine/__main__.py` (single comparison)

After extracting pages from both PDFs:

```python
ref_pages, ref_ocr, ref_tr_texts = extract_pages_for_profile(ref_path, profile, role="reference")
cnd_pages, cnd_ocr, cnd_tr_texts = extract_pages_for_profile(cnd_path, profile, role="candidate")
```

**Before calling `compare()`:**

For each page pair `(i)`, check if both `ref_tr_texts[i]` and `cnd_tr_texts[i]`
have entries for the same `region_index`. If yes:
- Run `compare_table_region(ref_text, cnd_text, page_num, region_index)`
- Collect the resulting deltas

**Call `compare()` on the remaining page texts** (which already have the
table_region blocks removed).

**Merge** table_region deltas + sequential comparison deltas into a single
result. The merged result determines `has_delta`.

### File: `engine/batch_processor.py`

Same integration pattern as `__main__.py` — the `_compare_pair` function
must handle the third return value and perform the same merge logic.

### Shared helper

Since both `__main__.py` and `batch_processor.py` need the same merge logic,
extract it into a shared function. Options:
- Add `merge_table_region_comparison()` to `table_region_comparator.py`, or
- Add a helper in `text_comparator.py`

Choose whichever is cleaner. The function should:
1. Accept `ref_tr_texts` and `cnd_tr_texts` (per-page dicts) for both PDFs
2. For each page, for each region_index present in BOTH sides: run Counter comparison
3. Return merged deltas list

### Tests:

**Integration test in `tests/test_main.py`:**
Create a synthetic fixture pair where:
- Both PDFs have a footer at the same coordinates with the same words
  but different block structure (one wide block vs. multiple narrow blocks)
- Profile has a `table_region` with the correct condition
- Assert: `has_delta` is `False` (the footer difference is a false positive
  that table_regions eliminates)

**Integration test in `tests/test_batch_processor.py`:**
Same scenario via batch processing path — assert no delta for the footer region.

**Integration test for genuine delta:**
Same fixture but with one word changed in the candidate footer.
Assert: `has_delta` is `True`, delta references the changed word.

**Pause after Step 4. Run pytest, report result. Wait for confirmation.**

---

## Fixture PDF Generation

### File: `tests/generate_fixtures.py`

Add fixture generation for `table_regions` tests. Create a test case directory
(e.g., `TC-TR-001`) with:

**ref.pdf:**
- Normal body text (e.g., "Sehr geehrte Damen und Herren, ...") on upper part
- Footer area (y > 750pt) containing ONE WIDE block with multi-column text:
  `"SV SparkassenVersicherung | Kundenservice | Tel: 0800-1234 | info@sv.de"`
  (Use a single `Paragraph` spanning the full page width)

**cnd.pdf:**
- Identical body text
- Footer area with FOUR NARROW blocks at the same y-position, each containing
  one column of the footer:
  - Block 1: `"SV SparkassenVersicherung"`
  - Block 2: `"Kundenservice"`
  - Block 3: `"Tel: 0800-1234"`
  - Block 4: `"info@sv.de"`
  (Use four separate `Paragraph` elements positioned with `Frame` objects or
  a `Table` with invisible borders)

This fixture simulates the real-world scenario: same visual footer, different
block structure.

Add a second fixture (`TC-TR-002`) where one word differs in the candidate
footer (e.g., "Tel: 0800-5678" instead of "Tel: 0800-1234") — for testing
genuine delta detection.

---

## Important Constraints

- **Do NOT commit.** Kim commits manually after pytest verification.
- **Pause after each step** (1, 2, 3, 4) and report what you did, what
  changed, and the pytest result. Do not proceed without confirmation.
- **Do not modify existing test fixtures** in `tests/fixtures/`.
- **Do not touch GUI code** (React/TypeScript/Tauri).
- **Backward compatibility:** Profiles without `table_regions` must continue
  to work unchanged. The new field defaults to an empty list.
- **No network access** — everything local, no external dependencies.
- Run `pytest` from the project root after each step.
- When the existing `Delta` dataclass needs inspection, read
  `engine/text_comparator.py` first to understand its structure.
