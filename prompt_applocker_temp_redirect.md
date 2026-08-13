# Redirect PyInstaller temp directory to AppLocker-whitelisted path (Windows only)

## Context

On corporate Windows machines, AppLocker blocks execution of `tesseract.exe`
from `%TEMP%\_MEIxxxxxx\` (where PyInstaller `--onefile` unpacks bundled
files at runtime). The customer's IT department has whitelisted
`%LocalAppData%\SVI` (including all subdirectories) in AppLocker.

PyInstaller's bootloader uses the Windows `GetTempPath()` API, which reads
the `TMP` → `TEMP` environment variable chain. By overriding `TEMP` and
`TMP` in the sidecar child process's environment, the `_MEI` directory is
created under the whitelisted path instead.

## Goal

Modify `src-tauri/src/lib.rs` so that on Windows, every sidecar invocation
sets `TEMP` and `TMP` to `%LocalAppData%\SVI\PaperTrail Compare\` in the
child process environment. The directory must be created if it does not
exist. On macOS, no environment override is applied.

## Implementation steps

### Step 1 — Add a helper function

Add a new function `sidecar_env_overrides()` in `src-tauri/src/lib.rs`
(place it before `engine_version`, after the existing struct definitions
and `resolve_profile_path`):

```rust
use std::collections::HashMap;

/// On Windows, returns environment overrides that redirect TEMP/TMP to an
/// AppLocker-whitelisted directory. On other platforms, returns an empty map.
///
/// Background: PyInstaller --onefile unpacks bundled files (including
/// tesseract.exe) into %TEMP%\_MEIxxxxxx at runtime. Corporate AppLocker
/// policies block .exe execution from %TEMP%. The customer's IT has
/// whitelisted %LOCALAPPDATA%\SVI (incl. subdirectories), so redirecting
/// the temp path there lets tesseract.exe run without code-signing.
fn sidecar_env_overrides() -> HashMap<String, String> {
    let mut env = HashMap::new();

    #[cfg(target_os = "windows")]
    {
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            let svi_tmp = format!("{}\\SVI\\PaperTrail Compare", local_app_data);
            // create_dir_all is safe: it only creates missing directories
            // and never modifies existing ones or their contents.
            let _ = std::fs::create_dir_all(&svi_tmp);
            env.insert("TEMP".to_string(), svi_tmp.clone());
            env.insert("TMP".to_string(), svi_tmp);
        }
    }

    env
}
```

### Step 2 — Wire into all three sidecar call sites

There are exactly three places in `lib.rs` that call
`app.shell().sidecar("papertrail-engine")`. Each must get `.envs()`
inserted into the call chain.

**2a) `engine_version`** — find:
```rust
let output = sidecar
    .args(["--version"])
    .output()
```
Change to:
```rust
let output = sidecar
    .args(["--version"])
    .envs(sidecar_env_overrides())
    .output()
```

**2b) `compare_documents`** — find:
```rust
let output = sidecar
    .args(cli_args)
    .output()
```
Change to:
```rust
let output = sidecar
    .args(cli_args)
    .envs(sidecar_env_overrides())
    .output()
```

**2c) `start_batch_compare`** — find:
```rust
let (mut rx, mut _child) = sidecar.args(cli_args).spawn()
```
Change to:
```rust
let (mut rx, mut _child) = sidecar.args(cli_args).envs(sidecar_env_overrides()).spawn()
```

### Step 3 — Verify

1. Run `cargo check` (or `cargo build`) in `src-tauri/` to confirm
   compilation succeeds on macOS. The `#[cfg(target_os = "windows")]`
   block will be compiled out, so `sidecar_env_overrides()` returns an
   empty HashMap on macOS — no behavioral change.
2. Run `npm run tauri dev` and confirm the app starts and Single + Batch
   comparison still work.
3. Check that `HashMap` is imported from `std::collections` — it may
   already be imported; if not, add the import.

## Constraints

- **Only** modify `src-tauri/src/lib.rs`. No changes to the Python engine,
  PyInstaller spec, frontend code, or any other file.
- Do **not** use `std::env::set_var` (that mutates the parent process's
  environment and is not thread-safe). The `.envs()` approach only affects
  the child process.
- Do **not** call `.env_clear()` — we want the child to inherit the full
  parent environment, only overriding TEMP/TMP.
- The `#[cfg(target_os = "windows")]` guard ensures zero impact on macOS.
- Commit message: `fix: redirect sidecar temp dir to AppLocker-whitelisted path (Windows)`
