# Sprint PTC-S6 Task 6 — Output Directory Default

## Overview

Change the default output directory for both Single and Batch
comparison to a path relative to the executable location, with
username and timestamp subdirectories:

```
{exe_parent}/../PTC-Vergleich/{username}/YYYY-MM-DD_HH-MM-SS/
```

**Behavior:**
- On tab mount: pre-fill the output dir field with the **base path**
  (without timestamp): `{exe_parent}/../PTC-Vergleich/{username}/`
- On comparison start: if the user has NOT manually changed the path,
  append a fresh `YYYY-MM-DD_HH-MM-SS/` timestamp subdirectory and
  use that as the actual output directory.
- If the user HAS manually picked a directory via "Durchsuchen…" or
  drag-and-drop, use that path as-is — no timestamp appended.
- Applies identically to Single and Batch tabs.

**Username source:**
- macOS/Linux: `std::env::var("USER")`
- Windows: `std::env::var("USERNAME")`

**Execution order:** Step 1 → 2 → 3 → Verification.

Do NOT run `git commit` or `git push` — Kim commits manually after
verification.

---

## Step 1 — Modify `get_default_output_dir` in Rust

### 1a. Replace the current implementation

The current `get_default_output_dir` returns
`Documents/PaperTrail Compare/YYYY-MM-DD`. Replace it entirely.

**Find the current function:**

```rust
#[tauri::command]
fn get_default_output_dir(app: tauri::AppHandle) -> Result<String, String> {
    let dir = app
        .path()
        .document_dir()
        .map_err(|e| e.to_string())?
        .join("PaperTrail Compare")
        .join(chrono::Local::now().format("%Y-%m-%d").to_string());
    Ok(dir.to_string_lossy().to_string())
}
```

**Replace with:**

```rust
/// Ermittelt den Benutzernamen aus der Umgebungsvariable (USER auf
/// macOS/Linux, USERNAME auf Windows). Fallback "default" falls
/// keiner gesetzt ist.
fn current_username() -> String {
    #[cfg(target_os = "windows")]
    {
        std::env::var("USERNAME").unwrap_or_else(|_| "default".to_string())
    }
    #[cfg(not(target_os = "windows"))]
    {
        std::env::var("USER").unwrap_or_else(|_| "default".to_string())
    }
}

/// Vorbelegung für das Ausgabeverzeichnis (Einzel- und Batch-Vergleich).
/// Gibt den Basispfad OHNE Zeitstempel zurück:
///   {exe_parent}/../PTC-Vergleich/{username}/
///
/// Der Zeitstempel-Unterordner (YYYY-MM-DD_HH-MM-SS) wird erst beim
/// tatsächlichen Vergleichsstart vom Frontend angehängt — so hat jeder
/// Lauf ein eigenes Verzeichnis, ohne Kollisionen bei aufeinanderfolgenden
/// Vergleichen. Wird das Verzeichnis vom Benutzer manuell per
/// "Durchsuchen…" überschrieben, entfällt der Zeitstempel komplett.
#[tauri::command]
fn get_default_output_dir() -> Result<String, String> {
    let exe_path = std::env::current_exe().map_err(|e| e.to_string())?;
    let exe_dir = exe_path
        .parent()
        .ok_or("Konnte Exe-Verzeichnis nicht ermitteln")?;
    let base_dir = exe_dir
        .join("..")
        .join("PTC-Vergleich")
        .join(current_username());
    // canonicalize() nicht verwenden - das Verzeichnis existiert noch
    // nicht. Stattdessen den Pfad mit join("..") belassen; das OS
    // löst relative Segmente beim tatsächlichen Zugriff auf.
    Ok(base_dir.to_string_lossy().to_string())
}
```

**Note:** The `app: tauri::AppHandle` parameter is removed — the
function no longer needs it (no `document_dir` call). Make sure the
command registration in `invoke_handler` still works without the
`AppHandle` (Tauri injects `AppHandle` only when the function
signature requests it — removing it is fine).

### Verification (Step 1)

Run `cargo check` in `src-tauri/` — must compile without errors.

**Pause — wait for confirmation before continuing.**

---

## Step 2 — Update SingleComparisonView.tsx

### 2a. Add `isCustomDir` tracking state

After the existing `outputDir` state declaration, add a boolean that
tracks whether the user has manually selected a directory:

**Find:**

```typescript
const [outputDir, setOutputDir] = useState("");
```

**Add after it:**

```typescript
const [isCustomDir, setIsCustomDir] = useState(false);
```

### 2b. Mark manual directory selection as custom

In the `pickOutputDir` function, set the custom flag when the user
picks a directory:

**Find:**

```typescript
async function pickOutputDir() {
  const path = await open({ multiple: false, directory: true });
  if (typeof path === "string") {
    setOutputDir(path);
  }
}
```

**Replace with:**

```typescript
async function pickOutputDir() {
  const path = await open({ multiple: false, directory: true });
  if (typeof path === "string") {
    setOutputDir(path);
    setIsCustomDir(true);
  }
}
```

### 2c. Mark drag-and-drop as custom

In the `useDragDropTarget` `onDrop` callback, find the `outputDir`
branch:

**Find the line:**

```typescript
setOutputDir(path);
```

(the one inside the `else` branch for the `"outputDir"` target)

**Add after it:**

```typescript
setIsCustomDir(true);
```

### 2d. Add timestamp helper function

Add a helper function at the top of the file (after the imports,
before the component function) that generates a timestamp string:

```typescript
/** Erzeugt einen Zeitstempel im Format YYYY-MM-DD_HH-MM-SS für die
 * Ausgabeverzeichnis-Vorbelegung. */
function nowTimestamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
}
```

### 2e. Append timestamp in handleCompare

In `handleCompare`, the output dir is passed to `compare_documents`.
Before the invoke call, compute the effective output dir:

**Find the invoke call:**

```typescript
const compareResult = await invoke<CompareResult>("compare_documents", {
  refPath,
  cndPath,
  profileName: profileName || undefined,
  outputDir: outputDir || undefined,
});
```

**Replace with:**

```typescript
const effectiveOutputDir = isCustomDir
  ? outputDir
  : `${outputDir}/${nowTimestamp()}`;
const compareResult = await invoke<CompareResult>("compare_documents", {
  refPath,
  cndPath,
  profileName: profileName || undefined,
  outputDir: effectiveOutputDir || undefined,
});
```

### Verification (Step 2)

Run `npm run build` — must compile without TypeScript errors.

**Pause — wait for confirmation before continuing.**

---

## Step 3 — Update BatchView.tsx

### 3a. Add default output dir loading and custom tracking

The BatchView currently starts with an empty `outputDir`. Add the
same default-loading logic as SingleComparisonView.

**Find:**

```typescript
const [outputDir, setOutputDir] = useState("");
```

**Replace with:**

```typescript
const [outputDir, setOutputDir] = useState("");
const [isCustomDir, setIsCustomDir] = useState(false);
```

**Add a useEffect to load the default** (add after the existing state
declarations, before the `useDragDropTarget` block). Also add the
necessary import of `useEffect` if not already imported:

```typescript
useEffect(() => {
  invoke<string>("get_default_output_dir")
    .then(setOutputDir)
    .catch(() => {});
}, []);
```

Make sure `useEffect` is imported from React. Check the existing
import line — it currently imports `useRef, useState`. Add `useEffect`:

**Find:**

```typescript
import { useRef, useState } from "react";
```

**Replace with:**

```typescript
import { useEffect, useRef, useState } from "react";
```

### 3b. Mark manual directory selection as custom

**Find the `pickOutputDir` function:**

```typescript
async function pickOutputDir() {
  const path = await open({ multiple: false, directory: true });
  if (typeof path === "string") {
    setOutputDir(path);
  }
}
```

**Replace with:**

```typescript
async function pickOutputDir() {
  const path = await open({ multiple: false, directory: true });
  if (typeof path === "string") {
    setOutputDir(path);
    setIsCustomDir(true);
  }
}
```

### 3c. Mark drag-and-drop as custom

In the `useDragDropTarget` `onDrop` callback, find the `outputDir`
branch:

**Find:**

```typescript
setOutputDir(path);
```

(the one inside the `else` branch for the `"outputDir"` target)

**Add after it:**

```typescript
setIsCustomDir(true);
```

### 3d. Add timestamp helper and apply in handleStart

Add the same `nowTimestamp` helper function (or import it from a
shared location — but to keep changes minimal, duplicate it at the
top of BatchView.tsx):

```typescript
function nowTimestamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
}
```

In `handleStart`, compute the effective output dir before the invoke:

**Find:**

```typescript
const output = await invoke<BatchOutput>("start_batch_compare", {
  filelistPath: csvPath,
  outputDir,
```

**Replace with:**

```typescript
const effectiveOutputDir = isCustomDir
  ? outputDir
  : `${outputDir}/${nowTimestamp()}`;
const output = await invoke<BatchOutput>("start_batch_compare", {
  filelistPath: csvPath,
  outputDir: effectiveOutputDir,
```

Make sure the rest of the invoke call (profileName, etc.) remains
unchanged.

### Verification (Step 3)

1. Run `npm run build` — must compile without TypeScript errors.
2. Run `pytest` from project root with `PYTHONPATH=.` — all tests
   green.
3. Run `npm run tauri dev` — verify:
   - **Single tab:** output dir field pre-filled with
     `{exe_dir}/../PTC-Vergleich/{your_username}/` (no timestamp yet)
   - Run a comparison → report saved in
     `.../PTC-Vergleich/{username}/YYYY-MM-DD_HH-MM-SS/`
   - Run another comparison immediately → different timestamp dir
   - Manually pick a custom dir via "Durchsuchen…" → report saved
     directly in the custom dir (no timestamp subdir appended)
   - **Batch tab:** same behavior — pre-filled default, timestamp on
     run, custom dir respected as-is
   - Switch tabs back and forth → default reloads on mount

---

## Files changed

| File | Change |
|------|--------|
| `src-tauri/src/lib.rs` | `get_default_output_dir` uses exe-relative path + username; new `current_username()` helper |
| `src/views/SingleComparisonView.tsx` | `isCustomDir` tracking, `nowTimestamp()`, timestamp append on compare |
| `src/views/BatchView.tsx` | Default output dir loading, `isCustomDir` tracking, `nowTimestamp()`, timestamp append on batch start |

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT modify the Python engine.
- Do NOT create the output directory in `get_default_output_dir` — it
  is created by the comparison commands when the comparison actually
  runs.
- The path separator in the timestamp append (`/`) works on both macOS
  and Windows because Tauri/Rust normalizes paths. However, if issues
  arise on Windows, use `\\` or `path.join()` equivalent in TypeScript.
