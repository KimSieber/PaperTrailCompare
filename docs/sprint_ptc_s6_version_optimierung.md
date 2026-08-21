# Sprint PTC-S6 — Version Number Optimization (Tasks 1–3)

## Overview

Three related changes to eliminate slow sidecar startup delays for the
version number display and improve visual affordance of the clickable
version text. All three tasks share the same code area (Sidebar, App
root, Rust commands) and are implemented together.

**Problem summary:**
1. Version text shows "Version …" for 30–60+ seconds at startup because
   it waits for the Python sidecar (PyInstaller cold start).
2. Clicking the version text to open the About dialog spawns a **new**
   sidecar process (another 17–30+ seconds) instead of reusing the
   already-fetched data.
3. The version text is clickable but has no visual indicator — users
   don't discover the About dialog.

**Solution summary:**
- New lightweight Rust command `get_app_version` (compile-time constant,
  no sidecar) for instant version display.
- Consolidate: `engine_version` (sidecar) is called **once** in
  `App.tsx`, result passed as prop to `Sidebar` — eliminates the
  duplicate sidecar spawn.
- About dialog click uses cached prop data — no sidecar call on click.
- Info icon (ⓘ) added left of version text with hover transition.

**Execution order:** Step 1 → 2 → 3 → 4 → Verification.

Do NOT run `git commit` or `git push` — Kim commits manually after
pytest and GUI verification.

---

## Step 1 — New Rust command `get_app_version`

In `src-tauri/src/lib.rs`, add a new Tauri command that returns the
app version as a plain string from the compile-time constant. This
requires no sidecar process and returns instantly.

### 1a. Add the command

Add this function anywhere above the `run()` function:

```rust
/// Gibt die App-Version als compile-time Konstante zurück (aus
/// Cargo.toml, ohne Sidecar-Prozess). Für die sofortige
/// Versionsanzeige in der Sidebar — der vollständige EngineInfo-Abruf
/// (mit Ablaufdatum) läuft separat im Hintergrund.
#[tauri::command]
fn get_app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}
```

### 1b. Register the command

In the `run()` function, add `get_app_version` to the
`invoke_handler` macro. Find the existing handler registration:

```rust
.invoke_handler(tauri::generate_handler![
    engine_version,
    compare_documents,
    ...
])
```

Add `get_app_version` as the first entry:

```rust
.invoke_handler(tauri::generate_handler![
    get_app_version,
    engine_version,
    compare_documents,
    ...
])
```

### Verification (Step 1)

Run `cargo check` in `src-tauri/` — must compile without errors.

**Pause — wait for confirmation before continuing.**

---

## Step 2 — Consolidate `engine_version` in `App.tsx`

Currently both `App.tsx` and `Sidebar.tsx` independently call
`engine_version` (spawning two sidecar processes at startup). Refactor
so `App.tsx` is the single owner of `engineInfo` and passes it down.

### 2a. Add `appVersion` state and fetch

Add a new state for the instant version string and fetch it on mount.
Also change `expiredInfo` to store the full `engineInfo` always (not
only when expired), so it can be passed to Sidebar.

**Replace the current state + useEffect block:**

```typescript
const [expiredInfo, setExpiredInfo] = useState<EngineInfo | null>(null);

useEffect(() => {
  (async () => {
    try {
      const info = await invoke<EngineInfo>("engine_version");
      if (info.expired) {
        setExpiredInfo(info);
      }
    } catch {
      // Engine (noch) nicht erreichbar - kein Blocker beim Start.
    }
  })();
}, []);
```

**With:**

```typescript
const [appVersion, setAppVersion] = useState<string | null>(null);
const [engineInfo, setEngineInfo] = useState<EngineInfo | null>(null);

// Sofortige Versionsanzeige aus Cargo.toml (compile-time, kein Sidecar).
useEffect(() => {
  invoke<string>("get_app_version")
    .then((v) => setAppVersion(v))
    .catch(() => {});
}, []);

// Vollständiger Engine-Check (Sidecar, dauert 10-60s) — läuft im
// Hintergrund, blockiert die Versionsanzeige nicht mehr.
useEffect(() => {
  invoke<EngineInfo>("engine_version")
    .then((info) => setEngineInfo(info))
    .catch(() => {});
}, []);
```

### 2b. Update the expiry check

The expiry-blocking render currently checks `if (expiredInfo)`. Change
it to check `engineInfo?.expired`:

```typescript
if (engineInfo?.expired) {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-slate-900/90">
      <div className="max-w-md rounded-lg bg-white p-8 text-center shadow-xl">
        <h1 className="text-lg font-semibold text-red-600">Testversion abgelaufen</h1>
        <p className="mt-3 text-sm text-slate-700">
          Diese Testversion von PaperTrail Compare ist am{" "}
          {formatGermanDate(engineInfo.expiry)} abgelaufen. Bitte wenden Sie sich an{" "}
          <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">
            {CONTACT_EMAIL}
          </a>{" "}
          für eine aktuelle Version.
        </p>
      </div>
    </div>
  );
}
```

### 2c. Pass props to Sidebar

Change the `Sidebar` invocation to pass both new props:

**Find:**
```tsx
<Sidebar active={activeView} onSelect={setActiveView} />
```

**Replace with:**
```tsx
<Sidebar
  active={activeView}
  onSelect={setActiveView}
  appVersion={appVersion}
  engineInfo={engineInfo}
/>
```

### 2d. Remove unused import

The `expiredInfo` state variable no longer exists. Verify there are no
remaining references to `expiredInfo` in the file. The `EngineInfo`
type import must stay (it's used for `engineInfo` state).

### Verification (Step 2)

Run `npm run build` — must compile without TypeScript errors. (It will
show TS errors until Step 3 updates Sidebar's prop types, so if you
prefer, continue to Step 3 before verifying.)

**Pause — wait for confirmation before continuing.**

---

## Step 3 — Refactor `Sidebar.tsx` (props, instant click, icon)

### 3a. Update imports

**Find the current imports at the top of the file:**

```typescript
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { EngineInfo, ViewKey } from "../types";
import { AboutDialog } from "../components/AboutDialog";
import { CompareIcon, QueueIcon, SettingsIcon } from "./icons";
```

**Replace with:**

```typescript
import { useState } from "react";
import type { ReactElement } from "react";
import type { EngineInfo, ViewKey } from "../types";
import { AboutDialog } from "../components/AboutDialog";
import { CompareIcon, QueueIcon, SettingsIcon, InfoIcon } from "./icons";
```

Removed: `useEffect` (no longer needed), `invoke` (no more direct
Tauri calls from Sidebar).
Added: `InfoIcon` import.

### 3b. Update SidebarProps interface and destructuring

**Find:**

```typescript
interface SidebarProps {
  active: ViewKey;
  onSelect: (key: ViewKey) => void;
}

export function Sidebar({ active, onSelect }: SidebarProps) {
```

**Replace with:**

```typescript
interface SidebarProps {
  active: ViewKey;
  onSelect: (key: ViewKey) => void;
  appVersion: string | null;
  engineInfo: EngineInfo | null;
}

export function Sidebar({ active, onSelect, appVersion, engineInfo }: SidebarProps) {
```

### 3c. Remove own state and fetch logic

**Delete the entire block** from `const [engineInfo` through the
closing `}, []);` of the useEffect. This is the block to remove:

```typescript
const [engineInfo, setEngineInfo] = useState<EngineInfo | null>(null);
const [showAbout, setShowAbout] = useState(false);

async function fetchEngineInfo(): Promise<EngineInfo | null> {
  try {
    const info = await invoke<EngineInfo>("engine_version");
    setEngineInfo(info);
    return info;
  } catch {
    return null;
  }
}

useEffect(() => {
  void fetchEngineInfo();
}, []);

async function handleVersionClick() {
  const info = await fetchEngineInfo();
  if (info) {
    setShowAbout(true);
  }
}
```

**Replace with:**

```typescript
const [showAbout, setShowAbout] = useState(false);

function handleVersionClick() {
  if (engineInfo) {
    setShowAbout(true);
  }
}
```

Note: `handleVersionClick` is now synchronous — no `async`, no
`await`, no sidecar call. It opens the dialog instantly using the
`engineInfo` prop from `App.tsx`.

### 3d. Update the version button with InfoIcon

**Find the version button:**

```tsx
<button
  type="button"
  onClick={handleVersionClick}
  className="cursor-pointer border-t border-slate-800 px-5 py-3 text-left text-xs text-slate-500 hover:underline"
>
  Version {engineInfo?.version ?? "…"}
</button>
```

**Replace with:**

```tsx
<button
  type="button"
  onClick={handleVersionClick}
  className="flex w-full items-center gap-2 border-t border-slate-800 px-5 py-3 text-left text-xs text-slate-400 transition-colors hover:text-slate-200"
>
  <InfoIcon className="h-3.5 w-3.5 shrink-0" />
  Version {appVersion ?? "…"}
</button>
```

Changes:
- `flex items-center gap-2` for icon + text layout
- `w-full` to maintain full-width click area
- `text-slate-400` base (brighter than old `text-slate-500`)
- `transition-colors hover:text-slate-200` (smooth hover brightening)
- `hover:underline` removed (the icon + color change is the affordance)
- Version source: `appVersion` prop (instant) instead of
  `engineInfo?.version` (slow sidecar)
- `InfoIcon` with `h-3.5 w-3.5` (slightly smaller than nav icons)

### Verification (Step 3)

Run `npm run build` — must compile without TypeScript errors.

**Pause — wait for confirmation before continuing.**

---

## Step 4 — Add `InfoIcon` to `icons.tsx`

In `src/layout/icons.tsx`, add the `InfoIcon` component after
`SettingsIcon`. It uses the same `Base` wrapper as all other icons
(consistent stroke style).

**Add at the end of the file:**

```typescript
export function InfoIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <circle cx="12" cy="8" r="0.5" fill="currentColor" stroke="none" />
    </Base>
  );
}
```

This draws: a circle outline, a vertical line for the "i" body
(12→16), and a small filled dot for the "i" tittle at y=8. The
`fill="currentColor"` on the dot and `stroke="none"` override the
Base defaults for that element only. The overall style matches the
hand-drawn, minimal look of the existing icon set.

### Verification (Step 4)

1. Run `npm run build` — must compile without errors.
2. Run `npm run tauri dev` — verify:
   - Version number appears **instantly** (no "Version …" delay)
   - ⓘ icon is visible left of the version text in the sidebar footer
   - Hover over version text → text brightens to near-white
   - Click version text → About dialog opens **instantly**
   - About dialog shows correct version, expiry date, links
   - Close About dialog via backdrop / Escape / X
   - Expiry blocking still works (temporarily set `__expiry__` to a
     past date in `engine/__init__.py`, restart, verify blocking dialog)
3. Run `pytest` from project root with `PYTHONPATH=.` — all tests green.

---

## Files changed

| File | Change |
|------|--------|
| `src-tauri/src/lib.rs` | Add `get_app_version` command + register |
| `src/App.tsx` | Add `appVersion` state, keep single `engineInfo`, pass both as props |
| `src/layout/Sidebar.tsx` | Receive props, remove own fetch, instant click, InfoIcon |
| `src/layout/icons.tsx` | Add `InfoIcon` component |

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT modify any Python engine files.
- Do NOT modify `AboutDialog.tsx` — it stays unchanged.
- Do NOT add external icon libraries — `InfoIcon` uses the existing
  `Base` wrapper.
