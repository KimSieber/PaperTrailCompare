"""PDF-Textextraktion: liefert pro Seite einen normalisierten Text-String,
passend als Eingabe für engine.text_comparator.compare().

Nutzt PyMuPDF (fitz) als primäre Extraktions-Engine (Koordinaten, Spalten)
und pdfplumber ergänzend für Tabellenerkennung, siehe
doc/PaperTrailCompare_Architekturspezifikation.docx Abschnitt 4/6.2.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import fitz
import pdfplumber

_TEXT_BLOCK_TYPE = 0
_COLUMN_BUCKET_PT = 50  # Blockbreite-Toleranz zur Spaltenerkennung

# PyMuPDF-Textblock: (x0, y0, x1, y1, text, block_no, block_type)
TextBlock = Tuple[float, float, float, float, str, int, int]


def get_text_blocks(page: "fitz.Page") -> List[TextBlock]:
    """Liefert die nicht-leeren Textblöcke einer Seite, unsortiert.

    Wiederverwendbarer Baustein für andere Schicht-1-Module (z.B.
    region_filter), die dieselbe Block-Extraktion benötigen, aber vor der
    Sortierung noch Blöcke herausfiltern müssen (Regionen-Ausschluss)."""
    return [
        b for b in page.get_text("blocks")
        if b[6] == _TEXT_BLOCK_TYPE and b[4].strip()
    ]


def sort_blocks_columns(blocks: Sequence[TextBlock]) -> List[TextBlock]:
    """Sortiert Textblöcke spaltenweise (links vor rechts), statt strikt
    zeilenweise – nötig für mehrspaltige Layouts (TC-T-007)."""
    return sorted(blocks, key=lambda b: (round(b[0] / _COLUMN_BUCKET_PT), round(b[1])))


def join_block_text(blocks: Sequence[TextBlock]) -> str:
    """Fügt die Texte bereits sortierter Blöcke zu einem Seitentext zusammen."""
    return "\n".join(b[4].strip() for b in blocks)


def _extract_page_text_columns(page: "fitz.Page") -> str:
    """Liest den Text einer Seite spaltenweise (links vor rechts), statt
    strikt zeilenweise."""
    return join_block_text(sort_blocks_columns(get_text_blocks(page)))


def _linearize_tables(tables: List[List[List[Optional[str]]]]) -> str:
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
