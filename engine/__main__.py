# file:    engine/__main__.py
# purpose: CLI entry point for the Python Core Engine sidecar process.
#          Provides the "compare" and "batch" subcommands invoked by the
#          Tauri shell via local IPC (no network socket).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-17

"""CLI-Einstiegspunkt der Python Core Engine.

Wird von der Tauri-Shell als Sidecar-Prozess gestartet (lokales IPC über
stdin/stdout/Prozessargumente, kein Netzwerk-Socket – siehe CLAUDE.md
Architekturentscheidung #1). Für die Auslieferung wird dieses Modul via
PyInstaller zu einer eigenständigen Executable gebündelt
(Architekturentscheidung #2).

`--version` gibt als JSON-Zeile `{"version", "expiry", "expired"}` aus
(Version aus engine.__version__, Ablaufdatum aus engine.__expiry__) und
bestätigt damit zugleich, dass der Sidecar-Prozess startet und antwortet;
die Tauri-Shell (engine_version-Command) nutzt das für den Startup- und
About-Dialog-Check. `--version` ist von der Ablaufprüfung ausgenommen und
liefert `expired: true` statt abzubrechen - sonst könnte die GUI den
Ablauf einer abgelaufenen Testversion gar nicht erst feststellen. Die
Subcommands (`compare`, `batch`) prüfen __expiry__ dagegen vor jeder
Ausführung und brechen mit Exit-Code 2 sowie einer deutschsprachigen
Fehlermeldung auf stderr ab, wenn die Testversion abgelaufen ist
(Exit-Code 1 bleibt für sonstige Laufzeitfehler reserviert).
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

# Felder von text_comparator.Delta, die rein Python-intern sind (nur vom
# report_generator konsumiert, siehe docs/prompt_region_clip_highlighting.md)
# und daher NIE in der Tauri-IPC-JSON-Ausgabe erscheinen dürfen -
# dataclasses.asdict() serialisiert alle Felder inkl. None-Werten, filtert
# also nicht von selbst.
_DELTA_INTERNAL_FIELDS = ("region_clip",)


def _strip_internal_delta_fields(deltas: list) -> None:
    """Entfernt _DELTA_INTERNAL_FIELDS in-place aus jedem Delta-Dict einer
    (von dataclasses.asdict erzeugten) Delta-Liste."""
    for delta_dict in deltas:
        for field_name in _DELTA_INTERNAL_FIELDS:
            delta_dict.pop(field_name, None)
from typing import Optional

from datetime import date, datetime
from pathlib import Path

from engine import __expiry__, __version__
from engine.batch_processor import batch_compare
from engine.comparison import run_comparison
from engine.models import PairResult
from engine.profile_loader import Profile, ValidationError, load_profile
from engine.report_generator import generate_batch_report, generate_report


def _run_compare(args: argparse.Namespace) -> int:
    profile: Optional[Profile] = None
    if args.profile:
        try:
            profile = load_profile(args.profile)
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    try:
        output = run_comparison(args.ref_pdf, args.cnd_pdf, profile)
    except Exception as exc:  # noqa: BLE001 - Fehler geht 1:1 an den Sidecar-Aufrufer
        print(str(exc), file=sys.stderr)
        return 1

    for warning in output.region_warnings:
        print(f"Warnung: {warning}", file=sys.stderr)

    result = output.result
    region_warnings = output.region_warnings
    duration_seconds = output.duration_seconds

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
        _strip_internal_delta_fields(payload["deltas"])
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


def _run_batch(args: argparse.Namespace) -> int:
    """Streamt pro verarbeitetem Paar sofort eine JSON-Zeile auf stdout
    (statt erst am Ende die gesamte Ausgabe zu puffern) - die Tauri-Shell
    liest den Sidecar-Prozess dafür zeilenweise (spawn statt output()) und
    emittiert je Zeile ein Tauri-Event Richtung Frontend (Live-Progress,
    siehe prompt_batch_verarbeitung.md). Die abschließende 'done'-Zeile
    trägt den Pfad des Batch-Report-PDFs (report_generator.generate_batch_report).

    Pro erfolgreich verglichenem Paar entsteht zusätzlich ein Einzel-Report
    flach in --output-dir (batch_compare(report_dir=...), siehe
    prompt_batch_fixes.md Punkt 1) - vorher lagen dort nur der Batch-Report.
    """
    profile: Optional[Profile] = None
    if args.profile:
        try:
            profile = load_profile(args.profile)
        except ValidationError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    def on_progress(index: int, total: int, pair_result: PairResult) -> None:
        pair_payload = dataclasses.asdict(pair_result)
        compare_result_payload = pair_payload.get("compare_result")
        if compare_result_payload is not None:
            _strip_internal_delta_fields(compare_result_payload["deltas"])
        print(json.dumps({
            "type": "progress",
            "index": index,
            "total": total,
            "pair": pair_payload,
        }), flush=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    start = time.perf_counter()
    try:
        result = batch_compare(
            args.filelist, profile=profile, on_progress=on_progress, report_dir=output_dir,
        )
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    duration_seconds = time.perf_counter() - start

    timestamp = start_time.strftime("%Y-%m-%d_%H-%M")
    report_path = output_dir / f"PTC-Batch-Report_{timestamp}.pdf"
    generate_batch_report(
        result, report_path, profile=profile, profile_path=args.profile,
        duration_seconds=duration_seconds, start_time=start_time,
    )

    print(json.dumps({
        "type": "done",
        "ok_count": result.ok_count,
        "error_count": result.error_count,
        "report_path": str(report_path),
    }), flush=True)

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

    batch_parser = subparsers.add_parser(
        "batch", help="Alle Dateipaare einer CSV-Dateiliste vergleichen"
    )
    batch_parser.add_argument("filelist", help="Pfad zur CSV-Dateiliste (ohne Kopfzeile: ref,cnd pro Zeile)")
    batch_parser.add_argument(
        "--output-dir", required=True, help="Verzeichnis für den Batch-Report (PTC-Batch-Report_<Zeitstempel>.pdf)"
    )
    batch_parser.add_argument(
        "--profile",
        default=None,
        help="Pfad zu einem JSON-Vergleichsprofil (siehe 'compare --profile')",
    )
    batch_parser.set_defaults(func=_run_batch)

    args = parser.parse_args(argv)

    if args.version:
        expired = date.today() > date.fromisoformat(__expiry__)
        print(json.dumps({
            "version": __version__,
            "expiry": __expiry__,
            "expired": expired,
        }))
        return 0

    if date.today() > date.fromisoformat(__expiry__):
        print(f"Diese Testversion ist am {__expiry__} abgelaufen. "
              f"Bitte wenden Sie sich an PaperTrail@Sieber-BW.de "
              f"für eine aktuelle Version.", file=sys.stderr)
        return 2

    if args.command in ("compare", "batch"):
        return args.func(args)

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - nur beim Sidecar-Start, nicht beim Import
    sys.exit(main())
