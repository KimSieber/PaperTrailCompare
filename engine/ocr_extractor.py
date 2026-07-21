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
            pixmap = page.get_pixmap(dpi=dpi)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            pages_text.append(pytesseract.image_to_string(image, lang=lang).strip())
    finally:
        doc.close()
    return pages_text
