# Sprint PTC-S3 Task A: Profile Option `merge_hyphenation`

## Problem

`normalize_text()` in `text_comparator.py` uses `_HYPHENATION_RE` to merge
syllable breaks (`Silben-\ntrennung` → `Silbentrennung`). When legacy output
systems (Papyrus) split a visual line into multiple Content-Stream operations,
PyMuPDF inserts `\n` between them. This causes compound hyphens like
`Stück- und` to become `Stück-\nund`, which `_HYPHENATION_RE` incorrectly
matches and strips, producing `Stückund` — a false delta.

The extraction cannot be safely modified (attempts caused regressions across
all documents). Instead, add a profile option to disable hyphenation merging
for document types where it causes more harm than good.

## Solution

New Profile field `merge_hyphenation` (boolean, default `true`). When `false`,
`normalize_text()` skips `_HYPHENATION_RE` entirely. The DV-Koordinator sets
this per profile for document types with few real syllable breaks (e.g.
Papyrus output).

## Files to Modify

1. `engine/profile_loader.py` — add field to Profile, load from JSON
2. `engine/text_comparator.py` — add parameter to `normalize_text()` and
   `compare()`
3. `engine/__main__.py` — pass profile value to `compare()`
4. `engine/batch_processor.py` — pass profile value to `compare()`
5. `tests/test_text_comparator.py` — unit tests
6. `tests/test_main.py` — E2E wiring test
7. `tests/test_profile_loader.py` — profile loading test

## Implementation Steps

### Step 1: Profile field

In `engine/profile_loader.py`:

**Profile dataclass** — add after `compare_mode`:
```python
merge_hyphenation: bool = True
```

**`load_profile()`** — add before the `return Profile(...)`:
```python
merge_hyphenation = bool(data.get("merge_hyphenation", True))
```

And add `merge_hyphenation=merge_hyphenation` to the `return Profile(...)` call.

No validation needed (bool with default).

### Step 2: `normalize_text()` parameter

In `engine/text_comparator.py`:

**`normalize_text()`** — change signature:
```python
def normalize_text(text: str, merge_hyphenation: bool = True) -> str:
```

Wrap the existing `_HYPHENATION_RE` application in a condition:
```python
if merge_hyphenation:
    text = _HYPHENATION_RE.sub("", text)
```

**`_words_with_pages()`** — add `merge_hyphenation` parameter, pass through:
```python
def _words_with_pages(pages, merge_hyphenation: bool = True):
    ...
    normalized = normalize_text(page_text, merge_hyphenation=merge_hyphenation)
```

**`_chars_with_pages()`** — add `merge_hyphenation` parameter, pass through:
```python
def _chars_with_pages(pages, merge_hyphenation: bool = True):
    ...
    normalized = normalize_text(page_text, merge_hyphenation=merge_hyphenation)
```

**`_compare_words()`** — add parameter, pass to `_words_with_pages()`:
```python
def _compare_words(ref_pages, cnd_pages, case_sensitive, normalize_whitespace,
                   merge_hyphenation: bool = True):
    ref_words, _ = _words_with_pages(ref_pages, merge_hyphenation=merge_hyphenation)
    cnd_words, cnd_word_pages = _words_with_pages(cnd_pages, merge_hyphenation=merge_hyphenation)
```

**`_compare_chars()`** — add parameter, pass to `_chars_with_pages()`:
```python
def _compare_chars(ref_pages, cnd_pages, case_sensitive,
                   merge_hyphenation: bool = True):
    ref_compact, ref_map, ref_original, ref_boundaries = _chars_with_pages(ref_pages, merge_hyphenation=merge_hyphenation)
    cnd_compact, cnd_map, cnd_original, cnd_boundaries = _chars_with_pages(cnd_pages, merge_hyphenation=merge_hyphenation)
```

**`_compare_hybrid()`** — add parameter, pass through to both
`_words_with_pages()` and `_chars_with_pages()` calls within it.

**`compare()`** — add parameter, pass to dispatch:
```python
def compare(
    ref_pages, cnd_pages,
    case_sensitive: bool = True,
    normalize_whitespace: bool = False,
    ocr_used: bool = False,
    compare_mode: str = "words",
    merge_hyphenation: bool = True,
) -> CompareResult:
```

And pass `merge_hyphenation=merge_hyphenation` to each `_compare_*()` call.

### Step 3: Wire through callers

**`engine/__main__.py`** — in `_run_compare()`, add to the `compare()` call:
```python
result = compare(
    ref_pages, cnd_pages,
    case_sensitive=profile.case_sensitive if profile else True,
    normalize_whitespace=profile.normalize_whitespace if profile else False,
    ocr_used=ref_ocr_used or cnd_ocr_used,
    compare_mode=profile.compare_mode if profile else "words",
    merge_hyphenation=profile.merge_hyphenation if profile else True,
)
```

**`engine/batch_processor.py`** — find the `compare()` call in `_compare_pair`
or equivalent, add the same pattern:
```python
merge_hyphenation=profile.merge_hyphenation if profile else True,
```

### Step 4: Tests

**In `tests/test_text_comparator.py`:**

```python
def test_normalize_text_merge_hyphenation_false_preserves_hyphen():
    """With merge_hyphenation=False, a hyphen before a newline is NOT
    removed — the compound hyphen 'Stück-' survives normalization."""
    result = normalize_text("Stück-\nund", merge_hyphenation=False)
    assert "Stück-" in result
    assert "Stückund" not in result


def test_normalize_text_merge_hyphenation_true_default_merges():
    """Default behavior: syllable breaks are still merged."""
    result = normalize_text("Silben-\ntrennung", merge_hyphenation=True)
    assert result == "Silbentrennung"


def test_compare_merge_hyphenation_false_no_false_delta():
    """With merge_hyphenation=False, 'Stück-\\nund' in ref vs 'Stück- und'
    in cnd must not produce a delta (both normalize to contain 'Stück-')."""
    ref_pages = ["Beiträge ohne Stück-\nund periodenabhängige Kosten"]
    cnd_pages = ["Beiträge ohne Stück- und periodenabhängige Kosten"]

    result = compare(ref_pages, cnd_pages, merge_hyphenation=False)
    assert result.has_delta is False


def test_compare_merge_hyphenation_true_still_merges_syllables():
    """Default: real syllable breaks still produce no delta."""
    ref_pages = ["Silben-\ntrennung"]
    cnd_pages = ["Silbentrennung"]

    result = compare(ref_pages, cnd_pages, merge_hyphenation=True)
    assert result.has_delta is False
```

**In `tests/test_main.py`** — E2E wiring test (follow existing pattern):

```python
def test_compare_mit_profile_merge_hyphenation_false_end_to_end(tmp_path, capsys):
    """merge_hyphenation=false must wire through CLI to compare()."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Stück-\nund periodenabhängige Kosten")
    _write_single_page_pdf(cnd_path, "Stück- und periodenabhängige Kosten")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "merge_hyphenation": False}),
        encoding="utf-8",
    )

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
```

**In `tests/test_profile_loader.py`** — loading test:

```python
def test_merge_hyphenation_default_true(tmp_path):
    """merge_hyphenation defaults to True when not in JSON."""
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0"}')
    profile = load_profile(path)
    assert profile.merge_hyphenation is True


def test_merge_hyphenation_false_from_json(tmp_path):
    """merge_hyphenation=false is loaded correctly."""
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0", "merge_hyphenation": false}')
    profile = load_profile(path)
    assert profile.merge_hyphenation is False
```

## Constraints

- Do NOT modify `engine/pdf_extractor.py` or `engine/ocr_extractor.py`
- Do NOT commit — Kim commits manually after verification
- Run `pytest` after each step — all existing tests must stay green
- Default `true` ensures backward compatibility (no behavior change for
  existing profiles without the field)
- The report should display "Silbentrennung zusammenführen" with "Ja"/"Nein"
  in the profile settings table — but this is a SEPARATE task, skip it for now

## Verification

After implementation, Kim will:
1. `pytest` — all tests green
2. Set `"merge_hyphenation": false` in Profil I.json
3. `npm run tauri dev` — run Papyrus comparison
4. Verify deltas #27, #28, #41 no longer appear
