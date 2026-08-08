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
    Abschnitt "force"). Duck-typed auf region.page/x/y/w/h, um keine
    Modulabhängigkeit auf pdf_extractor.Region einzugehen."""
    if not regions:
        return image
    page_regions = [r for r in regions if r.page == page_num]
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
) -> Tuple[List[str], bool]:
    """Extrahiert pro Seite nativen Text, falls vorhanden, sonst via OCR.

    Erkennt automatisch, ob eine Seite einen nativen Textlayer besitzt
    (TC-O-002: gemischtes PDF mit nativen und gescannten Seiten).

    regions wirkt auf beiden Zweigen: auf Seiten mit nativem Text
    block-basiert (wie pdf_extractor.extract_pages), auf tatsächlich per
    OCR gelesenen Seiten durch Maskieren vor dem Rastern-Ergebnis (siehe
    _mask_regions_on_image). warnings bleibt hier ungenutzt (beide Zweige
    unterstützen exclude_regions vollständig) - der Parameter existiert nur
    zur einheitlichen Signatur mit extract_pages_for_profile.

    Rückgabe: (Seitentexte, ocr_used) - ocr_used ist True, sobald
    mindestens eine Seite über Tesseract statt nativer Extraktion gelesen
    wurde, damit Aufrufer (z.B. der Report) das sichtbar machen können.
    """
    pages_text: List[str] = []
    ocr_used = False
    doc = fitz.open(pdf_path)
    try:
        for page_index, page in enumerate(doc):
            page_num = page_index + 1
            native_text = page.get_text().strip()
            if native_text:
                if regions and any(r.page == page_num for r in regions):
                    from engine.pdf_extractor import filter_blocks_by_regions, get_text_blocks, join_block_text
                    blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
                    pages_text.append(join_block_text(blocks))
                else:
                    pages_text.append(native_text)
            else:
                pages_text.append(_ocr_page(page, lang=lang, dpi=dpi, page_num=page_num, regions=regions))
                ocr_used = True
    finally:
        doc.close()
    return pages_text, ocr_used
