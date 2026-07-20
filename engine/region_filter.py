"""Koordinatenbasierter Ausschluss definierter Seitenbereiche vom Vergleich.

Regionen werden in PyMuPDF-Koordinaten angegeben (Ursprung oben links, y
wächst nach unten) – dieselbe Konvention wie engine.pdf_extractor, das
ebenfalls auf fitz basiert.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import fitz

_TEXT_BLOCK_TYPE = 0
_COLUMN_BUCKET_PT = 50


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

            blocks = [
                b for b in page.get_text("blocks")
                if b[6] == _TEXT_BLOCK_TYPE and b[4].strip()
            ]
            blocks = [
                b for b in blocks
                if not any(r.overlaps(b[:4]) for r in page_regions)
            ]
            blocks.sort(key=lambda b: (round(b[0] / _COLUMN_BUCKET_PT), round(b[1])))
            pages_text.append("\n".join(b[4].strip() for b in blocks))
    finally:
        doc.close()
    return pages_text
