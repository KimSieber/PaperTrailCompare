"""P1-Testfälle TC-G-001 und TC-G-002 für engine.page_group_detector.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 4.
Fixture: tests/fixtures/TC-G-001/ref.pdf (== TC-G-002/ref.pdf), ein
Batch-PDF mit 5 Dokumenten (3 Rechnungen, 2 Mahnungen), RE-2026-0002 über
2 Seiten.

Die Muster verwenden einen End-Anker ($), damit Folgeseiten eines
mehrseitigen Dokuments (Titel + " – Seite N") nicht fälschlich als neue
Gruppe erkannt werden – das lose Beispiel-Pattern aus profile_loader/
TC-P-001 ("Rechnung Nr\\..*") würde das nicht leisten.
"""
from pathlib import Path

from engine.page_group_detector import extract_page_groups
from engine.profile_loader import PageGroupPattern

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
