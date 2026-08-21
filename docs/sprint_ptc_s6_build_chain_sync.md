# Sprint PTC-S6 — Integrate Version Sync into Build Chain

## Overview

Wire `tools/sync_version.py` into the Tauri build chain so that
version and expiry from the central `VERSION` file are automatically
stamped into all four config files on every `npm run tauri dev` and
`npm run tauri build`. After this change, editing the `VERSION` file
is the only step needed — no manual script call required.

**Approach:** Extend the existing `packaging/prepare_sidecar.mjs`
(which already provides cross-platform Python resolution via
`resolvePython()`) with a `--sync-version` mode, add an npm script,
and prepend it to the Tauri `beforeDevCommand` / `beforeBuildCommand`.

**Execution order:** Step 1 → 2 → 3 → Verification.

Do NOT run `git commit` or `git push` — Kim commits manually after
verification.

---

## Step 1 — Add `--sync-version` mode to `prepare_sidecar.mjs`

In `packaging/prepare_sidecar.mjs`, extend the mode dispatch at the
bottom of the file.

**Find the existing dispatch block:**

```javascript
let exitCode;
if (mode === "--dev") {
  const script = path.join(__dirname, "dev_sidecar.sh");
  exitCode = run("bash", [script]);
} else if (mode === "--build") {
  const pythonCmd = resolvePython();
  const script = path.join(__dirname, "build_sidecar.py");
  exitCode = run(pythonCmd, [script]);
} else {
  console.error(`prepare_sidecar.mjs: unbekannter Modus '${mode}' - erwartet --dev oder --build.`);
  exitCode = 1;
}
```

**Replace with:**

```javascript
let exitCode;
if (mode === "--sync-version") {
  // Synchronisiert Version und Ablaufdatum aus der zentralen VERSION-Datei
  // in die vier Konfigurationsdateien (engine/__init__.py, package.json,
  // tauri.conf.json, Cargo.toml). Läuft automatisch vor jedem Dev- und
  // Release-Build, damit die VERSION-Datei die einzige Pflegestelle bleibt.
  const pythonCmd = resolvePython();
  const script = path.join(repoRoot, "tools", "sync_version.py");
  exitCode = run(pythonCmd, [script]);
} else if (mode === "--dev") {
  const script = path.join(__dirname, "dev_sidecar.sh");
  exitCode = run("bash", [script]);
} else if (mode === "--build") {
  const pythonCmd = resolvePython();
  const script = path.join(__dirname, "build_sidecar.py");
  exitCode = run(pythonCmd, [script]);
} else {
  console.error(`prepare_sidecar.mjs: unbekannter Modus '${mode}' - erwartet --sync-version, --dev oder --build.`);
  exitCode = 1;
}
```

Also update the file-level JSDoc comment to mention the new mode.

**Find in the comment block near the top:**

```javascript
// --dev   : schreibt packaging/dev_sidecar.sh (schnell, kein PyInstaller)
// --build : baut den echten PyInstaller-Sidecar (packaging/build_sidecar.py)
```

**Replace with:**

```javascript
// --sync-version : synchronisiert VERSION → 4 Konfigurationsdateien
// --dev          : schreibt packaging/dev_sidecar.sh (schnell, kein PyInstaller)
// --build        : baut den echten PyInstaller-Sidecar (packaging/build_sidecar.py)
```

**Pause — wait for confirmation before continuing.**

---

## Step 2 — Add npm script and update Tauri commands

### 2a. Add npm script in `package.json`

Add a `sync-version` script to the `"scripts"` section.

**Find:**

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "tauri": "tauri",
  "sidecar:dev": "node packaging/prepare_sidecar.mjs --dev",
  "sidecar:build": "node packaging/prepare_sidecar.mjs --build"
},
```

**Replace with:**

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "tauri": "tauri",
  "sync-version": "node packaging/prepare_sidecar.mjs --sync-version",
  "sidecar:dev": "node packaging/prepare_sidecar.mjs --dev",
  "sidecar:build": "node packaging/prepare_sidecar.mjs --build"
},
```

### 2b. Prepend sync to Tauri build commands in `tauri.conf.json`

**Find:**

```json
"beforeDevCommand": "npm run sidecar:dev && npm run dev",
```

**Replace with:**

```json
"beforeDevCommand": "npm run sync-version && npm run sidecar:dev && npm run dev",
```

**Find:**

```json
"beforeBuildCommand": "npm run sidecar:build && npm run build",
```

**Replace with:**

```json
"beforeBuildCommand": "npm run sync-version && npm run sidecar:build && npm run build",
```

**Pause — wait for confirmation before continuing.**

---

## Step 3 — Update VERSION file to correct expiry

The `VERSION` file currently has `expiry=2026-10-31`, but the correct
value (before the sync script overwrote it) was `2026-11-30`.

**In the `VERSION` file, change:**

```
expiry=2026-10-31
```

**To:**

```
expiry=2026-11-30
```

Do NOT run `sync_version.py` manually — the next `npm run tauri dev`
will do it automatically.

### Verification (Step 3)

1. Run `npm run tauri dev` — this should:
   - Automatically run `sync-version` (prints 4 checkmarks to console)
   - Then prepare the sidecar
   - Then start the dev server
   - App opens with correct version `0.2.1` in sidebar (instantly)
   - Click ⓘ → About dialog shows `0.2.1` and expiry `30.11.2026`
2. Verify `engine/__init__.py` now has `__expiry__ = "2026-11-30"`
   (written automatically by the sync script during the build).
3. Run `pytest` from project root with `PYTHONPATH=.` — all tests
   green.

---

## Files changed

| File | Change |
|------|--------|
| `packaging/prepare_sidecar.mjs` | Add `--sync-version` mode |
| `package.json` | Add `sync-version` npm script |
| `src-tauri/tauri.conf.json` | Prepend `sync-version` to both build commands |
| `VERSION` | Fix expiry to `2026-11-30` |

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT modify `tools/sync_version.py` — it stays unchanged.
- Do NOT modify `engine/__init__.py` manually — the sync script
  handles it.
- The sync script must run successfully on both macOS and Windows
  (uses existing `resolvePython()` from `prepare_sidecar.mjs`).
