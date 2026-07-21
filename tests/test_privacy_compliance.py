"""Automatisierte Datenschutz-/Compliance-Testfälle TC-S-001 und TC-S-002.

TC-S-003 (Standalone-Betrieb ohne Serverinstallation) ist laut
Testspezifikation ein manueller Systemtest auf frischer Maschine und wird
daher nicht hier, sondern in docs/manual-tests.md als Checkliste
dokumentiert.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 9.
Fixtures: tests/fixtures/TC-S-001/, tests/fixtures/TC-S-002/
(tests/generate_fixtures.py::generate_tc_s_001_002).
"""
import os
import socket
import tempfile
from pathlib import Path

from engine.pdf_extractor import extract_pages
from engine.report_generator import generate_report
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"


def test_tc_s_001_keine_netzwerkverbindung_waehrend_verarbeitung(monkeypatch, tmp_path):
    """Blockiert socket.socket/socket.create_connection während eines
    vollständigen Vergleichslaufs (Extraktion, Diff, Report-Erzeugung) –
    jeder Versuch, eine Netzwerkverbindung zu öffnen, lässt den Test
    sofort fehlschlagen."""

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "Netzwerkzugriff während der Verarbeitung ist nicht erlaubt (TC-S-001)"
        )

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    ref_path = FIXTURES / "TC-S-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-S-001" / "cnd.pdf"

    ref_pages = extract_pages(str(ref_path))
    cnd_pages = extract_pages(str(cnd_path))
    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False

    # Auch die Report-Erzeugung (PyMuPDF + ReportLab) darf keine
    # Netzwerkverbindung benötigen.
    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path)
    assert output_path.is_file()


def test_tc_s_002_temporaere_dateien_werden_bereinigt(monkeypatch):
    """Vergleicht den Inhalt eines isolierten Temp-Verzeichnisses vor und
    nach einem vollständigen Vergleichslauf – es dürfen keine neuen
    Dateien zurückbleiben.

    Stand heute nutzt kein Engine-Modul tempfile/das Systemverzeichnis für
    temporäre Dateien (pdf_extractor/ocr_extractor/report_generator halten
    alle Zwischendaten im Arbeitsspeicher, z.B. via io.BytesIO). Dieser
    Test ist daher aktuell trivial grün, dient aber als Regressionsschutz,
    falls künftig doch Temp-Dateien eingeführt werden.
    """
    isolated_tmp_dir = tempfile.mkdtemp(prefix="papertrail_tc_s_002_")
    monkeypatch.setattr(tempfile, "tempdir", isolated_tmp_dir)

    before = set(os.listdir(isolated_tmp_dir))

    ref_path = FIXTURES / "TC-S-002" / "ref.pdf"
    cnd_path = FIXTURES / "TC-S-002" / "cnd.pdf"

    ref_pages = extract_pages(str(ref_path))
    cnd_pages = extract_pages(str(cnd_path))
    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False

    after = set(os.listdir(isolated_tmp_dir))
    leftover = after - before
    assert leftover == set(), f"Temporäre Dateien nicht bereinigt: {leftover}"
