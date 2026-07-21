"""CLI-Einstiegspunkt der Python Core Engine.

Wird von der Tauri-Shell als Sidecar-Prozess gestartet (lokales IPC über
stdin/stdout/Prozessargumente, kein Netzwerk-Socket – siehe CLAUDE.md
Architekturentscheidung #1). Für die Auslieferung wird dieses Modul via
PyInstaller zu einer eigenständigen Executable gebündelt
(Architekturentscheidung #2).

`--version` bestätigt, dass der Sidecar-Prozess startet und antwortet.
`compare <ref.pdf> <cnd.pdf> [--json] [--report <output.pdf>]` führt den
Einzelvergleich aus (pdf_extractor + text_comparator) und gibt bei `--json`
exakt die Felder von text_comparator.CompareResult/Delta als JSON aus.
`--report` erzeugt zusätzlich einen PDF-Report mit rot markierten
Delta-Stellen (report_generator.generate_report, TC-R-001); der Pfad
erscheint bei `--json` als zusätzliches Feld `report_path`. Weitere Befehle
(Batch-Verarbeitung) werden hier ergänzt, sobald die Tauri-Commands dafür
angebunden werden.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from engine.pdf_extractor import extract_pages
from engine.report_generator import generate_report
from engine.text_comparator import compare

__version__ = "0.1.0"


def _run_compare(args: argparse.Namespace) -> int:
    try:
        ref_pages = extract_pages(args.ref_pdf)
        cnd_pages = extract_pages(args.cnd_pdf)
    except Exception as exc:  # noqa: BLE001 - Fehler geht 1:1 an den Sidecar-Aufrufer
        print(str(exc), file=sys.stderr)
        return 1

    result = compare(ref_pages, cnd_pages)

    report_path = None
    if args.report:
        try:
            generate_report(result, args.ref_pdf, args.cnd_pdf, args.report)
        except Exception as exc:  # noqa: BLE001 - Fehler geht 1:1 an den Sidecar-Aufrufer
            print(str(exc), file=sys.stderr)
            return 1
        report_path = args.report

    if args.json:
        payload = dataclasses.asdict(result)
        if report_path is not None:
            payload["report_path"] = report_path
        print(json.dumps(payload))
    else:
        summary = (
            f"{len(result.deltas)} Delta(s) gefunden."
            if result.has_delta
            else "Kein Delta gefunden."
        )
        if report_path is not None:
            summary += f" Report: {report_path}"
        print(summary)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="papertrail-engine")
    parser.add_argument(
        "--version", action="store_true", help="Version der Engine ausgeben und beenden"
    )
    subparsers = parser.add_subparsers(dest="command")

    compare_parser = subparsers.add_parser(
        "compare", help="Zwei PDF-Dateien textlich vergleichen"
    )
    compare_parser.add_argument("ref_pdf", help="Pfad zur Referenz-PDF")
    compare_parser.add_argument("cnd_pdf", help="Pfad zur Kandidat-PDF")
    compare_parser.add_argument(
        "--json", action="store_true", help="Ergebnis als JSON auf stdout ausgeben"
    )
    compare_parser.add_argument(
        "--report",
        default=None,
        help="Pfad für PDF-Report mit rot markierten Deltas (TC-R-001)",
    )
    compare_parser.set_defaults(func=_run_compare)

    args = parser.parse_args(argv)

    if args.version:
        print(f"papertrail-engine {__version__}")
        return 0

    if args.command == "compare":
        return args.func(args)

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - nur beim Sidecar-Start, nicht beim Import
    sys.exit(main())
