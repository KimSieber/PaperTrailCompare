"""Koordinatenbasierter Ausschluss definierter Seitenbereiche vom Vergleich.

Regionen werden in PyMuPDF-Koordinaten angegeben (Ursprung oben links, y
wächst nach unten) – dieselbe Konvention wie engine.pdf_extractor, dessen
Block-Extraktions-/Spalten-Sortierlogik hier wiederverwendet wird (beide
Schicht 1, siehe CLAUDE.md Modulübersicht).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import fitz

from engine.pdf_extractor import get_text_blocks, join_block_text, sort_blocks_columns


@dataclass
class Region:
    page: int  # 1-basiert
    x: float
    y: float
    w: float
    h: float

    def overlaps(self, bbox: Sequence[float]) -> bool:
        x0, y0, x1, y1 = bbox
        return not (
            x1 <= self.x
            or x0 >= self.x + self.w
            or y1 <= self.y
            or y0 >= self.y + self.h
        )


def extract_pages_excluding_regions(
    pdf_path: str, regions: Sequence[Region]
) -> List[str]:
    """Wie pdf_extractor.extract_pages, aber Textblöcke, die eine der
    angegebenen Regionen auf ihrer Seite überlappen, werden vor der
    Extraktion entfernt."""
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        for page_index, page in enumerate(doc):
            page_num = page_index + 1
            page_regions = [r for r in regions if r.page == page_num]

            blocks = get_text_blocks(page)
            blocks = [
                b for b in blocks
                if not any(r.overlaps(b[:4]) for r in page_regions)
            ]
            blocks = sort_blocks_columns(blocks)
            pages_text.append(join_block_text(blocks))
    finally:
        doc.close()
    return pages_text
