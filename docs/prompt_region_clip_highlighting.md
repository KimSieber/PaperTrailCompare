# Claude Code Prompt: Region-Clip for Precise Delta Highlighting

## Context

PaperTrail Compare, local desktop PDF comparison app (Tauri + React/TS + Python
engine). 236 tests green. `compare_regions` feature fully working with
`mode: "sequential"` (default) and `mode: "unordered"`.

**Do NOT commit** — Kim commits manually after pytest + GUI verification.
**Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.**

---

## Problem (verified on real customer documents)

`report_generator._find_delta_rects` locates delta positions for yellow
overlay highlighting via `page.search_for(text)` — a full-page text search.
This causes three concrete problems:

1. **Region deltas highlight too broadly**: a sequential region delta like
   `"Tel.: 0611 178-49830"` is found everywhere on the page where that phone
   number appears (sender block AND footer), not just inside the region.
2. **Unordered region deltas highlight the entire block**: the single delta
   text for a multiset mismatch contains ALL region text → the whole footer
   is highlighted.
3. **Ghost highlights**: text fragments from a region delta (e.g.
   `service@sparkassenversicherung.de`) match in unrelated page areas (footer,
   header) that have no delta at all, producing yellow marks with no
   corresponding entry in the delta list.

All three problems disappear if `search_for` is constrained to the region's
bounding box via its `clip` parameter.

---

## Fix (three small, connected changes)

### 1. Add `region_clip` to Delta

File: `engine/text_comparator.py` (or wherever the `Delta` dataclass lives).

Add an optional field:

```python
region_clip: Optional[Tuple[float, float, float, float]] = None
```

This is a `(x0, y0, x1, y1)` rectangle in PDF page coordinates. `None` means
"no clip, search the whole page" (all non-region deltas). The field is
Python-internal — it is used only by the report generator. It MUST NOT appear
in the JSON output (`__main__.py` serialization) — either exclude it explicitly
or ensure the serializer already skips `None` fields. Check and verify.

### 2. Populate `region_clip` when creating region deltas

File: `engine/compare_region_comparator.py`

In BOTH code paths that create Delta objects for regions:

- `compare_region` (unordered mode) — when building the single mismatch Delta
- `_compare_region_sequential` (sequential mode) — when remapping the Deltas
  from `text_comparator.compare()`

Set `region_clip` to `(region.x, region.y, region.x + region.width,
region.y + region.height)` using the `CompareRegion` definition from the
profile.

The region coordinates must be available at the point where the Delta is
created. If they are not currently passed through, thread them through — but
keep the change minimal. `merge_compare_region_comparison` already receives the
profile and knows the region index, so the coordinates are accessible.

### 3. Use `clip` in `_find_delta_rects`

File: `engine/report_generator.py`

Change the data flow so `_find_delta_rects` receives clip information alongside
the text. The cleanest approach:

- Change `texts_by_page` from `Dict[int, List[str]]` to
  `Dict[int, List[Tuple[str, Optional[fitz.Rect]]]]` — each entry is
  `(delta_text, optional_clip_rect)`.
- At the call site where `texts_by_page` is built from the delta list,
  convert `delta.region_clip` (the 4-tuple) to a `fitz.Rect` if present,
  else `None`.
- Inside `_find_delta_rects`, when `clip` is not None, call
  `page.search_for(text, clip=clip)` instead of `page.search_for(text)`.
- The fallback search (`fallback_search_all_pages`) should NOT use the clip
  (the whole point of the fallback is to search other pages where the region
  coordinates don't apply).

Update the docstring of `_find_delta_rects` to document the clip behaviour.

---

## Tests (TDD: write/adjust tests first, watch them fail, then implement)

1. **New test — region clip restricts search**: create a synthetic one-page PDF
   (ReportLab) where the same short text (e.g. "Stuttgart") appears TWICE on
   the page: once at y≈100 (inside a defined region) and once at y≈700
   (outside). Create a Delta with `region_clip` covering only the upper area.
   Call `_find_delta_rects` and assert that exactly ONE rect is returned, and
   its y-coordinate is in the upper region (not ~700). Without the clip, the
   test would find two rects.

2. **New test — no clip searches whole page**: same PDF, but Delta without
   `region_clip` (None) → both occurrences found (two rects). This confirms
   backwards compatibility for non-region deltas.

3. **New test — clip not used in fallback**: Delta with `region_clip` set, but
   `page` pointing to a page where the text does NOT appear inside the clip
   (or page out of range). With `fallback_search_all_pages=True`, the fallback
   must still find the text on another page (without clip).

4. **Existing report tests**: must pass unchanged. The existing tests create
   Deltas without `region_clip`, so `None` is the default, and behaviour is
   identical.

5. **JSON serialization**: verify that `region_clip` does NOT appear in the
   JSON output of a comparison (the field is internal to the Python report
   pipeline).

---

## Workflow

Single step (the change is small and self-contained). Write tests first (red),
implement, run the FULL pytest suite, report. Do NOT commit.

## General rules

- Do NOT commit.
- Do NOT modify Rust or TypeScript code.
- Do NOT change comparison logic, region separation, condition checking, or
  delta sorting — this prompt is purely about report highlighting.
- Real customer PDFs must never become test fixtures.
