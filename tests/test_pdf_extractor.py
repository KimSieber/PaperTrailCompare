"""Testfälle für engine.pdf_extractor.

TC-X-001/002: eigene P1-Basistests für native Textextraktion – die
Testspezifikation definiert dafür keine eigenen Testfall-IDs.

TC-T-007/008: laut Testspezifikation unter "Modul: text_comparator"
gelistet, betreffen inhaltlich aber die PDF-Extraktion (Mehrspaltigkeit,
Tabellenerkennung) und werden daher hier statt in test_text_comparator.py
umgesetzt, siehe CLAUDE.md Modulübersicht (pdf_extractor: "Mehrspaltigkeit,
Tabellen").

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 2.
"""
import shutil
from pathlib import Path

import pytest

from engine.pdf_extractor import extract_pages, extract_pages_for_profile
from engine.profile_loader import OcrConfig, Profile
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"


def test_tc_x_001_nativen_text_aus_einseitigem_pdf_extrahieren():
    pages = extract_pages(str(FIXTURES / "TC-X-001" / "doc.pdf"))

    assert len(pages) == 1
    assert "einfacher, einseitiger Testtext" in pages[0]


def test_tc_x_002_text_aus_mehrseitigem_pdf_seitenweise_extrahieren():
    pages = extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))

    assert len(pages) == 3
    assert "Seite eins" in pages[0]
    assert "Seite zwei" in pages[1]
    assert "Seite drei" in pages[2]


def test_tc_t_007_mehrspaltiger_text_korrekte_lesereihenfolge():
    ref_pages = extract_pages(str(FIXTURES / "TC-T-007" / "ref.pdf"))
    cnd_pages = extract_pages(str(FIXTURES / "TC-T-007" / "cnd.pdf"))

    assert len(ref_pages) == 1
    page_text = ref_pages[0]

    # Spalte 1 muss vollständig vor Spalte 2 erscheinen (kein Mischtext).
    pos_a = page_text.index("Abschnitt A")
    pos_a4 = page_text.index("A 4: Fazit")
    pos_b = page_text.index("Abschnitt B")
    assert pos_a < pos_a4 < pos_b

    result = compare(ref_pages, cnd_pages)
    assert result.has_delta is False
    assert result.deltas == []


def test_extract_pages_for_profile_ohne_profil_wie_extract_pages():
    pages, ocr_used = extract_pages_for_profile(str(FIXTURES / "TC-X-002" / "doc.pdf"), None)

    assert pages == extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))
    assert ocr_used is False


def test_extract_pages_for_profile_ocr_deaktiviert_wie_extract_pages():
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=False))
    pages, ocr_used = extract_pages_for_profile(str(FIXTURES / "TC-X-002" / "doc.pdf"), profile)

    assert pages == extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))
    assert ocr_used is False


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract-Binary nicht installiert (siehe README.md 'Tesseract OCR')",
)
def test_extract_pages_for_profile_ocr_aktiviert_nutzt_fallback():
    """Bei profile.ocr.enabled=True muss extract_pages_for_profile die
    gescannte Seite (kein nativer Textlayer) via OCR-Fallback lesen,
    statt leeren Text zu liefern (siehe TC-O-002-Fixture)."""
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=True))
    pages, ocr_used = extract_pages_for_profile(str(FIXTURES / "TC-O-002" / "ref.pdf"), profile)

    assert len(pages) == 2
    assert "AB-2026-00099" in pages[0]
    assert "Lieferdatum" in pages[1]  # nur via OCR lesbar (Seite ohne Textlayer)
    assert ocr_used is True


def test_tc_t_008_tabellenerkennung_kein_falsches_delta():
    ref_pages = extract_pages(str(FIXTURES / "TC-T-008" / "ref.pdf"))
    cnd_pages = extract_pages(str(FIXTURES / "TC-T-008" / "cnd.pdf"))

    assert "Artikel Alpha" in ref_pages[0]
    assert "907,97 EUR" in ref_pages[0]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []
