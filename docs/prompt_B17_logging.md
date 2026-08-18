# Claude Code Prompt: B17 — Replace print() with Python logging

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.

Sprint PTC-S5 (Housekeeping). Code-Review Rule 15 finding: ad-hoc `print()` to
stderr without log levels or timestamps.

**Do NOT run `git commit` or `git push`** — Kim commits manually after verification.

---

## Problem

Several files use `print(..., file=sys.stderr)` for warnings and errors instead
of Python's `logging` module. This means no log levels, no timestamps, and no
uniform format across the application.

**Critical constraint:** stdout is exclusively reserved for structured JSON IPC
with the Tauri shell. The logging framework must NEVER write to stdout. All log
output goes to stderr.

---

## Fix

### Step 1 — Investigate current state

Before making changes, search the entire `engine/` and `packaging/` directories
for all `print(..., file=sys.stderr)` and ad-hoc `print(f"[` calls. List every
occurrence with file, line number, and the current message. Report the list before
proceeding.

### Step 2 — Configure logging

Create a minimal logging setup. The configuration goes into a new file
`engine/log_config.py`:

```python
"""Zentrale Logging-Konfiguration für die PaperTrail-Engine.

Alle Log-Ausgaben gehen auf stderr — stdout ist exklusiv für die
JSON-IPC mit dem Tauri-Sidecar reserviert und darf nicht beschrieben
werden."""

import logging
import sys


def configure_logging(level: int = logging.WARNING) -> None:
    """Konfiguriert das Root-Logging mit einheitlichem Format auf stderr.

    Wird einmal beim Engine-Start aufgerufen (engine/__main__.py, main()).
    Wiederholte Aufrufe sind harmlos (handler-Duplikate werden vermieden)."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(handler)
    root.setLevel(level)
```

### Step 3 — Call configure_logging at engine entry points

Add `configure_logging()` call at the top of `main()` in `engine/__main__.py`,
BEFORE any other logic. This is the single entry point for both CLI and Sidecar
execution.

### Step 4 — Replace all print-to-stderr with logging calls

In each file that currently uses `print(..., file=sys.stderr)`:

1. Add `import logging` and create a module-level logger:
   ```python
   logger = logging.getLogger(__name__)
   ```

2. Replace each `print()` call with the appropriate log level:
   - `print(str(exc), file=sys.stderr)` → `logger.error("%s", exc)`
   - `print(f"Warnung: {warning}", file=sys.stderr)` → `logger.warning("%s", warning)`
   - `print(f"Warnung ({ref_path} / {cnd_path}): {warning}", ...)` →
     `logger.warning("%s / %s: %s", ref_path, cnd_path, warning)`

**Known locations** (verify in Step 1 — there may be more or fewer):
- `engine/__main__.py` — multiple error/warning prints
- `engine/batch_processor.py` — warning prints

### Step 5 — Convert build_sidecar.py

In `packaging/build_sidecar.py`, replace the ad-hoc `print(f"[build_sidecar] ...")`
pattern with proper logging. Since this is a standalone build script (not launched
via `engine/__main__.py`), it needs its own `configure_logging()` call at the top
of its `main()` or `if __name__ == "__main__"` block. Use log level `INFO` for
this script (build scripts should show progress by default).

Replace:
- `print(f"[build_sidecar] ...")` → `logger.info("...")`

### Step 6 — Verify

1. Run `PYTHONPATH=. python -m pytest -q` — all tests must pass.
2. Run `PYTHONPATH=. python -m engine compare --help` — must work without errors.
3. Grep for remaining `print(` calls in `engine/` and `packaging/`. The ONLY
   remaining `print()` calls should be those writing to **stdout** (JSON output,
   human-readable summary, `--version`). List any remaining stderr prints.

---

## Rules

- Do NOT run `git commit` or `git push`.
- Do NOT change any business logic or test behavior.
- Do NOT add logging to stdout — stderr only.
- Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.
- Docstrings for new functions (`configure_logging`) in German.
- Keep the format string style consistent: use `%s` placeholders in logging
  calls (not f-strings) — this is Python logging best practice (lazy
  interpolation).
