"""OCR-Texterkennung für gescannte bzw. als Grafik hinterlegte PDF-Seiten.

Rasterisiert jede Seite via PyMuPDF und erkennt den Text via Tesseract 5
(pytesseract). Sprachmodell laut Architekturentscheidung #3 ausschließlich
Deutsch ('deu').
"""
from __future__ import annotations

import io
from typing import List

import fitz
import pytesseract
from PIL import Image

_DEFAULT_DPI = 300
_DEFAULT_LANG = "deu"


def extract_text_via_ocr(
    pdf_path: str, lang: str = _DEFAULT_LANG, dpi: int = _DEFAULT_DPI
) -> List[str]:
    """Extrahiert den Text jeder Seite eines PDFs via OCR.

    Unabhängig davon, ob eine Seite einen nativen Textlayer besitzt – jede
    Seite wird gerastert und per Bilderkennung gelesen. Für PDFs mit
    nativem Text ist engine.pdf_extractor.extract_pages vorzuziehen
    (schneller, keine Erkennungsfehler).
    """
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            pages_text.append(_ocr_page(page, lang=lang, dpi=dpi))
    finally:
        doc.close()
    return pages_text


def _ocr_page(page: "fitz.Page", lang: str = _DEFAULT_LANG, dpi: int = _DEFAULT_DPI) -> str:
    pixmap = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    return pytesseract.image_to_string(image, lang=lang).strip()


def extract_pages_with_ocr_fallback(
    pdf_path: str, lang: str = _DEFAULT_LANG, dpi: int = _DEFAULT_DPI
) -> List[str]:
    """Extrahiert pro Seite nativen Text, falls vorhanden, sonst via OCR.

    Erkennt automatisch, ob eine Seite einen nativen Textlayer besitzt
    (TC-O-002: gemischtes PDF mit nativen und gescannten Seiten).
    """
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            native_text = page.get_text().strip()
            if native_text:
                pages_text.append(native_text)
            else:
                pages_text.append(_ocr_page(page, lang=lang, dpi=dpi))
    finally:
        doc.close()
    return pages_text
