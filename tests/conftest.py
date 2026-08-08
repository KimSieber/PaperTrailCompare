# file:    tests/conftest.py
# purpose: Shared pytest fixtures: FIXTURES path resolution, vendored
#          Tesseract language data setup, and local_filelist helper for
#          platform-independent CSV file list generation.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Gemeinsame Test-Hilfsmittel für tests/.

FIXTURES löst relativ zum Speicherort dieser Datei auf, nicht relativ zum
Arbeitsverzeichnis, aus dem pytest aufgerufen wird - Voraussetzung dafür,
dass die Testsuite unabhängig vom Aufrufverzeichnis läuft (siehe
Portabilitäts-Review, H1).
"""
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
_VENDORED_TESSDATA = Path(__file__).parent.parent / "vendor" / "tessdata"


@pytest.fixture(scope="session", autouse=True)
def vendored_tessdata_prefix():
    """Zeigt Tesseract für die gesamte Testsession auf das vendorte
    deu.traineddata statt auf ein zufällig vorhandenes System-Sprachpaket -
    die Tests dürfen auf jeder Maschine mit Tesseract-Binary laufen,
    unabhängig davon, welche Sprachen dort installiert sind (z.B.
    Windows-CI: Chocolatey liefert die Binary, aber kein deu-Sprachmodell).

    TESSDATA_PREFIX zeigt hier bewusst auf den tessdata-Ordner selbst,
    nicht dessen Elternverzeichnis - konsistent mit
    engine.ocr_extractor._configure_bundled_tesseract, das für Tesseract 5
    denselben Ordner setzt."""
    previous = os.environ.get("TESSDATA_PREFIX")
    os.environ["TESSDATA_PREFIX"] = str(_VENDORED_TESSDATA)
    yield
    if previous is None:
        os.environ.pop("TESSDATA_PREFIX", None)
    else:
        os.environ["TESSDATA_PREFIX"] = previous


@pytest.fixture
def local_filelist(tmp_path):
    """Erzeugt filelist.csv frisch für den aktuellen Checkout, statt eine
    eingecheckte CSV mit fest einprogrammierten Pfaden vom
    Erzeugungs-Rechner zu verwenden. Eine committete CSV mit absoluten
    Pfaden bricht auf jeder anderen Maschine bzw. jedem anderen
    Betriebssystem - siehe Windows-CI-Fund: ein PairResult enthielt einen
    macOS-Pfad des Entwicklers (/Users/kim/…), der auf dem Windows-Runner
    naturgemäß nicht existiert.

    Die referenzierten PDFs unter tests/fixtures/<tc>/pairs/ sind echte,
    orts- und plattformunabhängige Binärdateien und bleiben unverändert;
    nur die Pfadliste, die auf sie zeigt, wird pro Testlauf lokal neu
    geschrieben (Namensschema deckungsgleich mit
    tests/generate_fixtures.py::generate_tc_b_001_003/generate_tc_b_005)."""

    def _make(tc: str, count: int, digits: int = 2) -> Path:
        pairs_dir = FIXTURES / tc / "pairs"
        rows = [
            f"{pairs_dir / f'doc_{i:0{digits}d}_ref.pdf'},{pairs_dir / f'doc_{i:0{digits}d}_cnd.pdf'}"
            for i in range(1, count + 1)
        ]
        filelist_path = tmp_path / "filelist.csv"
        filelist_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return filelist_path

    return _make
