"""CLI-Einstiegspunkt der Python Core Engine.

Wird von der Tauri-Shell als Sidecar-Prozess gestartet (lokales IPC über
stdin/stdout/Prozessargumente, kein Netzwerk-Socket – siehe CLAUDE.md
Architekturentscheidung #1). Für die Auslieferung wird dieses Modul via
PyInstaller zu einer eigenständigen Executable gebündelt
(Architekturentscheidung #2).

Aktuell nur als Grundgerüst: `--version` bestätigt, dass der Sidecar-
Prozess startet und antwortet. Weitere Befehle (Einzelvergleich,
Batch-Verarbeitung, Report-Erzeugung) werden hier ergänzt, sobald die
Tauri-Commands dafür angebunden werden.
"""
from __future__ import annotations

import argparse
import sys

__version__ = "0.1.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="papertrail-engine")
    parser.add_argument(
        "--version", action="store_true", help="Version der Engine ausgeben und beenden"
    )
    args = parser.parse_args(argv)

    if args.version:
        print(f"papertrail-engine {__version__}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
