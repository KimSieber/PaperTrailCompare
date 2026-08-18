# file:    engine/batch_processor.py
# purpose: Batch comparison of PDF document pairs from a CSV file list,
#          XMP-based pairing, or page-group-based splitting of large PDFs.
#          Generates per-pair reports and aggregated batch results.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-17

"""Massenvergleich von Dokumentenpaaren: per Dateiliste (CSV) oder per
XMP-Metadaten (Document-ID).

Die Extraktion→Vergleich→Merge→Sortierung-Pipeline liegt seit
docs/prompt_B11_B12_shared_comparison.md in engine.comparison.run_comparison()
(gemeinsam mit engine.__main__._run_compare) - hier verbleiben nur
Batch-spezifische Aspekte: Dateiexistenz, Fehlerbehandlung pro Paar (B11:
eine defekte PDF darf den restlichen Batch nicht abbrechen),
Report-Erzeugung und Aggregation; daher Integrationstests statt
Unit-Tests (siehe CLAUDE.md).
"""
from __future__ import annotations

import csv
import logging
import re
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

import pymupdf

from engine.comparison import run_comparison
from engine.models import BatchResult, PairResult
from engine.page_group_detector import extract_page_groups
from engine.profile_loader import Profile
from engine.report_generator import generate_report

logger = logging.getLogger(__name__)

_XMP_IDENTIFIER_RE = re.compile(r"<dc:identifier>(.*?)</dc:identifier>")
_FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]")


def read_filelist(filelist_path: Union[str, Path]) -> List[Tuple[str, str]]:
    """Liest eine CSV-Dateiliste ohne Kopfzeile: jede Zeile ist
    'Referenzdatei,Kandidatendatei'."""
    with open(filelist_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return [(row[0], row[1]) for row in reader if row]


def _sanitize_filename_part(name: str) -> str:
    """Ersetzt alle Zeichen, die nicht auf jedem Zielbetriebssystem in
    Dateinamen zulässig sind, durch Unterstriche - spiegelt
    src-tauri/src/lib.rs::sanitize_filename_part, damit Einzel-Reports aus
    Einzelvergleich und Batch demselben Namensschema folgen."""
    return _FILENAME_SANITIZE_RE.sub("_", name)


def _unique_report_path(report_dir: Path, ref_file: Path, cnd_file: Path) -> Path:
    """Bildet den Ziel-Dateinamen für den Einzel-Report eines Batch-Paares
    ({RefStem}_{CndStem}.pdf, siehe prompt_batch_fixes.md Punkt 1). Existiert
    dieser Name bereits (Normalfall: nicht der Fall), wird ein Zähler
    angehängt, damit kein bestehender Report überschrieben wird."""
    base = f"PTC-Vergleich_{_sanitize_filename_part(ref_file.stem)}_{_sanitize_filename_part(cnd_file.stem)}"
    candidate = report_dir / f"{base}.pdf"
    counter = 2
    while candidate.exists():
        candidate = report_dir / f"{base}_{counter}.pdf"
        counter += 1
    return candidate


def _compare_pair(
    ref_path: str,
    cnd_path: str,
    profile: Optional[Profile],
    report_dir: Optional[Union[str, Path]] = None,
) -> PairResult:
    """Vergleicht ein einzelnes Dateipaar für den Batch: prüft, ob beide Dateien
    existieren, ruft run_comparison() auf und erzeugt bei gesetztem report_dir
    zusätzlich einen Einzel-Report (_unique_report_path). Fehlt eine Datei
    oder schlägt der Vergleich fehl, wird dies als PairResult(status="error")
    zurückgegeben statt eine Exception zu werfen - eine defekte PDF darf den
    restlichen Batch nicht abbrechen (siehe Kommentar unten, B11)."""
    ref_file = Path(ref_path)
    cnd_file = Path(cnd_path)

    missing = [str(p) for p in (ref_file, cnd_file) if not p.is_file()]
    if missing:
        return PairResult(
            ref_path=ref_path,
            cnd_path=cnd_path,
            status="error",
            error=f"Datei(en) nicht gefunden: {', '.join(missing)}",
        )

    # B11: try/except so a corrupt PDF doesn't crash the entire batch (Code
    # Review Finding B11, Rule 11 - Fehlerbehandlung) - der Pfad wird als
    # PairResult(status="error") zurückgemeldet statt die Exception
    # unbehandelt bis zum Pool/Batch-Aufrufer durchschlagen zu lassen.
    try:
        output = run_comparison(str(ref_file), str(cnd_file), profile)
    except Exception as exc:  # noqa: BLE001 - fehlerhaftes Paar darf den Batch nicht abbrechen
        return PairResult(
            ref_path=ref_path,
            cnd_path=cnd_path,
            status="error",
            error=str(exc),
        )

    for warning in output.region_warnings:
        logger.warning("%s / %s: %s", ref_path, cnd_path, warning)

    if report_dir is not None:
        report_path = _unique_report_path(Path(report_dir), ref_file, cnd_file)
        generate_report(
            output.result, ref_file, cnd_file, report_path,
            profile=profile, region_warnings=output.region_warnings,
            duration_seconds=output.duration_seconds,
        )

    return PairResult(
        ref_path=ref_path, cnd_path=cnd_path, status="ok",
        compare_result=output.result, total_pages=output.total_pages,
    )


def _compare_pair_worker(
    args: Tuple[str, str, Optional[Profile], Optional[Union[str, Path]]]
) -> PairResult:
    """Modul-Top-Level-Wrapper für multiprocessing.Pool.map – Pool benötigt
    eine picklebare, importierbare Funktion (keine Closure/Lambda)."""
    ref_path, cnd_path, profile, report_dir = args
    return _compare_pair(ref_path, cnd_path, profile, report_dir)


def batch_compare(
    filelist_path: Union[str, Path],
    profile: Optional[Profile] = None,
    workers: int = 1,
    on_progress: Optional[Callable[[int, int, PairResult], None]] = None,
    report_dir: Optional[Union[str, Path]] = None,
) -> BatchResult:
    """Vergleicht alle Dateipaare aus einer CSV-Dateiliste.

    Fehlende Dateien werden pro Paar protokolliert (status='error'); die
    übrigen Paare werden trotzdem weiterverarbeitet (TC-B-002).

    workers>1 verarbeitet die Paare parallel über multiprocessing.Pool
    (TC-B-005) – siehe Architekturspezifikation: "Python multiprocessing /
    parallele Verarbeitung ohne externen Queue-Server". Die Ergebnisreihenfolge
    entspricht dabei stets der Reihenfolge in der Dateiliste (Pool.imap
    erhält die Eingabereihenfolge).

    on_progress(index, total, pair_result) wird nach jedem verarbeiteten Paar
    aufgerufen (index ab 1) – Grundlage für Live-Progress-Events Richtung GUI
    per Tauri-Command. Bei workers>1 entspricht die Aufrufreihenfolge des
    Callbacks weiterhin der Dateilisten-Reihenfolge (Pool.imap statt
    Pool.map), nicht notwendigerweise der tatsächlichen Fertigstellungs-
    reihenfolge der Worker-Prozesse.

    report_dir erzeugt zusätzlich pro erfolgreich verglichenem Paar einen
    Einzel-Report (analog zum Einzelvergleich, siehe report_generator.
    generate_report) flach in diesem Verzeichnis - auch bei 0 Deltas.
    Paare mit status="error" erzeugen keinen Einzel-Report (siehe
    prompt_batch_fixes.md Punkt 1).
    """
    pairs = read_filelist(filelist_path)
    total = len(pairs)

    if workers > 1:
        with Pool(processes=workers) as pool:
            results_iter = pool.imap(
                _compare_pair_worker,
                [(ref, cnd, profile, report_dir) for ref, cnd in pairs],
            )
            results = []
            for index, pair_result in enumerate(results_iter, start=1):
                results.append(pair_result)
                if on_progress is not None:
                    on_progress(index, total, pair_result)
    else:
        results = []
        for index, (ref, cnd) in enumerate(pairs, start=1):
            pair_result = _compare_pair(ref, cnd, profile, report_dir)
            results.append(pair_result)
            if on_progress is not None:
                on_progress(index, total, pair_result)

    return BatchResult(pairs=results)


def split_batch_pdf(
    pdf_path: Union[str, Path],
    profile: Profile,
    output_dir: Union[str, Path],
    group_filter: Optional[Sequence[str]] = None,
) -> List[Path]:
    """Zerlegt ein großes Batch-PDF in Einzeldokumente anhand der
    Seitengruppen-Patterns aus dem Profil (TC-B-004).

    Nutzt page_group_detector.extract_page_groups, um die Seitenbereiche
    der einzelnen Dokumente zu bestimmen, und schreibt jeden Bereich als
    eigenständiges PDF in output_dir.
    """
    groups = extract_page_groups(
        str(pdf_path), profile.page_groups, group_filter=group_filter
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_paths: List[Path] = []
    src_doc = pymupdf.open(str(pdf_path))
    try:
        for index, group in enumerate(groups, start=1):
            first_page_index = group.start_page - 1
            last_page_index = first_page_index + len(group.pages) - 1

            single_doc = pymupdf.open()
            try:
                single_doc.insert_pdf(src_doc, from_page=first_page_index, to_page=last_page_index)

                out_path = output_dir / f"{index:03d}_{group.name}.pdf"
                single_doc.save(str(out_path))
            finally:
                single_doc.close()
            output_paths.append(out_path)
    finally:
        src_doc.close()

    return output_paths


def _read_document_id(pdf_path: Path) -> Optional[str]:
    """Liest die Document-ID aus dem echten XMP-Metadatenpaket des PDFs
    (dc:identifier), via PyMuPDF (doc.get_xml_metadata) – siehe CLAUDE.md
    Tech-Stack: 'XMP-Metadaten: python-xmp-toolkit / PyMuPDF'. PyMuPDF
    liest/schreibt XMP direkt, ohne zusätzliche Systemabhängigkeit
    (python-xmp-toolkit würde die C-Bibliothek 'exempi' voraussetzen)."""
    doc = pymupdf.open(str(pdf_path))
    try:
        xmp_packet = doc.get_xml_metadata() or ""
    finally:
        doc.close()
    match = _XMP_IDENTIFIER_RE.search(xmp_packet)
    return match.group(1) if match else None


def batch_compare_by_xmp(
    ref_dir: Union[str, Path],
    cnd_dir: Union[str, Path],
    profile: Optional[Profile] = None,
    ref_glob: str = "*.pdf",
    cnd_glob: str = "*.pdf",
) -> BatchResult:
    """Ordnet PDFs aus zwei Verzeichnissen anhand ihrer Document-ID zu und
    vergleicht die zugeordneten Paare (TC-B-003).

    ref_dir/cnd_dir dürfen auf dasselbe Verzeichnis zeigen; ref_glob/
    cnd_glob erlauben dann, ref- und cnd-Dateien anhand des Dateinamens
    auseinanderzuhalten (z.B. 'ref_*.pdf' / 'cnd_*.pdf').
    """
    ref_by_id = {}
    for path in sorted(Path(ref_dir).glob(ref_glob)):
        doc_id = _read_document_id(path)
        if doc_id is not None:
            ref_by_id[doc_id] = path

    cnd_by_id = {}
    for path in sorted(Path(cnd_dir).glob(cnd_glob)):
        doc_id = _read_document_id(path)
        if doc_id is not None:
            cnd_by_id[doc_id] = path

    common_ids = sorted(set(ref_by_id) & set(cnd_by_id))
    results = [
        _compare_pair(str(ref_by_id[doc_id]), str(cnd_by_id[doc_id]), profile)
        for doc_id in common_ids
    ]
    return BatchResult(pairs=results)
