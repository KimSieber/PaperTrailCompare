"""P1-Testfall TC-O-001 für engine.ocr_extractor.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 5.
Fixture: tests/fixtures/TC-O-001/{ref,cnd}.pdf – echte Bitmap-Seiten
(gerendert via Pillow, in PDF eingebettet), ohne nativen Textlayer, siehe
tests/generate_fixtures.py::generate_tc_o_001.

Setzt eine lokale Tesseract-Installation voraus (siehe README.md,
Abschnitt "Tesseract OCR"); ist sie nicht vorhanden, wird der Test
übersprungen statt fehlzuschlagen.
"""
import shutil
from pathlib import Path

import pytest

from engine.ocr_extractor import extract_text_via_ocr
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
