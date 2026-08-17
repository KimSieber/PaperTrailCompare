# Sprint PTC-1 — Dialog Adjustments

## Overview

Seven changes to the PaperTrail Compare desktop GUI, grouped into
execution blocks with explicit pause points. Each block ends with
verification steps. Do NOT commit autonomously — pause after each block
and wait for confirmation.

**Execution order:** Block 1 → 2 → 3 → 4 → 5 → 6 → 7 (dependencies
flow downward; later blocks rely on earlier ones being committed).

---

## Block 1 — Version number synchronization + expiry date (A + B)

### 1a. Central version and expiry in `engine/__init__.py`

`engine/__init__.py` already contains `__version__ = "0.1.0"` as the
single source of truth. Add a plain-text expiry date next to it:

```python
__version__ = "0.1.0"
__expiry__ = "2026-12-31"
```

`__expiry__` is an ISO date string (YYYY-MM-DD). The engine checks this
on every invocation; the GUI checks it at startup. Both must block
operation when the date is in the past.

### 1b. Engine expiry guard

In `engine/__main__.py`, add an expiry check as the very first action
in `main()` — before argument parsing, before any subcommand runs:

```python
from datetime import date
from engine import __expiry__

if date.today() > date.fromisoformat(__expiry__):
    print(f"Diese Testversion ist am {__expiry__} abgelaufen. "
          f"Bitte wenden Sie sich an PaperTrail@Sieber-BW.de "
          f"für eine aktuelle Version.", file=sys.stderr)
    sys.exit(2)
```

Exit code 2 distinguishes expiry from runtime errors (exit code 1).

### 1c. Synchronize version across all manifests

Update the version string to `"0.1.0"` (current value, confirming
consistency) in all four locations. Document these locations with a
comment in each file so future maintainers know to update all four:

1. `engine/__init__.py` — `__version__ = "0.1.0"` (already exists)
2. `package.json` — `"version": "0.1.0"`
3. `src-tauri/tauri.conf.json` — `"version": "0.1.0"`
4. `src-tauri/Cargo.toml` — `version = "0.1.0"`

Verify all four files contain the identical version string. If any
differ, align them to `"0.1.0"`.

### 1d. Extend `engine_version` Rust command

The existing `engine_version` command calls `papertrail-engine --version`
and returns a plain version string. Extend the engine's `--version`
output and the Rust command to also return the expiry date and whether
the engine is still valid.

**Python side** (`engine/__main__.py`): change the `--version` handler
to output JSON instead of a plain string:

```python
if args.version:
    from engine import __expiry__
    expired = date.today() > date.fromisoformat(__expiry__)
    print(json.dumps({
        "version": __version__,
        "expiry": __expiry__,
        "expired": expired,
    }))
    sys.exit(0)
```

**Rust side** (`src-tauri/src/lib.rs`): change `engine_version` to
return a struct instead of a String:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineInfo {
    version: String,
    expiry: String,
    expired: bool,
}
```

Modify the `engine_version` command to deserialize the JSON output into
`EngineInfo` and return it.

### Verification (Block 1)

1. `cargo check` in `src-tauri/` — must compile
2. `python -m engine --version` — must output JSON with version, expiry,
   expired fields
3. Set `__expiry__` temporarily to a past date, run
   `python -m engine compare ...` — must print expiry message to stderr
   and exit with code 2. Restore the correct date afterward.
4. Verify all four manifest files contain `"0.1.0"`.
5. Run `pytest` — all existing tests must remain green.

**Pause — wait for confirmation before continuing.**

---

## Block 2 — About dialog via version number click (C)

### 2a. Create `AboutDialog` component

Create `src/components/AboutDialog.tsx` — a modal overlay triggered by
clicking the version number in the sidebar footer.

**Content (top to bottom):**
1. App icon (`engine/assets/512x512.png` — load via Tauri asset
   protocol or import as static asset; if not accessible from the
   frontend, copy to `public/` or `src/assets/`)
2. App name: **PaperTrail Compare**
3. Version: `Version {version}` (from `EngineInfo`)
4. Expiry line: `Testversion gültig bis: {expiry}` (format the ISO date
   as DD.MM.YYYY for German locale display)
5. Horizontal divider
6. `© 2026 Kim Sieber, Stuttgart`
7. Email: `PaperTrail@Sieber-BW.de` — clickable `mailto:` link
8. Website: `https://papertrail.sieber-bw.de` — clickable link (opens
   in external browser via Tauri's opener plugin)

**Styling:**
- Modal overlay with semi-transparent dark backdrop
- Centered white card, rounded corners, max-width ~400px
- Close on clicking backdrop, close on Escape key, close on X button
- Use existing Tailwind utility classes; match the slate color scheme
  of the existing UI

### 2b. Wire version click in sidebar

The version number is displayed in the sidebar/footer area (bottom
left). Find the element showing the version and make it clickable:

- Add `cursor-pointer hover:underline` styling
- On click: call `engine_version` (from Block 1d) to get `EngineInfo`,
  then open `AboutDialog` with that data
- The version display itself should continue showing just the version
  number (not the full About content)

### 2c. Expiry check at app startup

In the top-level `App.tsx` (or equivalent root component):

- On mount, call `engine_version` to get `EngineInfo`
- If `expired === true`: show a blocking dialog (not the About dialog)
  with the message:

  > **Testversion abgelaufen**
  >
  > Diese Testversion von PaperTrail Compare ist am {expiry} abgelaufen.
  > Bitte wenden Sie sich an PaperTrail@Sieber-BW.de für eine aktuelle
  > Version.

  This dialog has NO close button and NO way to dismiss it. The app
  is unusable. The email address should be a clickable mailto: link.
- If not expired: continue normally, no dialog shown.

### Verification (Block 2)

1. `npm run build` — must compile without errors
2. `npm run tauri dev` — app starts, click version number → About
   dialog appears with correct content, closes on backdrop/Escape/X
3. Temporarily set `__expiry__` to a past date, rebuild engine, restart
   app → blocking expiry dialog appears, app is unusable
4. Verify mailto: link and website link open correctly

**Pause — wait for confirmation before continuing.**

---

## Block 3 — Profile dropdown into file selection block (D)

### 3a. Extend `AppConfig` for profile persistence

In `src-tauri/src/lib.rs`, extend the `AppConfig` struct:

```rust
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct AppConfig {
    profile_directory: Option<String>,
    selected_profile_single: Option<String>,
    selected_profile_batch: Option<String>,
}
```

Add two new Tauri commands:

```rust
#[tauri::command]
fn get_selected_profiles(app: tauri::AppHandle)
    -> Result<(Option<String>, Option<String>), String>

#[tauri::command]
fn set_selected_profile(
    app: tauri::AppHandle,
    mode: String,           // "single" or "batch"
    profile_name: Option<String>,
) -> Result<(), String>
```

`get_selected_profiles` returns `(selected_profile_single, selected_profile_batch)`
from `app_config.json`.

`set_selected_profile` updates the corresponding field and writes
`app_config.json`. Register both commands in the Tauri builder.

### 3b. Update `ProfileSelect` component

Modify `src/components/ProfileSelect.tsx`:

- Change the label from `"Vergleichsprofil"` to `"Profil:"`
- Style it to match `FilePickerRow`: same height, same spacing, label
  on the left, dropdown on the right, identical padding and font size.
  The dropdown should visually sit in the same grid/layout as the file
  picker rows so the labels and inputs align vertically.
- Add a `className` prop or wrapper so it can be placed inside the
  white `<section>` block alongside `FilePickerRow` components.

### 3c. Move ProfileSelect into white block — SingleComparisonView

In `src/views/SingleComparisonView.tsx`:

- Remove the `<ProfileSelect>` from its current position (outside the
  white `<section>` block)
- Place it as the **first child** inside the white `<section>` block,
  before the Referenz `FilePickerRow`

Row order inside the white block:
1. Profil (ProfileSelect dropdown)
2. Referenz (FilePickerRow)
3. Kandidat (FilePickerRow)

(Output directory is added in Block 5.)

- On mount, load the persisted profile selection via
  `get_selected_profiles` and use the `single` value
- On profile change, call `set_selected_profile` with mode `"single"`

### 3d. Move ProfileSelect into white block — BatchView

In `src/views/BatchView.tsx`:

- Remove the `<ProfileSelect>` from its current position
- Place it as the **first child** inside the white `<section>` block,
  before the CSV file picker

Row order inside the white block:
1. Profil (ProfileSelect dropdown)
2. Dateiliste (FilePickerRow for CSV)
3. Ausgabeverzeichnis (FilePickerRow for output dir)

- On mount, load persisted profile via `get_selected_profiles`, use
  the `batch` value
- On profile change, call `set_selected_profile` with mode `"batch"`

### Verification (Block 3)

1. `cargo check` — must compile
2. `npm run build` — must compile
3. `npm run tauri dev`:
   - Single tab: ProfileSelect is first row inside white block, same
     visual style as file pickers
   - Batch tab: ProfileSelect is first row inside white block
   - Select a profile in Single, switch to Batch, switch back → Single
     selection preserved
   - Select different profiles in Single and Batch → both preserved
   - Restart app → both selections restored from app_config.json
4. Run `pytest` — all tests green (no engine changes in this block)

**Pause — wait for confirmation before continuing.**

---

## Block 4 — Output directory for single comparison (F)

### 4a. Rust backend: modify `compare_documents`

In `src-tauri/src/lib.rs`, add an `output_dir: Option<String>` parameter
to the `compare_documents` command. If provided, pass `--report` with a
path constructed as `{output_dir}/{timestamp}_Vergleich.pdf`. If not
provided, use the existing default behavior (Documents/YYYY-MM-DD).

Find how the current report path is constructed and make it use the
`output_dir` parameter when present.

### 4b. Default output directory helper

Add a Rust helper function:

```rust
fn default_single_output_dir() -> Result<String, String>
```

This returns the platform-specific Documents directory + today's date
as subdirectory (YYYY-MM-DD format), e.g.:
- macOS: `~/Documents/2026-08-14`
- Windows: `C:\Users\<user>\Documents\2026-08-14`

Use `tauri::api::path::document_dir()` or `dirs::document_dir()` to
get the Documents path. Create the subdirectory only when the comparison
actually runs, not when the path is computed.

Add a Tauri command `get_default_output_dir() -> String` that the
frontend calls to pre-fill the field.

### 4c. Add output directory picker to SingleComparisonView

In `src/views/SingleComparisonView.tsx`:

- Add a new state `outputDir` initialized by calling
  `get_default_output_dir` on mount
- Add a `FilePickerRow` (or equivalent directory picker row) as the
  **last row** inside the white block, after Kandidat:
  - Label: `"Ausgabe"`
  - Shows the directory path
  - "Durchsuchen..." button opens a native directory picker
  - Supports drag-and-drop of a directory (add `"outputDir"` to the
    `DropTarget` type union)

Row order inside the white block after this change:
1. Profil (from Block 3)
2. Referenz
3. Kandidat
4. Ausgabe (new)

- The output directory is NOT persisted — on every fresh load of the
  Single tab, it resets to `Documents/YYYY-MM-DD` (with today's date)
- Pass the `outputDir` to `compare_documents` when invoking

### Verification (Block 4)

1. `cargo check` — must compile
2. `npm run build` — must compile
3. `npm run tauri dev`:
   - Single tab shows 4 rows: Profil, Referenz, Kandidat, Ausgabe
   - Output dir is pre-filled with Documents/YYYY-MM-DD
   - Can change output dir via button or drag-and-drop
   - Run a comparison → report is created in the selected output dir
   - Switch away and back → output dir resets to Documents/YYYY-MM-DD
     (with current date)
4. Run `pytest` — all tests green

**Pause — wait for confirmation before continuing.**

---

## Block 5 — Window start size (E)

### 5a. Set initial window dimensions

In `src-tauri/tauri.conf.json`, find the `windows` array and set the
initial window dimensions so that the Batch tab content fits without
scrolling:

- The Batch tab is the tallest view: white block (3 rows) + start
  button + progress bar + result list (6 visible rows) + report
  button/status below the list
- Calculate approximately: existing header/nav + white block (~200px) +
  button (~50px) + list with 6 rows (~280px) + report button area
  (~60px) + padding/margins (~80px) ≈ 700–750px height
- Set `"height": 750` (adjust if needed after visual verification)
- Set `"width": 900` (or keep existing if already adequate)
- Keep `"resizable": true`

The exact pixel value will likely need fine-tuning. Start with 750 and
verify visually.

### 5b. Fix batch result list to 6 visible rows

In `src/views/BatchView.tsx`, find the batch result list rendering.
Apply a fixed maximum height that shows exactly 6 rows, with overflow
scrolling:

- Each row is approximately 44–48px tall (verify from current styling)
- Set `max-height` to `6 * row_height` (e.g., `max-h-[276px]` for
  46px rows) on the list container
- Add `overflow-y: auto` so excess rows scroll within the list
- The list container height is **static** — it does NOT grow when the
  window is resized. Use a fixed pixel value, not a relative/flex
  value.

### 5c. Ensure report button stays visible

The report button (and OK/error count) that appears after batch
completion must be positioned **below** the fixed-height list, outside
the scrollable area. It should be visible without scrolling when the
window is at its initial size.

Verify that the layout structure is:
```
[White block: Profil + CSV + Output Dir]
[Start button]
[Progress bar]
[Result list — fixed 6 rows, scrolls internally]
[Report button + counts — always visible below list]
```

### Verification (Block 5)

1. `npm run tauri dev`:
   - Window opens at the new size
   - Switch to Batch tab: white block, start button, and space for
     list + report button all visible without scrolling
   - Run a batch with >6 pairs: list shows 6 rows, scrolls internally,
     report button visible below without window scrolling
   - Run a batch with <6 pairs: list shows actual count, no excess
     empty space issues
   - Switch to Single tab: everything fits (Single is shorter, so
     there is extra white space — this is intentional, window size
     does not change between tabs)
   - Window is resizable: shrinking causes the page to need scrolling
     (acceptable), enlarging adds white space (list stays fixed height)
   - Settings tab: fits comfortably

**Pause — wait for confirmation before continuing.**

---

## Block 6 — Batch abort function (G)

### 6a. Rust: store child process handle and add cancel command

In `src-tauri/src/lib.rs`:

Add a shared state to hold the batch child process handle:

```rust
use std::sync::Mutex;
use tauri_plugin_shell::process::CommandChild;

struct BatchChildState(Mutex<Option<CommandChild>>);
```

Register this as managed state in the Tauri builder:

```rust
.manage(BatchChildState(Mutex::new(None)))
```

**Modify `start_batch_compare`:**
- Accept `batch_state: tauri::State<'_, BatchChildState>` as parameter
- After `sidecar.spawn()`, store the `_child` (rename to `child`) in
  the shared state: `*batch_state.0.lock().unwrap() = Some(child);`
- At the end of the function (after the event loop), clear the state:
  `*batch_state.0.lock().unwrap() = None;`
- Also clear on error paths

**Add a new command:**

```rust
#[tauri::command]
fn cancel_batch(batch_state: tauri::State<'_, BatchChildState>) -> Result<(), String> {
    let mut guard = batch_state.0.lock().map_err(|e| e.to_string())?;
    if let Some(child) = guard.take() {
        child.kill().map_err(|e| e.to_string())?;
    }
    Ok(())
}
```

Register `cancel_batch` in the Tauri builder's `invoke_handler`.

### 6b. React: abort button and status in BatchView

In `src/views/BatchView.tsx`:

**Add a red abort button:**
- Shown only while `loading === true` (batch is running)
- Positioned next to the "Vergleich starten" button (not replacing it)
- Styled red: `bg-red-600 text-white hover:bg-red-500`
- Label: `"Abbrechen"`
- On click: calls `invoke("cancel_batch")`, then sets a state flag
  `cancelled = true`

**Handle abort in the batch flow:**
- The `start_batch_compare` invoke will reject (error) when the
  sidecar is killed. In the `catch` block, check if `cancelled` is
  true. If so, do NOT show the error as an error message. Instead:
  1. Add a virtual "abort" row to the result list:
     - Display as a red-styled row
     - Text: `"Abbruch"` (in the pair status area)
     - No file names, no delta count
  2. Show a status text below the list (where the report button would
     normally appear):
     `"Batch abgebrochen nach {rows.length} von {progress.total} Paaren"`
     Styled in red.
  3. Do NOT show the report button (no batch report was generated)

**Button visibility rules:**
- Before batch start: "Vergleich starten" visible, "Abbrechen" hidden
- During batch: both visible side by side
- After completion: "Vergleich starten" visible (for re-run),
  "Abbrechen" hidden
- After abort: "Vergleich starten" visible, "Abbrechen" hidden

### Verification (Block 6)

1. `cargo check` — must compile
2. `npm run build` — must compile
3. `npm run tauri dev`:
   - Start a batch with many pairs → red "Abbrechen" button appears
     next to start button
   - Click "Abbrechen" → batch stops, completed rows remain in list,
     red "Abbruch" row appears at end, status text shows
     "Batch abgebrochen nach X von Y Paaren", no report button
   - Already-generated single reports in the output dir are intact
   - Start a new batch after abort → works normally
   - Let a batch complete without abort → no "Abbrechen" button,
     report button appears as usual
4. Run `pytest` — all tests green (no engine logic changes)

**Pause — wait for confirmation before continuing.**

---

## Block 7 — Final verification and commit

After all blocks are confirmed individually:

1. Run `pytest` — full green
2. Run `cargo check` — clean
3. Run `npm run build` — clean
4. Run `npm run tauri dev` — full manual walkthrough:
   - Version number visible in sidebar, clickable → About dialog
   - About dialog shows icon, name, version, expiry, copyright, email,
     website
   - Profile dropdown in Single and Batch: inside white block, first
     row, visually aligned with file pickers, persisted separately
   - Single: output dir picker as 4th row, pre-filled with
     Documents/YYYY-MM-DD
   - Batch: list fixed at 6 rows, report button visible without
     scrolling
   - Batch abort: red button, clean stop, "Abbruch" row in list
   - Window size comfortable for all three tabs

**Commit: `feat(sprint-ptc1): dialog adjustments — version, expiry, about, profile layout, output dir, window size, batch abort`**

---

## Files touched (summary)

| File | Blocks |
|---|---|
| `engine/__init__.py` | 1a |
| `engine/__main__.py` | 1b, 1d |
| `package.json` | 1c |
| `src-tauri/tauri.conf.json` | 1c, 5a |
| `src-tauri/Cargo.toml` | 1c |
| `src-tauri/src/lib.rs` | 1d, 3a, 4a, 4b, 6a |
| `src/components/AboutDialog.tsx` | 2a (new) |
| `src/components/ProfileSelect.tsx` | 3b |
| `src/views/SingleComparisonView.tsx` | 2b, 3c, 4c |
| `src/views/BatchView.tsx` | 3d, 5b, 5c, 6b |
| `src/App.tsx` (or root component) | 2c |
