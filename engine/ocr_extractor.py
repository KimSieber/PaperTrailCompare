# file:    engine/ocr_extractor.py
# purpose: OCR text extraction via Tesseract (pytesseract). Supports full-
#          page OCR, fallback mode (OCR only for pages without native text),
#          and exclude-region masking on rasterized page images.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""OCR-Texterkennung für gescannte bzw. als Grafik hinterlegte PDF-Seiten.

Rasterisiert jede Seite via PyMuPDF und erkennt den Text via Tesseract 5
(pytesseract). Sprachmodell laut Architekturentscheidung #3 ausschließlich
Deutsch ('deu').
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import fitz
import pytesseract
from PIL import Image, ImageDraw

from engine.pdf_extractor import (
    _region_applies_to_page,
    calibrate_spacewidths,
    get_text_blocks_reconstructed,
)

_DEFAULT_DPI = 300
_DEFAULT_LANG = "deu"


def _configure_bundled_tesseract() -> None:
    """Zeigt pytesseract im PyInstaller-gebündelten Zustand (sys.frozen) auf
    die mitgelieferte Tesseract-Binary/tessdata statt auf die PATH-Suche
    von pytesseract - siehe packaging/papertrail-engine.spec, das Binary
    und deu.traineddata unter <MEIPASS>/tesseract/ ablegt (Layout siehe
    packaging/build_sidecar.py:_stage_tesseract). Ohne das würde die
    Datei zwar mitgebündelt, pytesseract fände sie zur Laufzeit aber
    trotzdem nicht (Standardverhalten: 'tesseract' über PATH suchen -
    auf einer frischen Kundenmaschine ohne separate Tesseract-Installation
    schlägt das fehl).

    Im Dev-Betrieb (sys.frozen nicht gesetzt) bleibt das
    Standardverhalten unverändert - dort ist Tesseract separat installiert
    (siehe README.md, Abschnitt 'Tesseract OCR')."""
    if not getattr(sys, "frozen", False):
        return
    bundle_root = Path(getattr(sys, "_MEIPASS", ""))
    binary_name = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    pytesseract.pytesseract.tesseract_cmd = str(bundle_root / "tesseract" / "bin" / binary_name)
    os.environ["TESSDATA_PREFIX"] = str(bundle_root / "tesseract" / "tessdata")


_configure_bundled_tesseract()


def _mask_regions_on_image(
    image: "Image.Image", page_num: int, regions: Optional[Sequence], dpi: int
) -> "Image.Image":
    """Malt exclude_regions (PyMuPDF-Punktkoordinaten) als weiße Fläche auf
    das bereits gerasterte Seitenbild, VOR dem Tesseract-Lauf - dadurch
    wirkt der Ausschluss auch dort, wo es (anders als bei nativer
    Extraktion) keine Textblockstruktur gibt, auf die ein nachträglicher
    Filter aufbauen könnte (siehe pdf_extractor.extract_pages_for_profile,
    Abschnitt "force"). Nutzt pdf_extractor._region_applies_to_page fürs
    page=0/page_from-Wildcard-Matching (Modulabhängigkeit auf pdf_extractor
    besteht ohnehin bereits an anderer Stelle in dieser Datei, siehe
    extract_pages_with_ocr_fallback); erwartet Regionen mit region.x/y/w/h
    (siehe pdf_extractor.Region) - r.page/r.page_from reichen für
    _region_applies_to_page, Test-Doubles ohne .page_from funktionieren,
    solange .page gesetzt ist (siehe tests/test_ocr_extractor.py
    _FakeRegion)."""
    if not regions:
        return image
    page_regions = [r for r in regions if _region_applies_to_page(r, page_num)]
    if not page_regions:
        return image
    scale = dpi / 72
    draw = ImageDraw.Draw(image)
    for r in page_regions:
        box = (r.x * scale, r.y * scale, (r.x + r.w) * scale, (r.y + r.h) * scale)
        draw.rectangle(box, fill="white")
    return image


def extract_text_via_ocr(
    pdf_path: str,
    lang: str = _DEFAULT_LANG,
    dpi: int = _DEFAULT_DPI,
    regions: Optional[Sequence] = None,
) -> List[str]:
    """Extrahiert den Text jeder Seite eines PDFs via OCR.

    Unabhängig davon, ob eine Seite einen nativen Textlayer besitzt – jede
    Seite wird gerastert und per Bilderkennung gelesen. Für PDFs mit
    nativem Text ist engine.pdf_extractor.extract_pages vorzuziehen
    (schneller, keine Erkennungsfehler).

    regions (siehe _mask_regions_on_image) werden vor der Erkennung auf dem
    Seitenbild geweißt, damit exclude_regions auch unter OCR wirkt.
    """
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page_index, page in enumerate(doc):
            pages_text.append(_ocr_page(page, lang=lang, dpi=dpi, page_num=page_index + 1, regions=regions))
    finally:
        doc.close()
    return pages_text


def _ocr_page(
    page: "fitz.Page",
    lang: str = _DEFAULT_LANG,
    dpi: int = _DEFAULT_DPI,
    page_num: int = 1,
    regions: Optional[Sequence] = None,
) -> str:
    pixmap = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    image = _mask_regions_on_image(image, page_num, regions, dpi)
    return pytesseract.image_to_string(image, lang=lang).strip()


def extract_pages_with_ocr_fallback(
    pdf_path: str,
    lang: str = _DEFAULT_LANG,
    dpi: int = _DEFAULT_DPI,
    regions: Optional[Sequence] = None,
    warnings: Optional[List[str]] = None,
    table_regions: Optional[Sequence] = None,
) -> Tuple[List[str], bool, List[dict]]:
    """Extrahiert pro Seite nativen Text, falls vorhanden, sonst via OCR.

    Erkennt automatisch, ob eine Seite einen nativen Textlayer besitzt
    (TC-O-002: gemischtes PDF mit nativen und gescannten Seiten).

    Dies ist der tatsächliche Ausführungspfad für Profile mit
    ocr.mode="fallback" (siehe pdf_extractor.extract_pages_for_profile) -
    table_regions muss deshalb hier ausgewertet werden, nicht nur im
    "off"-Pfad (pdf_extractor.extract_pages), sonst griffe der Multiset-
    Vergleich für genau das real beobachtete Profil nie (siehe
    docs/prompt_table_regions.md, Motivation).

    regions wirkt auf beiden Zweigen: auf Seiten mit nativem Text
    block-basiert (filter_blocks_by_regions, siehe pdf_extractor.extract_pages -
    page=0/page_from-Wildcards über _region_applies_to_page), auf tatsächlich
    per OCR gelesenen Seiten durch Maskieren vor dem Rastern-Ergebnis (siehe
    _mask_regions_on_image). table_regions wirkt nur auf Seiten mit nativem
    Text (separate_table_region_blocks braucht Blockstruktur, die es unter
    OCR nicht gibt - Seiten ohne nativen Text liefern dafür ein leeres dict).
    warnings bleibt hier ungenutzt (beide Zweige unterstützen exclude_regions
    vollständig) - der Parameter existiert nur zur einheitlichen Signatur mit
    extract_pages_for_profile.

    Rückgabe: (Seitentexte, ocr_used, table_region_texte_pro_seite) -
    ocr_used ist True, sobald mindestens eine Seite über Tesseract statt
    nativer Extraktion gelesen wurde, damit Aufrufer (z.B. der Report) das
    sichtbar machen können. table_region_texte_pro_seite: eine Liste (ein
    Eintrag pro Seite) von dicts region_index -> normalisierter Text.

    Seiten mit nativem Text nutzen get_text_blocks_reconstructed() statt
    get_text_blocks() - PyMuPDFs eigene Leerzeichen-Heuristik fügt bei
    Type3-Schriften (Size=1.0, typisch für Großrechner-Drucksysteme) falsche
    Leerzeichen zwischen Silbenfragmenten ein ("SV Spa r ka ssen V er si ch
    eru n g" statt "SV SparkassenVersicherung") - siehe
    docs/prompt_spacewidth_ocr_fallback.md. Der native Pfad
    (_extract_page_text_columns) löst das bereits über
    calibrate_spacewidths()/get_text_blocks_reconstructed(); dieser Fallback-
    Pfad war der einzige native-Text-Pfad ohne diese Kalibrierung - das
    betraf auch table_regions direkt (condition-Match schlug auf dem
    unkalibrierten Text fehl). calibrate_spacewidths(doc) läuft einmal pro
    Dokument vor der Seiten-Schleife (Lesezugriff auf Font-Metriken, keine
    Seiteneffekte). BEWUSST NICHT hinzugefügt: sort_blocks_columns/
    split_wide_blocks - ein früherer Versuch, dafür _extract_page_text_columns()
    zu nutzen, verschlechterte die Ergebnisse (638->1253 Deltas), weil
    sort_blocks_columns die Lesereihenfolge der ganzen Seite veränderte.
    Diese Änderung betrifft nur die Textqualität innerhalb der Blöcke, nicht
    deren Reihenfolge.
    """
    pages_text: List[str] = []
    per_page_table_region_texts: List[dict] = []
    ocr_used = False
    doc = fitz.open(pdf_path)
    try:
        calibration = calibrate_spacewidths(doc)
        for page_index, page in enumerate(doc):
            page_num = page_index + 1
            native_text = page.get_text().strip()
            if native_text:
                from engine.pdf_extractor import (
                    filter_blocks_by_regions,
                    join_block_text,
                    separate_table_region_blocks,
                )
                if regions and any(_region_applies_to_page(r, page_num) for r in regions):
                    blocks = filter_blocks_by_regions(
                        get_text_blocks_reconstructed(page, calibration), page_num, regions
                    )
                else:
                    blocks = get_text_blocks_reconstructed(page, calibration)
                page_table_region_texts: dict = {}
                if table_regions:
                    blocks, page_table_region_texts = separate_table_region_blocks(
                        blocks, page_num, table_regions
                    )
                pages_text.append(join_block_text(blocks))
                per_page_table_region_texts.append(page_table_region_texts)
            else:
                pages_text.append(_ocr_page(page, lang=lang, dpi=dpi, page_num=page_num, regions=regions))
                per_page_table_region_texts.append({})
                ocr_used = True
    finally:
        doc.close()
    return pages_text, ocr_used, per_page_table_region_texts
