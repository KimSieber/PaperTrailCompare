# file:    engine/region_filter.py
# purpose: Re-exports Region from pdf_extractor and provides
#          regions_from_profile() to convert profile exclude-regions into
#          Region instances (TC-E-001 ff.).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-18

"""Koordinatenbasierter Ausschluss definierter Seitenbereiche vom Vergleich.

Regionen werden in PyMuPDF-Koordinaten angegeben (Ursprung oben links, y
wächst nach unten) – dieselbe Konvention wie engine.pdf_extractor.

Region selbst ist in engine.pdf_extractor definiert (dort direkt von den
Extraktionspfaden extract_pages()/_extract_pages_reconstructed() genutzt,
siehe pdf_extractor.extract_pages_for_profile) und wird hier nur unter ihrem
angestammten Namen re-exportiert, damit bestehender Code/Tests
(`from engine.region_filter import Region`) unverändert funktionieren.
"""
from __future__ import annotations

from typing import List

from engine.pdf_extractor import Region
from engine.profile_loader import Profile

__all__ = ["Region", "regions_from_profile"]


def regions_from_profile(profile: Profile) -> List[Region]:
    """Wandelt profile.exclude_regions (profile_loader.ExcludeRegion:
    page/x/y/width/height) in Region-Instanzen (page/x/y/w/h) - dieselbe
    Umrechnung, die pdf_extractor.extract_pages_for_profile intern
    vornimmt. Nützlich für Aufrufer, die die Regionen unabhängig von
    extract_pages_for_profile benötigen (z.B. eigene Diagnose-Skripte)."""
    return [
        Region(page=r.page, x=r.x, y=r.y, w=r.width, h=r.height, page_from=r.page_from)
        for r in profile.exclude_regions
    ]
