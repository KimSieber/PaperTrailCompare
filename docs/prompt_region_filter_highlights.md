# Claude Code Prompt: Filter Sequential Delta Highlights Outside Regions

## Context

PaperTrail Compare, local desktop PDF comparison app (Tauri + React/TS + Python
engine). 243 tests green. Region-clip highlighting for region deltas already
works (deltas with `region_clip` use `search_for(text, clip=...)` to restrict
results to the region bounding box).

**Do NOT commit** — Kim commits manually after pytest + GUI verification.
**Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.**

---

## Problem (verified empirically on real customer documents)

Sequential (non-region) deltas have no `region_clip`, so
`report_generator._find_delta_rects` calls `page.search_for(text)` over the
full page. When the delta text is a common word (e.g. "SparkassenVersicherung"),
`search_for` finds it everywhere on the page — in the footer, sender block,
recipient address, header — producing false yellow highlights with no
corresponding delta in the list.

Empirical measurement on the real reference PDF page 1: searching for
"SparkassenVersicherung" returns 7 hits. Only 1 is the actual delta (in the
subject line). The other 6 are false positives, 5 of which fall inside defined
`exclude_regions` or `compare_regions`.

---

## Fix (single, targeted change)

### In `engine/report_generator.py`, function `_find_delta_rects`

After `search_for` returns hit rectangles for a delta **without** a
`region_clip` (i.e. a sequential/non-region delta), filter out any hit whose
**center point** falls inside an active `exclude_region` or `compare_region`
for that page.

The logic:
- For each hit rect, compute its center: `cx = (rect.x0 + rect.x1) / 2`,
  `cy = (rect.y0 + rect.y1) / 2`.
- Check against all `exclude_regions` and `compare_regions` from the profile
  that apply to this page (use the same `page: 0` = "all pages" convention
  as elsewhere: `page == 0` means the region applies to every page,
  `page == N` means it applies only to page N).
- If the center falls inside ANY such region, discard that hit rect.
- If ALL hits are discarded, keep the results empty (do NOT fall back to
  unfiltered — the delta text genuinely does not appear outside the regions
  on this page, and that's fine; the delta is still in the list, just not
  visually highlighted, which is better than a wrong highlight).

**Do NOT apply this filter to deltas that already have a `region_clip`** — those
are already correctly constrained.

### Threading the profile through

`_find_delta_rects` currently has no access to the profile's region
definitions. The fix requires passing them in. Options (choose the cleanest):

- Change the signature of `_find_delta_rects` to accept an additional
  parameter for the region rectangles (a flat list of `(page, x, y, w, h)`
  tuples covering both `exclude_regions` and `compare_regions`).
- Build this list at the call site from the profile (or from the
  `CompareResult` if the profile is not available there — check what is
  accessible).
- If the profile is not accessible in `generate_report`, thread it through.
  But keep the change minimal — only pass what is needed (the region
  rectangles), not the whole profile.

### Data structure change for `texts_by_page`

`_find_delta_rects` currently receives
`Dict[int, List[Tuple[str, Optional[fitz.Rect]]]]` (from the region-clip
change). The clip information tells the function whether a delta is a region
delta (clip is not None) or a sequential delta (clip is None). Use this
existing distinction to decide whether to apply the region filter:
- `clip is not None` → region delta, use clip as before, no filtering.
- `clip is None` → sequential delta, search full page, then filter.

No additional flag needed.

---

## Tests (TDD: write/adjust tests first, watch them fail, then implement)

1. **New test — sequential delta filtered by region**: create a synthetic
   one-page PDF where "Stuttgart" appears THREE times: once at y≈300 (body
   text, outside all regions), once at y≈750 (inside a defined
   compare_region), and once at x≈30 (inside a defined exclude_region).
   Create a sequential Delta (no `region_clip`) for "Stuttgart". Pass region
   definitions covering the y≈750 and x≈30 areas. Assert that
   `_find_delta_rects` returns exactly ONE rect, at y≈300.

2. **New test — region delta NOT filtered**: same PDF setup, but the Delta
   has `region_clip` set to the y≈750 area. Assert that `_find_delta_rects`
   returns exactly ONE rect at y≈750 (the clip restricts, not the filter).

3. **New test — all hits inside regions**: sequential Delta where ALL
   occurrences fall inside regions. Assert `_find_delta_rects` returns an
   empty dict (no rects), not the unfiltered list.

4. **Existing tests**: must pass unchanged. Existing tests that don't pass
   region definitions should see no filtering (empty region list = nothing
   filtered out).

5. **Signature compatibility**: ensure the default for the new parameter is
   an empty list or None, so all existing callers work without modification
   unless they explicitly pass regions.

---

## Workflow

Single step (small change). Write tests first (red), implement, run the FULL
pytest suite, report. Do NOT commit.

## General rules

- Do NOT commit.
- Do NOT modify Rust or TypeScript code.
- Do NOT change comparison logic, region separation, condition checking, or
  the existing region-clip behaviour for region deltas.
- Real customer PDFs must never become test fixtures.
