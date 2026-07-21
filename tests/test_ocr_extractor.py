"""Testfälle TC-O-001 (P1) und TC-O-002 (P2) für engine.ocr_extractor.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 5.

TC-O-001-Fixture: tests/fixtures/TC-O-001/{ref,cnd}.pdf – echte Bitmap-
Seiten (gerendert via Pillow, in PDF eingebettet), ohne nativen Textlayer.

TC-O-002-Fixture: tests/fixtures/TC-O-002/{ref,cnd}.pdf – Seite 1 mit
nativem Textlayer, Seite 2 als echte Bitmap ohne Textlayer, siehe
tests/generate_fixtures.py::generate_tc_o_001 / generate_tc_o_002.

Setzt eine lokale Tesseract-Installation voraus (siehe README.md,
Abschnitt "Tesseract OCR"); ist sie nicht vorhanden, werden die Tests
übersprungen statt fehlzuschlagen.
"""
import shutil
from pathlib import Path

import pytest

from engine.ocr_extractor import extract_pages_with_ocr_fallback, extract_text_via_ocr
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract-Binary nicht installiert (siehe README.md 'Tesseract OCR')",
)


def test_tc_o_001_gescannten_text_via_ocr_erkennen():
    ref_pages = extract_text_via_ocr(str(FIXTURES / "TC-O-001" / "ref.pdf"))
    cnd_pages = extract_text_via_ocr(str(FIXTURES / "TC-O-001" / "cnd.pdf"))

    assert len(ref_pages) == 1
    assert "Auftragsbestaetigung" in ref_pages[0]
    assert "AB-2026-00099" in ref_pages[0]
    assert "1234,56" in ref_pages[0]

    result = compare(ref_pages, cnd_pages)
    assert result.has_delta is False
    assert result.deltas == []


def test_tc_o_002_gemischtes_pdf_nativer_und_gescannter_text():
    ref_pages = extract_pages_with_ocr_fallback(str(FIXTURES / "TC-O-002" / "ref.pdf"))
    cnd_pages = extract_pages_with_ocr_fallback(str(FIXTURES / "TC-O-002" / "cnd.pdf"))

    assert len(ref_pages) == 2
    # Seite 1: nativer Text, direkt extrahiert (kein OCR nötig).
    assert "AB-2026-00099" in ref_pages[0]
    assert "Mustermann" in ref_pages[0]
    # Seite 2: keine nativen Zeichen, Inhalt kommt aus OCR.
    assert "Lieferdatum" in ref_pages[1]
    assert "25.07.2026" in ref_pages[1]

    result = compare(ref_pages, cnd_pages)
    assert result.has_delta is False
    assert result.deltas == []
