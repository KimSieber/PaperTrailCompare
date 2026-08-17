# file:    tests/test_ocr_extractor.py
# purpose: Tests TC-O-001 and TC-O-002 for engine.ocr_extractor. Covers
#          full-page OCR, mixed-PDF fallback mode, and exclude-region masking
#          on rasterized images.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

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
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from engine.ocr_extractor import (
    _mask_regions_on_image,
    extract_pages_with_ocr_fallback,
    extract_text_via_ocr,
)
from engine.profile_loader import CompareRegion
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class _FakeRegion:
    """Duck-typed Ersatz für pdf_extractor.Region (page/x/y/w/h) - vermeidet
    eine Testabhängigkeit auf pdf_extractor, _mask_regions_on_image liest
    ohnehin nur diese Attribute."""

    page: int
    x: float
    y: float
    w: float
    h: float


def test_mask_regions_on_image_faerbt_region_weiss_bei_passender_seite():
    """Keine Tesseract-Abhängigkeit nötig: prüft direkt, dass
    _mask_regions_on_image die Pixel innerhalb der Region auf der
    richtigen Seite weiß färbt, VOR dem eigentlichen OCR-Lauf - das ist
    der Mechanismus, der exclude_regions unter ocr.mode='force' wirken
    lässt (siehe pdf_extractor.extract_pages_for_profile)."""
    image = Image.new("RGB", (100, 100), color="black")
    region = _FakeRegion(page=1, x=0, y=0, w=50, h=50)  # PDF-Punktkoordinaten bei dpi=72

    masked = _mask_regions_on_image(image, page_num=1, regions=[region], dpi=72)

    assert masked.getpixel((10, 10)) == (255, 255, 255)  # innerhalb der Region
    assert masked.getpixel((90, 90)) == (0, 0, 0)  # außerhalb bleibt unverändert


def test_mask_regions_on_image_wirkt_nur_auf_die_definierte_seite():
    image = Image.new("RGB", (100, 100), color="black")
    region = _FakeRegion(page=2, x=0, y=0, w=50, h=50)

    masked = _mask_regions_on_image(image, page_num=1, regions=[region], dpi=72)

    assert masked.getpixel((10, 10)) == (0, 0, 0)  # Region gilt nicht für Seite 1


_requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract-Binary nicht installiert (siehe README.md 'Tesseract OCR')",
)


@_requires_tesseract
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


@_requires_tesseract
def test_tc_o_002_gemischtes_pdf_nativer_und_gescannter_text():
    ref_pages, ref_ocr_used, _ = extract_pages_with_ocr_fallback(str(FIXTURES / "TC-O-002" / "ref.pdf"))
    cnd_pages, cnd_ocr_used, _ = extract_pages_with_ocr_fallback(str(FIXTURES / "TC-O-002" / "cnd.pdf"))

    assert len(ref_pages) == 2
    # Seite 1: nativer Text, direkt extrahiert (kein OCR nötig).
    assert "AB-2026-00099" in ref_pages[0]
    assert "Mustermann" in ref_pages[0]
    # Seite 2: keine nativen Zeichen, Inhalt kommt aus OCR.
    assert "Lieferdatum" in ref_pages[1]
    assert "25.07.2026" in ref_pages[1]
    # Mindestens eine Seite (Seite 2) wurde tatsächlich per OCR gelesen.
    assert ref_ocr_used is True
    assert cnd_ocr_used is True

    result = compare(ref_pages, cnd_pages, ocr_used=ref_ocr_used or cnd_ocr_used)
    assert result.has_delta is False
    assert result.deltas == []
    assert result.ocr_was_used is True


def test_extract_pages_with_ocr_fallback_compare_regions_auf_nativer_seite(tmp_path):
    """compare_regions muss im nativen Zweig von extract_pages_with_ocr_fallback
    wirken (Sprint PTC-S3 Task C, siehe docs/prompt_table_regions.md) - das
    ist der tatsächliche Ausführungspfad für ocr.mode='fallback'-Profile.
    Kein Tesseract nötig, da die Seite nativen Text hat (OCR-Zweig wird
    nicht betreten)."""
    pdf_path = tmp_path / "footer.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(30, 700, "Fliesstext im Hauptteil der Seite, unveraendert.")
    c.drawString(30, 70, "ACME Insurance Company")
    c.showPage()
    c.save()

    compare_regions = [CompareRegion(condition="ACME Insurance", page=1, x=0, y=700, width=300, height=100)]

    pages, ocr_used, compare_region_texts = extract_pages_with_ocr_fallback(
        str(pdf_path), compare_regions=compare_regions
    )

    assert ocr_used is False
    assert "ACME" not in pages[0]
    assert "Fliesstext" in pages[0]
    assert compare_region_texts == [{0: ("ACMEInsuranceCompany", "ACME Insurance Company")}]


# --- Spacewidth-Kalibrierung im Fallback-Pfad (siehe docs/prompt_spacewidth_ocr_fallback.md) ---


def test_extract_pages_with_ocr_fallback_nutzt_spacewidth_kalibrierte_extraktion(tmp_path, monkeypatch):
    """Der native-Text-Zweig von extract_pages_with_ocr_fallback muss
    get_text_blocks_reconstructed() (mit calibrate_spacewidths()-Ergebnis)
    nutzen statt der unkalibrierten get_text_blocks() - sonst liefert dieser
    Pfad bei Type3-Schriften falsche Leerzeichen zwischen Silbenfragmenten
    (z.B. 'SV Spa r ka ssen V er si ch eru n g' statt 'SV
    SparkassenVersicherung'), was auch compare_regions-condition-Matches
    fehlschlagen lässt. Kein Tesseract nötig, da die Seite nativen Text hat
    (OCR-Zweig wird nicht betreten)."""
    pdf_path = tmp_path / "native.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 720, "Normaler Fliesstext mit echten Leerzeichen.")
    c.showPage()
    c.save()

    import engine.ocr_extractor as ocr_extractor_module

    real_calibrate = ocr_extractor_module.calibrate_spacewidths
    real_reconstructed = ocr_extractor_module.get_text_blocks_reconstructed
    calibrate_calls = []
    reconstructed_calls = []

    def spy_calibrate(doc):
        calibrate_calls.append(doc)
        return real_calibrate(doc)

    def spy_reconstructed(page, calibration):
        reconstructed_calls.append(calibration)
        return real_reconstructed(page, calibration)

    monkeypatch.setattr(ocr_extractor_module, "calibrate_spacewidths", spy_calibrate)
    monkeypatch.setattr(ocr_extractor_module, "get_text_blocks_reconstructed", spy_reconstructed)

    pages, ocr_used, _ = extract_pages_with_ocr_fallback(str(pdf_path))

    assert len(calibrate_calls) == 1  # einmal pro Dokument, nicht pro Seite
    assert len(reconstructed_calls) == 1  # einmal für die eine native-Text-Seite
    assert ocr_used is False
    assert "Fliesstext" in pages[0]


def test_extract_pages_with_ocr_fallback_stimmt_mit_direkter_rekonstruktion_ueberein():
    """Für dieselbe Seite muss der Fallback-Pfad denselben Text liefern wie
    die direkte Nutzung von calibrate_spacewidths() +
    get_text_blocks_reconstructed() (siehe pdf_extractor._extract_page_text_columns_reconstructed)
    - beide nutzen jetzt dieselbe Kalibrierung/Rekonstruktion. TC-T-009/cnd.pdf
    hat echte Leerzeichen-Glyphen (source='real_spaces', siehe
    test_calibrate_spacewidths_nutzt_echte_leerzeichen_wenn_vorhanden) und
    genau eine Seite mit nativem Text - kein Tesseract nötig."""
    import pymupdf

    from engine.pdf_extractor import calibrate_spacewidths, get_text_blocks_reconstructed, join_block_text

    pdf_path = str(FIXTURES / "TC-T-009" / "cnd.pdf")

    pages, ocr_used, _ = extract_pages_with_ocr_fallback(pdf_path)

    doc = pymupdf.open(pdf_path)
    try:
        calibration = calibrate_spacewidths(doc)
        expected = join_block_text(get_text_blocks_reconstructed(doc[0], calibration))
    finally:
        doc.close()

    assert ocr_used is False
    assert pages[0] == expected


def test_extract_text_via_ocr_raises_on_nonexistent_file():
    with pytest.raises(FileNotFoundError, match="nicht gefunden"):
        extract_text_via_ocr("/does/not/exist.pdf")
