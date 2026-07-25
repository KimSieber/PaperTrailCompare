"""Massenvergleich von Dokumentenpaaren: per Dateiliste (CSV) oder per
XMP-Metadaten (Document-ID).

Kombiniert die Schicht-1/2-Bausteine pdf_extractor (Textextraktion),
text_comparator (Diff) und profile_loader (Konfiguration) zu einem
Batch-Ablauf; daher Integrationstests statt Unit-Tests (siehe CLAUDE.md).
"""
from __future__ import annotations

import csv
import re
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import fitz

from engine.models import BatchResult, PairResult
from engine.page_group_detector import extract_page_groups
from engine.pdf_extractor import extract_pages_for_profile
from engine.profile_loader import Profile
from engine.text_comparator import compare

_XMP_IDENTIFIER_RE = re.compile(r"<dc:identifier>(.*?)</dc:identifier>")


def read_filelist(filelist_path: Union[str, Path]) -> List[Tuple[str, str]]:
    """Liest eine CSV-Dateiliste mit Spalten 'ref' und 'cnd'."""
    with open(filelist_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [(row["ref"], row["cnd"]) for row in reader]


def _compare_pair(ref_path: str, cnd_path: str, profile: Optional[Profile]) -> PairResult:
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

    case_sensitive = profile.case_sensitive if profile is not None else True
    normalize_whitespace = profile.normalize_whitespace if profile is not None else False
    compare_mode = profile.compare_mode if profile is not None else "words"
    region_warnings: List[str] = []
    ref_pages, ref_ocr_used = extract_pages_for_profile(
        str(ref_file), profile, role="reference", warnings=region_warnings
    )
    cnd_pages, cnd_ocr_used = extract_pages_for_profile(
        str(cnd_file), profile, role="candidate", warnings=region_warnings
    )
    for warning in region_warnings:
        print(f"Warnung ({ref_path} / {cnd_path}): {warning}", file=sys.stderr)
    result = compare(
        ref_pages, cnd_pages,
        case_sensitive=case_sensitive,
        normalize_whitespace=normalize_whitespace,
        ocr_used=ref_ocr_used or cnd_ocr_used,
        compare_mode=compare_mode,
    )

    return PairResult(ref_path=ref_path, cnd_path=cnd_path, status="ok", compare_result=result)


def _compare_pair_worker(args: Tuple[str, str, Optional[Profile]]) -> PairResult:
    """Modul-Top-Level-Wrapper für multiprocessing.Pool.map – Pool benötigt
    eine picklebare, importierbare Funktion (keine Closure/Lambda)."""
    ref_path, cnd_path, profile = args
    return _compare_pair(ref_path, cnd_path, profile)


def batch_compare(
    filelist_path: Union[str, Path],
    profile: Optional[Profile] = None,
    workers: int = 1,
) -> BatchResult:
    """Vergleicht alle Dateipaare aus einer CSV-Dateiliste.

    Fehlende Dateien werden pro Paar protokolliert (status='error'); die
    übrigen Paare werden trotzdem weiterverarbeitet (TC-B-002).

    workers>1 verarbeitet die Paare parallel über multiprocessing.Pool
    (TC-B-005) – siehe Architekturspezifikation: "Python multiprocessing /
    parallele Verarbeitung ohne externen Queue-Server". Die Ergebnisreihenfolge
    entspricht dabei stets der Reihenfolge in der Dateiliste (Pool.map
    erhält die Eingabereihenfolge).
    """
    pairs = read_filelist(filelist_path)

    if workers > 1:
        with Pool(processes=workers) as pool:
            results = pool.map(
                _compare_pair_worker, [(ref, cnd, profile) for ref, cnd in pairs]
            )
    else:
        results = [_compare_pair(ref, cnd, profile) for ref, cnd in pairs]

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
    src_doc = fitz.open(str(pdf_path))
    try:
        for index, group in enumerate(groups, start=1):
            first_page_index = group.start_page - 1
            last_page_index = first_page_index + len(group.pages) - 1

            single_doc = fitz.open()
            single_doc.insert_pdf(src_doc, from_page=first_page_index, to_page=last_page_index)

            out_path = output_dir / f"{index:03d}_{group.name}.pdf"
            single_doc.save(str(out_path))
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
    doc = fitz.open(str(pdf_path))
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
