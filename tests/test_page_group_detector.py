# file:    tests/test_page_group_detector.py
# purpose: Tests TC-G-001 to TC-G-003 for engine.page_group_detector.
#          Covers pattern-based page group identification, group filtering,
#          and groups with differing page counts.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Testfälle TC-G-001, TC-G-002 (P1) und TC-G-003 (P2) für
engine.page_group_detector.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 4.

Fixture TC-G-001/002: Batch-PDF mit 5 Dokumenten (3 Rechnungen, 2
Mahnungen), RE-2026-0002 über 2 Seiten. Die Muster verwenden einen
End-Anker ($), damit Folgeseiten eines mehrseitigen Dokuments (Titel +
" – Seite N") nicht fälschlich als neue Gruppe erkannt werden.

Fixture TC-G-003: 2 Dokumente mit identischem Fließtext, der bei cnd.pdf
(größere Schrift) auf mehr Seiten umbricht als bei ref.pdf. Fortsetzungs-
seiten tragen dort keinen Titel, daher reicht ein einfaches Pattern ohne
End-Anker-Sonderfall.
"""
from pathlib import Path

from engine.page_group_detector import extract_page_groups
from engine.profile_loader import PageGroupPattern
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"

PATTERNS = [
    PageGroupPattern(pattern=r"^Rechnung Nr\. \S+$", name="Rechnung"),
    PageGroupPattern(pattern=r"^Mahnung Nr\. \S+$", name="Mahnung"),
]


def test_tc_g_001_seitengruppe_per_such_pattern_identifizieren():
    groups = extract_page_groups(str(FIXTURES / "TC-G-001" / "ref.pdf"), PATTERNS)

    assert [g.name for g in groups] == [
        "Rechnung", "Mahnung", "Rechnung", "Mahnung", "Rechnung",
    ]
    # RE-2026-0002 hat 2 Seiten -> die dritte Gruppe (Index 2) muss beide enthalten.
    assert [len(g.pages) for g in groups] == [1, 1, 2, 1, 1]
    assert groups[2].start_page == 3
    assert "RE-2026-0002" in groups[2].pages[0]
    assert "Fortsetzung des Dokuments" in groups[2].pages[1]


def test_tc_g_002_nur_bestimmte_seitengruppen_vergleichen():
    groups = extract_page_groups(
        str(FIXTURES / "TC-G-001" / "ref.pdf"), PATTERNS, group_filter=["Rechnung"]
    )

    assert len(groups) == 3
    assert all(g.name == "Rechnung" for g in groups)
    assert [len(g.pages) for g in groups] == [1, 2, 1]


def test_tc_g_003_seitengruppen_mit_unterschiedlichem_seitenumfang():
    ref_path = str(FIXTURES / "TC-G-003" / "ref.pdf")
    cnd_path = str(FIXTURES / "TC-G-003" / "cnd.pdf")
    rechnung_pattern = [PageGroupPattern(pattern=r"^Rechnung Nr\. \S+$", name="Rechnung")]

    ref_groups = extract_page_groups(ref_path, rechnung_pattern)
    cnd_groups = extract_page_groups(cnd_path, rechnung_pattern)

    assert len(ref_groups) == len(cnd_groups) == 2
    # ref: 2 Seiten pro Dokument, cnd: 4 Seiten pro Dokument – unterschiedlicher
    # Seitenumfang bei identischem Fließtext (größere Schrift in cnd.pdf).
    assert [len(g.pages) for g in ref_groups] == [2, 2]
    assert [len(g.pages) for g in cnd_groups] == [4, 4]

    for ref_group, cnd_group in zip(ref_groups, cnd_groups):
        result = compare(ref_group.pages, cnd_group.pages)
        assert result.has_delta is False
        assert result.deltas == []
