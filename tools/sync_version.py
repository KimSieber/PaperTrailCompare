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
    print(f"  [ok] {init_py.relative_to(project_root)}")

    # 2. package.json — "version": "X.Y.Z"
    package_json = project_root / "package.json"
    _replace_in_file(
        package_json,
        r'"version"\s*:\s*"[^"]*"',
        f'"version": "{version}"',
    )
    print(f"  [ok] {package_json.relative_to(project_root)}")

    # 3. src-tauri/tauri.conf.json — "version": "X.Y.Z"
    tauri_conf = project_root / "src-tauri" / "tauri.conf.json"
    _replace_in_file(
        tauri_conf,
        r'"version"\s*:\s*"[^"]*"',
        f'"version": "{version}"',
    )
    print(f"  [ok] {tauri_conf.relative_to(project_root)}")

    # 4. src-tauri/Cargo.toml — version = "X.Y.Z"
    #    Nur im [package]-Abschnitt, nicht bei Dependency-Versionen.
    #    Das Muster matcht "version = " am Zeilenanfang (nach optionalem
    #    Whitespace), was in TOML nur im [package]-Block vorkommt.
    cargo_toml = project_root / "src-tauri" / "Cargo.toml"
    _replace_in_file(
        cargo_toml,
        r'^(version\s*=\s*)"[^"]*"',
        rf'\g<1>"{version}"',
        flags=re.MULTILINE,
    )
    print(f"  [ok] {cargo_toml.relative_to(project_root)}")

    print()
    print(f"Fertig — alle 4 Dateien auf version={version}, expiry={expiry} gesetzt.")


if __name__ == "__main__":
    main()
