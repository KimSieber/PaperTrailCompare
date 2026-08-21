# Sprint PTC-S6 Task 4 — Batch List Column + Window Width

## Overview

Two small GUI changes:
1. Remove the "Übereinstimmung" (match percentage) column from the
   batch results list in `BatchView.tsx`. The PDF batch report keeps
   its column unchanged.
2. Reduce the default window width by 50px (1050 → 1000).

**Execution order:** Step 1 → 2 → Verification.

Do NOT run `git commit` or `git push` — Kim commits manually after
verification.

---

## Step 1 — Remove "Übereinstimmung" column from BatchView.tsx

### 1a. Remove the `matchPercent` function

The `matchPercent` function (near the top of the file) is only used
for the GUI column being removed. Delete the entire function:

```typescript
function matchPercent(pair: BatchPairResult): number | null {
  if (pair.status !== "ok" || !pair.compare_result || !pair.total_pages) {
    return null;
  }
  const deltaPageCount = new Set(pair.compare_result.deltas.map((d) => d.page)).size;
  const matchRatio = (pair.total_pages - deltaPageCount) / pair.total_pages;
  return Math.round(matchRatio * 100);
}
```

### 1b. Update the colgroup

Change from 4 columns to 3. The two filename columns get more space,
the Deltas column stays narrow.

**Find:**

```tsx
<colgroup>
  <col className="w-[38%]" />
  <col className="w-[38%]" />
  <col className="w-[12%]" />
  <col className="w-[12%]" />
</colgroup>
```

**Replace with:**

```tsx
<colgroup>
  <col className="w-[42%]" />
  <col className="w-[42%]" />
  <col className="w-[16%]" />
</colgroup>
```

### 1c. Remove the header column

**Find in the `<thead>`:**

```tsx
<th className="px-3 py-2">Deltas</th>
<th className="px-3 py-2">Übereinstimmung</th>
```

**Replace with:**

```tsx
<th className="px-3 py-2">Deltas</th>
```

### 1d. Update the data rows

In the `<tbody>` row rendering, find the block that renders the
Deltas and Übereinstimmung cells for non-error rows.

**Find the fragment (inside `isError ? ... : ...`):**

```tsx
<>
  <td className="px-3 py-2">{pair.compare_result?.deltas.length ?? "—"}</td>
  <td className="px-3 py-2">{percent !== null ? `${percent} %` : "—"}</td>
</>
```

**Replace with:**

```tsx
<td className="px-3 py-2">{pair.compare_result?.deltas.length ?? "—"}</td>
```

Since we removed the fragment wrapper (`<>...</>`), the non-error
branch now returns a single `<td>` instead of a fragment — make sure
the surrounding ternary still works syntactically.

### 1e. Update the error row colspan

Error rows currently span 2 columns (`colSpan={2}`) for the combined
Deltas + Übereinstimmung area. With only one remaining column (Deltas),
the colspan is no longer needed.

**Find:**

```tsx
<td className="overflow-hidden px-3 py-2" colSpan={2}>
  <MiddleTruncate text={`Fehler: ${pair.error}`} tailLength={16} />
</td>
```

**Replace with:**

```tsx
<td className="overflow-hidden px-3 py-2">
  <MiddleTruncate text={`Fehler: ${pair.error}`} tailLength={16} />
</td>
```

### 1f. Remove unused `percent` variable

In the row rendering, there should be a line like:

```typescript
const percent = matchPercent(pair);
```

Delete this line (the function was already removed in 1a).

**Pause — wait for confirmation before continuing.**

---

## Step 2 — Reduce default window width

In `src-tauri/tauri.conf.json`, reduce the default window width.

**Find:**

```json
"width": 1050,
```

**Replace with:**

```json
"width": 1000,
```

The `minWidth` (700) stays unchanged.

### Verification (Step 2)

1. Run `npm run build` — must compile without TypeScript errors.
2. Run `pytest` from project root with `PYTHONPATH=.` — all tests
   green (no Python changes, but verify nothing broke).
3. Run `npm run tauri dev` — verify:
   - Batch list shows 3 columns: Referenz, Kandidat, Deltas
   - No "Übereinstimmung" column visible
   - Error rows display correctly (red, single error cell)
   - Window is slightly narrower than before
   - All three tabs (Einzelvergleich, Batch, Einstellungen) display
     correctly at the new width

---

## Files changed

| File | Change |
|------|--------|
| `src/views/BatchView.tsx` | Remove Übereinstimmung column, matchPercent function, adjust colgroup |
| `src-tauri/tauri.conf.json` | Window width 1050 → 1000 |

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT modify `engine/report_generator.py` — the PDF batch report
  keeps its Übereinstimmung column.
- Do NOT change `minWidth`, `height`, or `minHeight`.
