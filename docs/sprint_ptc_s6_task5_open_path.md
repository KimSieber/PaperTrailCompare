# Sprint PTC-S6 Task 5 — Open Path on Network Drives

## Overview

The "Open report" button fails on network drives and exe-relative
paths because `tauri-plugin-opener` restricts `openPath()` to
`$DOCUMENT/PaperTrailCompare/**` and `$HOME/**`. Widen the scope
to allow all paths.

Single-file change, no pause points needed.

Do NOT run `git commit` or `git push`.

---

## Step 1 — Widen opener path scope

In `src-tauri/capabilities/default.json`, find the opener permission:

```json
{
  "identifier": "opener:allow-open-path",
  "allow": [
    { "path": "$DOCUMENT/PaperTrailCompare/**" },
    { "path": "$HOME/**" }
  ]
}
```

Replace with:

```json
{
  "identifier": "opener:allow-open-path",
  "allow": [
    { "path": "**" }
  ]
}
```

### Verification

1. Run `cargo check` in `src-tauri/` — must compile.
2. Run `npm run build` — must compile.
3. Run `pytest` — all tests green.
