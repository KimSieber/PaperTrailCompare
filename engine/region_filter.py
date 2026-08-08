# file:    engine/region_filter.py
# purpose: Coordinate-based exclusion of page regions from comparison.
#          Re-exports Region from pdf_extractor and provides a standalone
#          extraction function with region filtering (TC-E-001 ff.).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Koordinatenbasierter Ausschluss definierter Seitenbereiche vom Vergleich.

Regionen werden in PyMuPDF-Koordinaten angegeben (Ursprung oben links, y
wächst nach unten) – dieselbe Konvention wie engine.pdf_extractor, dessen
Block-Extraktions-/Spalten-Sortierlogik hier wiederverwendet wird (beide
Schicht 1, siehe CLAUDE.md Modulübersicht).

Region selbst ist in engine.pdf_extractor definiert (dort direkt von den
Extraktionspfaden extract_pages()/_extract_pages_reconstructed() genutzt,
siehe pdf_extractor.extract_pages_for_profile) und wird hier nur unter ihrem
angestammten Namen re-exportiert, damit bestehender Code/Tests
(`from engine.region_filter import Region`) unverändert funktionieren.
"""
from __future__ import annotations

from typing import List, Sequence

import fitz

from engine.pdf_extractor import (
    Region,
    filter_blocks_by_regions,
    get_text_blocks,
    join_block_text,
    sort_blocks_columns,
)
from engine.profile_loader import Profile

__all__ = ["Region", "extract_pages_excluding_regions", "regions_from_profile"]


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
            blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
            blocks = sort_blocks_columns(blocks)
            pages_text.append(join_block_text(blocks))
    finally:
        doc.close()
    return pages_text


def regions_from_profile(profile: Profile) -> List[Region]:
    """Wandelt profile.exclude_regions (profile_loader.ExcludeRegion:
    page/x/y/width/height) in Region-Instanzen (page/x/y/w/h) - dieselbe
    Umrechnung, die pdf_extractor.extract_pages_for_profile intern
    vornimmt. Nützlich für Aufrufer, die die Regionen unabhängig von
    extract_pages_for_profile benötigen (z.B. eigene Diagnose-Skripte)."""
    return [
        Region(page=r.page, x=r.x, y=r.y, w=r.width, h=r.height)
        for r in profile.exclude_regions
    ]
