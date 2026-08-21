# Sprint PTC-S6 — Central VERSION File + Sync Script

## Overview

Create a central `VERSION` file as the single source of truth for the
app version and expiry date, plus a sync script that stamps these
values into the four config files that require them as literals.

**Why a script?** Cargo (`Cargo.toml`), npm (`package.json`), Tauri
(`tauri.conf.json`), and Python (`engine/__init__.py`) each require
the version as a literal value in their own config format. None of
these tools supports includes or references to external files. The
sync script bridges this gap — the developer only ever edits `VERSION`,
then runs the script once to propagate.

**Execution order:** Step 1 → 2 → Verification.

Do NOT run `git commit` or `git push` — Kim commits manually after
verification.

---

## Step 1 — Create `VERSION` file

Create the file `VERSION` in the project root with the following
content:

```
# =============================================================================
# PaperTrail Compare — Zentrale Versions- und Ablaufdatei
# =============================================================================
#
# Diese Datei ist die EINZIGE Stelle, an der Version und Ablaufdatum
# gepflegt werden. Beide Werte werden von tools/sync_version.py in die
# vier Konfigurationsdateien übertragen, die sie als Literale benötigen:
#
#   1. engine/__init__.py        — __version__ und __expiry__
#   2. package.json              — "version"
#   3. src-tauri/tauri.conf.json — "version"
#   4. src-tauri/Cargo.toml      — version
#
# Workflow:
#   1. Werte hier ändern
#   2. python tools/sync_version.py ausführen
#   3. Ergebnis prüfen (npm run tauri dev)
#   4. Committen
#
# NIEMALS die Version oder das Ablaufdatum direkt in einer der vier
# Zieldateien ändern — beim nächsten Sync-Lauf wird der Wert
# überschrieben.
# =============================================================================

version=0.2.1
expiry=2026-10-31
```

**Pause — wait for confirmation before continuing.**

---

## Step 2 — Create `tools/sync_version.py`

Create the file `tools/sync_version.py`. The `tools/` directory should
already exist; if not, create it.

The script must:

1. Read `VERSION` from the project root (relative to the script's own
   location: `script_dir / ".." / "VERSION"`).
2. Parse `version=` and `expiry=` values (ignore comments and blank
   lines).
3. Write both values into the four target files using targeted
   text replacement (not full file rewrites where avoidable).
4. Print a summary of what was written where.

```python
#!/usr/bin/env python3
# file:    tools/sync_version.py
# purpose: Reads version and expiry from the central VERSION file and
#          stamps both values into the four config files that require
#          them as literals. See VERSION file header for details.
# author:  Kim Sieber
# created: 2026-08-21
# changed: 2026-08-21

"""Synchronisiert Version und Ablaufdatum aus der zentralen VERSION-Datei
in die vier Konfigurationsdateien des Projekts.

Aufruf aus dem Projektverzeichnis:
    python tools/sync_version.py

Die vier Zieldateien und ihre jeweiligen Ersetzungsmuster:

1. engine/__init__.py
   - __version__ = "X.Y.Z"
   - __expiry__  = "YYYY-MM-DD"

2. package.json
   - "version": "X.Y.Z"  (erstes Vorkommen)

3. src-tauri/tauri.conf.json
   - "version": "X.Y.Z"  (erstes Vorkommen)

4. src-tauri/Cargo.toml
   - version = "X.Y.Z"   (erstes Vorkommen im [package]-Abschnitt)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _read_version_file(path: Path) -> dict[str, str]:
    """Liest die VERSION-Datei und gibt ein Dict mit den Schlüssel-Wert-
    Paaren zurück. Ignoriert Leerzeilen und Kommentarzeilen (#)."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        values[key.strip()] = val.strip()
    return values


def _replace_in_file(path: Path, pattern: str, replacement: str) -> None:
    """Ersetzt das erste Vorkommen von `pattern` (Regex) in der Datei
    durch `replacement`. Bricht ab, wenn kein Treffer gefunden wird."""
    content = path.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, count=1)
    if count == 0:
        print(f"  WARNUNG: Muster nicht gefunden in {path}: {pattern}")
        sys.exit(1)
    path.write_text(new_content, encoding="utf-8")


def main() -> None:
    """Hauptfunktion: VERSION lesen, vier Dateien aktualisieren."""
    project_root = Path(__file__).resolve().parent.parent
    version_file = project_root / "VERSION"

    if not version_file.exists():
        print(f"FEHLER: {version_file} nicht gefunden.")
        sys.exit(1)

    values = _read_version_file(version_file)

    version = values.get("version")
    expiry = values.get("expiry")

    if not version:
        print("FEHLER: 'version' nicht in VERSION-Datei gefunden.")
        sys.exit(1)
    if not expiry:
        print("FEHLER: 'expiry' nicht in VERSION-Datei gefunden.")
        sys.exit(1)

    print(f"VERSION-Datei gelesen: version={version}, expiry={expiry}")
    print()

    # 1. engine/__init__.py — __version__ und __expiry__
    init_py = project_root / "engine" / "__init__.py"
    _replace_in_file(
        init_py,
        r'__version__\s*=\s*"[^"]*"',
        f'__version__ = "{version}"',
    )
    _replace_in_file(
        init_py,
        r'__expiry__\s*=\s*"[^"]*"',
        f'__expiry__ = "{expiry}"',
    )
    print(f"  ✓ {init_py.relative_to(project_root)}")

    # 2. package.json — "version": "X.Y.Z"
    package_json = project_root / "package.json"
    _replace_in_file(
        package_json,
        r'"version"\s*:\s*"[^"]*"',
        f'"version": "{version}"',
    )
    print(f"  ✓ {package_json.relative_to(project_root)}")

    # 3. src-tauri/tauri.conf.json — "version": "X.Y.Z"
    tauri_conf = project_root / "src-tauri" / "tauri.conf.json"
    _replace_in_file(
        tauri_conf,
        r'"version"\s*:\s*"[^"]*"',
        f'"version": "{version}"',
    )
    print(f"  ✓ {tauri_conf.relative_to(project_root)}")

    # 4. src-tauri/Cargo.toml — version = "X.Y.Z"
    #    Nur im [package]-Abschnitt, nicht bei Dependency-Versionen.
    #    Das Muster matcht "version = " am Zeilenanfang (nach optionalem
    #    Whitespace), was in TOML nur im [package]-Block vorkommt.
    cargo_toml = project_root / "src-tauri" / "Cargo.toml"
    _replace_in_file(
        cargo_toml,
        r'^(version\s*=\s*)"[^"]*"',
        rf'\g<1>"{version}"',
    )
    print(f"  ✓ {cargo_toml.relative_to(project_root)}")

    print()
    print(f"Fertig — alle 4 Dateien auf version={version}, expiry={expiry} gesetzt.")


if __name__ == "__main__":
    main()
```

**Important:** The regex for `Cargo.toml` uses `re.MULTILINE` flag.
Update the `_replace_in_file` function to accept an optional `flags`
parameter, or change the `Cargo.toml` call to use `re.MULTILINE`:

Replace the `_replace_in_file` function with:

```python
def _replace_in_file(
    path: Path, pattern: str, replacement: str, flags: int = 0
) -> None:
    """Ersetzt das erste Vorkommen von `pattern` (Regex) in der Datei
    durch `replacement`. Bricht ab, wenn kein Treffer gefunden wird."""
    content = path.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, count=1, flags=flags)
    if count == 0:
        print(f"  WARNUNG: Muster nicht gefunden in {path}: {pattern}")
        sys.exit(1)
    path.write_text(new_content, encoding="utf-8")
```

And update the Cargo.toml call to pass `re.MULTILINE`:

```python
_replace_in_file(
    cargo_toml,
    r'^(version\s*=\s*)"[^"]*"',
    rf'\g<1>"{version}"',
    flags=re.MULTILINE,
)
```

### Verification (Step 2)

1. Run `python tools/sync_version.py` — should print 4 checkmarks.
2. Verify all four files contain `0.2.1` and `2026-10-31` (where
   applicable).
3. Change `VERSION` to `version=0.2.2` temporarily, run script again,
   verify all four files updated. Revert back to `0.2.1`.
4. Run `pytest` from project root with `PYTHONPATH=.` — all tests
   green.
5. Run `npm run tauri dev` — version shows `0.2.1` in sidebar and
   About dialog.

---

## Files created

| File | Purpose |
|------|---------|
| `VERSION` | Single source of truth for version + expiry |
| `tools/sync_version.py` | Stamps values into 4 config files |

## Files modified (by the script, not manually)

| File | Fields updated |
|------|---------------|
| `engine/__init__.py` | `__version__`, `__expiry__` |
| `package.json` | `"version"` |
| `src-tauri/tauri.conf.json` | `"version"` |
| `src-tauri/Cargo.toml` | `version` |

## Constraints

- Do NOT run `git commit` or `git push`.
- Do NOT modify the four target files manually — only via the script.
- The script must work on both macOS and Windows (use `pathlib`, not
  hardcoded separators).
