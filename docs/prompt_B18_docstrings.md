# Claude Code Prompt: B18 — Add Missing Docstrings

## Context

PaperTrail Compare is a local desktop application (Tauri + React/TS + Python engine)
for content-level PDF comparison during print system migrations.

Sprint PTC-S5 (Housekeeping). Code-Review Rule 6 finding: ~25 helper functions
lack docstrings. Some may have been added in later sprints — the exact count must
be verified.

**Do NOT run `git commit` or `git push`** — Kim commits manually after verification.

---

## Fix

### Step 1 — Scan and list all functions without docstrings

Search ALL Python files in `engine/`, `tests/`, `tools/`, and `packaging/` for
functions and methods (`def ...`) that have NO docstring (no `"""..."""` as the
first statement in the function body).

**Exclude from the list:**
- Test functions (`def test_...`) — these are self-documenting by name and
  assertion.
- Functions that already have a docstring (even a short one).
- `__init__`, `__repr__`, `__eq__` and similar dunder methods on simple
  dataclasses where purpose is obvious.

**Report the complete list** with file path, line number, and function name.
Do NOT add docstrings yet — wait for confirmation.

### Step 2 — Add docstrings (after confirmation)

For each function in the confirmed list, add a German docstring following
the existing project style:

- **Language:** German (all documentation in the project is German).
- **Format:** PEP 257 — triple-quoted string as the first statement.
- **Minimum:** One sentence stating the purpose of the function.
- **Where applicable:** Document parameters (with type/unit/value range),
  return value, raised exceptions, and important side effects.
- **Style reference:** Follow the existing docstrings in the project (e.g.,
  `_region_applies_to_page`, `filter_blocks_by_regions`, `_reconstruct_line_text`
  in `pdf_extractor.py`). These are concise but informative, often explaining
  WHY the function exists, not just WHAT it does.

**Do NOT:**
- Change any function signatures or logic.
- Add docstrings to test functions.
- Rewrite existing docstrings (even if they could be improved).
- Add JSDoc to TypeScript files (out of scope for this task).

### Step 3 — Verify

Run `PYTHONPATH=. python -m pytest -q` — all tests must pass (docstrings are
documentation-only changes, but verify nothing was accidentally modified).

Report the total number of docstrings added.

---

## Rules

- Do NOT run `git commit` or `git push`.
- Do NOT change any logic, signatures, or test behavior.
- Do NOT modify Rust (`src-tauri/`) or TypeScript (`src/`) code.
- Docstrings in German, following PEP 257 and existing project style.
