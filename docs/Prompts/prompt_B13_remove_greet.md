# Claude Code Prompt: B13 — Remove Dead Code `greet()` from lib.rs

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.

Sprint PTC-S5 (Housekeeping). This is a trivial dead-code removal.

**Do NOT run `git commit` or `git push`** — Kim commits manually after verification.

---

## Problem

`src-tauri/src/lib.rs` contains the Tauri template function `greet()` (~line 28):

```rust
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}
```

This function has **no caller** anywhere in the application — it is leftover
boilerplate from `cargo tauri init`. It is also still registered in the
`invoke_handler` macro inside `pub fn run()`.

## Fix

1. **Remove the `greet()` function** entirely (the `#[tauri::command]` attribute
   and the function body).

2. **Remove `greet` from the `invoke_handler!` macro** in `pub fn run()`. The
   line currently reads:
   ```rust
   .invoke_handler(tauri::generate_handler![
       greet,
       engine_version,
       ...
   ])
   ```
   Remove only the `greet,` entry. All other entries must remain unchanged.

3. **Verify** that the remaining code compiles: `cd src-tauri && cargo check`.

4. **Search the frontend** (`src/` directory) for any reference to `"greet"` or
   `invoke("greet"` — there should be none. Report if you find any.

## Rules

- Do NOT run `git commit` or `git push`.
- Do NOT change any other function or logic.
- Do NOT modify any Python or TypeScript code unless step 4 reveals a caller.
