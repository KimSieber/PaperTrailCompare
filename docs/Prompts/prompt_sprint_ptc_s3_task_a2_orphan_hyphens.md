# Sprint PTC-S3 Task A2: Profile Option `normalize_orphan_hyphens`

## Problem

Legacy output systems (Papyrus) split visual lines into multiple Content-
Stream operations. PyMuPDF interprets these as separate lines and inserts `\n`.
When a compound hyphen like `Stück-` lands in a separate rawdict line, the
extracted text becomes `Stück \n - \n und`. After whitespace normalization
this is `Stück - und`, but the candidate has `Stück- und` — the hyphen is
attached to the word.

The word-level diff sees Ref=`' '` (space) vs Cand=`'-'` (hyphen) as a delta.

## Solution

New Profile field `normalize_orphan_hyphens` (boolean, default `true`).

When `true`, `normalize_text()` applies an additional normalization step AFTER
whitespace collapsing: a hyphen/minus that is surrounded by spaces
(`word - next`) is attached to the preceding word (`word- next`).

Regex: `(\S) - ` → `\1- ` (non-whitespace char, space, hyphen, space →
non-whitespace char, hyphen, space). This covers U+002D (hyphen-minus).

This runs AFTER `_WHITESPACE_RE` collapsing and is independent of
`merge_hyphenation`.

## Files to Modify

1. `engine/profile_loader.py` — add field to Profile, load from JSON
2. `engine/text_comparator.py` — add normalization step and parameter
3. `engine/__main__.py` — pass profile value to `compare()`
4. `engine/batch_processor.py` — pass profile value to `compare()`
5. `tests/test_text_comparator.py` — unit tests
6. `tests/test_profile_loader.py` — profile loading test

## Implementation Steps

### Step 1: Profile field

In `engine/profile_loader.py`:

**Profile dataclass** — add after `merge_hyphenation`:
```python
normalize_orphan_hyphens: bool = True
```

**`load_profile()`** — add before the `return Profile(...)`:
```python
normalize_orphan_hyphens = bool(data.get("normalize_orphan_hyphens", True))
```

And add `normalize_orphan_hyphens=normalize_orphan_hyphens` to the
`return Profile(...)` call.

### Step 2: Normalization in `text_comparator.py`

Add a new compiled regex near `_WHITESPACE_RE`:
```python
_ORPHAN_HYPHEN_RE = re.compile(r"(\S) - ")
```

**`normalize_text()`** — add parameter and apply AFTER `_WHITESPACE_RE`:
```python
def normalize_text(text: str, merge_hyphenation: bool = True,
                   normalize_orphan_hyphens: bool = True) -> str:
```

After the existing `_WHITESPACE_RE.sub(" ", text).strip()` line, add:
```python
if normalize_orphan_hyphens:
    text = _ORPHAN_HYPHEN_RE.sub(r"\1- ", text)
```

Thread the parameter through the same functions as `merge_hyphenation`:
- `_words_with_pages()` — add parameter, pass to `normalize_text()`
- `_chars_with_pages()` — add parameter, pass to `normalize_text()`
- `_compare_words()` — add parameter, pass through
- `_compare_chars()` — add parameter, pass through
- `_compare_hybrid()` — add parameter, pass through
- `compare()` — add parameter, pass to dispatch

### Step 3: Wire through callers

**`engine/__main__.py`** — add to the `compare()` call:
```python
normalize_orphan_hyphens=profile.normalize_orphan_hyphens if profile else True,
```

**`engine/batch_processor.py`** — same pattern.

### Step 4: Tests

**In `tests/test_text_comparator.py`:**

```python
def test_normalize_text_orphan_hyphen_attached_to_preceding_word():
    """A standalone hyphen surrounded by spaces is attached to the
    preceding word: 'Stück - und' → 'Stück- und'."""
    result = normalize_text("Stück - und", normalize_orphan_hyphens=True)
    assert result == "Stück- und"


def test_normalize_text_orphan_hyphen_disabled():
    """With normalize_orphan_hyphens=False, standalone hyphens stay."""
    result = normalize_text("Stück - und", normalize_orphan_hyphens=False)
    assert result == "Stück - und"


def test_normalize_text_orphan_hyphen_from_newline_split():
    """Simulates the Papyrus pattern: word\\n-\\nword → after whitespace
    collapse → 'word - word' → orphan hyphen attach → 'word- word'."""
    result = normalize_text("Stück\n-\nund", normalize_orphan_hyphens=True)
    assert result == "Stück- und"


def test_compare_orphan_hyphen_no_false_delta():
    """Ref has orphan hyphen, cand has attached hyphen — no delta."""
    ref_pages = ["Beiträge ohne Stück - und periodenabhängige Kosten"]
    cnd_pages = ["Beiträge ohne Stück- und periodenabhängige Kosten"]

    result = compare(ref_pages, cnd_pages, normalize_orphan_hyphens=True)
    assert result.has_delta is False


def test_compare_orphan_hyphen_disabled_produces_delta():
    """With orphan hyphen normalization off, the difference IS a delta."""
    ref_pages = ["Beiträge ohne Stück - und periodenabhängige Kosten"]
    cnd_pages = ["Beiträge ohne Stück- und periodenabhängige Kosten"]

    result = compare(ref_pages, cnd_pages, normalize_orphan_hyphens=False)
    assert result.has_delta is True
```

**In `tests/test_profile_loader.py`:**

```python
def test_normalize_orphan_hyphens_default_true(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0"}')
    profile = load_profile(path)
    assert profile.normalize_orphan_hyphens is True


def test_normalize_orphan_hyphens_false_from_json(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0", "normalize_orphan_hyphens": false}')
    profile = load_profile(path)
    assert profile.normalize_orphan_hyphens is False
```

### Step 5: Update existing test

The existing test `test_normalize_text_isolierter_bindestrich_nach_zeilenumbruch_bleibt_erhalten`
currently asserts:
```python
assert normalize_text("Wort\n-\nnächstes") == "Wort - nächstes"
```

With the new default `normalize_orphan_hyphens=True`, this will now produce
`"Wort- nächstes"`. Update the test:
```python
def test_normalize_text_isolierter_bindestrich_nach_zeilenumbruch_bleibt_erhalten():
    """Standalone hyphen on its own line: with default orphan-hyphen
    normalization, it attaches to the preceding word."""
    assert normalize_text("Wort\n-\nnächstes") == "Wort- nächstes"
```

Also check `test_isolierter_gedankenstrich_ergibt_kein_falsches_delta` — this
test compares `"Verlässlichkeit\n-\nvielen Dank dafür!"` vs
`"Verlässlichkeit - vielen Dank dafür!"`. With orphan-hyphen normalization,
both should produce `"Verlässlichkeit- vielen Dank dafür!"` — verify the test
still passes (it should, since both sides normalize the same way).

## Constraints

- Do NOT modify `engine/pdf_extractor.py` or `engine/ocr_extractor.py`
- Do NOT commit — Kim commits manually after verification
- Run `pytest` after each step — all existing tests must stay green
- The regex `_ORPHAN_HYPHEN_RE` must only match U+002D (hyphen-minus),
  not em-dash or en-dash
