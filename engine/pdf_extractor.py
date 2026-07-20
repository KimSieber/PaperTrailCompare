"""PDF-Textextraktion: liefert pro Seite einen normalisierten Text-String,
passend als Eingabe für engine.text_comparator.compare().

Nutzt PyMuPDF (fitz) als primäre Extraktions-Engine (Koordinaten, Spalten)
und pdfplumber ergänzend für Tabellenerkennung, siehe
doc/PaperTrailCompare_Architekturspezifikation.docx Abschnitt 4/6.2.
"""
from __future__ import annotations

from typing import List

import fitz
import pdfplumber

_TEXT_BLOCK_TYPE = 0
_COLUMN_BUCKET_PT = 50  # Blockbreite-Toleranz zur Spaltenerkennung


def _extract_page_text_columns(page: "fitz.Page") -> str:
    """Liest Textblöcke einer Seite spaltenweise (links vor rechts), statt
    strikt zeilenweise – nötig für mehrspaltige Layouts (TC-T-007)."""
    blocks = [
        b for b in page.get_text("blocks")
        if b[6] == _TEXT_BLOCK_TYPE and b[4].strip()
    ]
    blocks.sort(key=lambda b: (round(b[0] / _COLUMN_BUCKET_PT), round(b[1])))
    return "\n".join(b[4].strip() for b in blocks)


def _linearize_tables(tables: List[List[List[str]]]) -> str:
    """Wandelt erkannte Tabellen (Zeilen aus Zellen) in Text um, zeilenweise,
    layoutunabhängig von Spaltenbreiten/Farbschema (TC-T-008)."""
    lines: List[str] = []
    for table in tables:
        for row in table:
            cells = [cell.strip() for cell in row if cell and cell.strip()]
            if cells:
                lines.append(" ".join(cells))
    return "\n".join(lines)


def extract_pages(pdf_path: str) -> List[str]:
    """Extrahiert den Text jeder Seite eines PDFs als eigenen String.

    Enthält eine Seite Tabellen, wird deren Inhalt zeilenweise linearisiert;
    andernfalls wird der Fließtext spaltenbewusst gelesen.
    """
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        with pdfplumber.open(pdf_path) as plumber_pdf:
            for page_index, page in enumerate(doc):
                plumber_page = plumber_pdf.pages[page_index]
                tables = plumber_page.extract_tables()
                if tables:
                    pages_text.append(_linearize_tables(tables))
                else:
                    pages_text.append(_extract_page_text_columns(page))
    finally:
        doc.close()
    return pages_text
