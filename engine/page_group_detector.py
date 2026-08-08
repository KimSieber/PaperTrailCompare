# file:    engine/page_group_detector.py
# purpose: Detects document boundaries within a batch PDF using regex
#          patterns on the first line of each page. Used by batch_processor
#          for PDF splitting (TC-B-004, TC-G-001 ff.).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09
# 
"""Erkennt Seitengruppen (einzelne Dokumente) innerhalb eines Batch-PDFs
anhand von Such-Patterns – z.B. um Rechnungen/Mahnungen in einer großen
Sammel-PDF-Datei voneinander abzugrenzen.

Ein Muster markiert den Beginn einer neuen Gruppe, wenn es auf die erste
Zeile einer Seite passt; alle folgenden Seiten ohne eigenen Treffer gehören
zur zuletzt begonnenen Gruppe.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from engine.pdf_extractor import extract_pages
from engine.profile_loader import PageGroupPattern


@dataclass
class PageGroup:
    name: str
    start_page: int
    pages: List[str] = field(default_factory=list)


def _match_group_name(first_line: str, compiled_patterns) -> Optional[str]:
    for pattern, name in compiled_patterns:
        if pattern.match(first_line):
            return name
    return None


def extract_page_groups(
    pdf_path: str,
    page_groups: Sequence[PageGroupPattern],
    group_filter: Optional[Sequence[str]] = None,
) -> List[PageGroup]:
    """Zerlegt ein Batch-PDF in Seitengruppen anhand der übergebenen Patterns.

    group_filter schränkt das Ergebnis auf Gruppen mit passendem Namen ein
    (TC-G-002); ohne group_filter werden alle erkannten Gruppen zurückgegeben.
    """
    compiled_patterns = [(re.compile(g.pattern), g.name) for g in page_groups]
    pages = extract_pages(pdf_path)

    groups: List[PageGroup] = []
    current: Optional[PageGroup] = None

    for page_num, page_text in enumerate(pages, start=1):
        first_line = page_text.split("\n", 1)[0]
        matched_name = _match_group_name(first_line, compiled_patterns)

        if matched_name is not None:
            current = PageGroup(name=matched_name, start_page=page_num, pages=[page_text])
            groups.append(current)
        elif current is not None:
            current.pages.append(page_text)
        # Seiten vor der ersten erkannten Gruppe werden ignoriert.

    if group_filter is not None:
        groups = [g for g in groups if g.name in group_filter]

    return groups
