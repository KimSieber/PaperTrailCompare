"""Massenvergleich von Dokumentenpaaren: per Dateiliste (CSV) oder per
XMP-Metadaten (Document-ID).

Kombiniert die Schicht-1/2-Bausteine pdf_extractor (Textextraktion),
text_comparator (Diff) und profile_loader (Konfiguration) zu einem
Batch-Ablauf; daher Integrationstests statt Unit-Tests (siehe CLAUDE.md).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

import fitz

from engine.pdf_extractor import extract_pages
from engine.profile_loader import Profile
from engine.text_comparator import CompareResult, compare

_XMP_IDENTIFIER_RE = re.compile(r"<dc:identifier>(.*?)</dc:identifier>")


@dataclass
class PairResult:
    ref_path: str
    cnd_path: str
    status: str  # "ok" oder "error"
    compare_result: Optional[CompareResult] = None
    error: Optional[str] = None


@dataclass
class BatchResult:
    pairs: List[PairResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for p in self.pairs if p.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for p in self.pairs if p.status == "error")


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
    ref_pages = extract_pages(str(ref_file))
    cnd_pages = extract_pages(str(cnd_file))
    result = compare(ref_pages, cnd_pages, case_sensitive=case_sensitive)

    return PairResult(ref_path=ref_path, cnd_path=cnd_path, status="ok", compare_result=result)


def batch_compare(
    filelist_path: Union[str, Path], profile: Optional[Profile] = None
) -> BatchResult:
    """Vergleicht alle Dateipaare aus einer CSV-Dateiliste.

    Fehlende Dateien werden pro Paar protokolliert (status='error'); die
    übrigen Paare werden trotzdem weiterverarbeitet (TC-B-002).
    """
    pairs = read_filelist(filelist_path)
    results = [_compare_pair(ref, cnd, profile) for ref, cnd in pairs]
    return BatchResult(pairs=results)


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
