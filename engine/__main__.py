"""CLI-Einstiegspunkt der Python Core Engine.

Wird von der Tauri-Shell als Sidecar-Prozess gestartet (lokales IPC über
stdin/stdout/Prozessargumente, kein Netzwerk-Socket – siehe CLAUDE.md
Architekturentscheidung #1). Für die Auslieferung wird dieses Modul via
PyInstaller zu einer eigenständigen Executable gebündelt
(Architekturentscheidung #2).

`--version` bestätigt, dass der Sidecar-Prozess startet und antwortet.
`compare <ref.pdf> <cnd.pdf> [--json] [--report <output.pdf>] [--profile <profil.json>]`
führt den Einzelvergleich aus (pdf_extractor + text_comparator) und gibt bei
`--json` exakt die Felder von text_comparator.CompareResult/Delta als JSON
aus. `--profile` lädt ein JSON-Vergleichsprofil (profile_loader.load_profile)
und übernimmt daraus case_sensitive, normalize_whitespace sowie
ocr.mode_reference/ocr.mode_candidate ("off"/"fallback"/"force", getrennt
für Referenz und Kandidat einstellbar) und ocr.dpi über
pdf_extractor.extract_pages_for_profile(role="reference"/"candidate"); ohne
`--profile` gilt das bisherige Verhalten (case_sensitive=True, kein
Whitespace-Toleranz-Filter, kein OCR). `--report` erzeugt
zusätzlich einen PDF-Report mit rot markierten Delta-Stellen
(report_generator.generate_report, TC-R-001); der Pfad erscheint bei
`--json` als zusätzliches Feld `report_path`. Weitere Befehle
(Batch-Verarbeitung) werden hier ergänzt, sobald die Tauri-Commands dafür
angebunden werden.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from typing import Optional

from engine.pdf_extractor import extract_pages_for_profile
from engine.profile_loader import Profile, ValidationError, load_profile
from engine.report_generator import generate_report
from engine.text_comparator import compare

__version__ = "0.1.0"


def _run_compare(args: argparse.Namespace) -> int:
    profile: Optional[Profile] = None
    if args.profile:
        try:
            profile = load_profile(args.profile)
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    region_warnings: list[str] = []
    start = time.perf_counter()
    try:
        ref_pages, ref_ocr_used = extract_pages_for_profile(
            args.ref_pdf, profile, role="reference", warnings=region_warnings
        )
        cnd_pages, cnd_ocr_used = extract_pages_for_profile(
            args.cnd_pdf, profile, role="candidate", warnings=region_warnings
        )
    except Exception as exc:  # noqa: BLE001 - Fehler geht 1:1 an den Sidecar-Aufrufer
        print(str(exc), file=sys.stderr)
        return 1

    for warning in region_warnings:
        print(f"Warnung: {warning}", file=sys.stderr)

    result = compare(
        ref_pages, cnd_pages,
        case_sensitive=profile.case_sensitive if profile else True,
        normalize_whitespace=profile.normalize_whitespace if profile else False,
        ocr_used=ref_ocr_used or cnd_ocr_used,
        compare_mode=profile.compare_mode if profile else "words",
    )
    duration_seconds = time.perf_counter() - start

    report_path = None
    if args.report:
        try:
            generate_report(
                result, args.ref_pdf, args.cnd_pdf, args.report,
                profile=profile, profile_path=args.profile,
                duration_seconds=duration_seconds,
                region_warnings=region_warnings,
            )
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
    compare_parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Pfad zu einem JSON-Vergleichsprofil (case_sensitive, "
            "normalize_whitespace, ocr.enabled werden daraus übernommen)"
        ),
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
