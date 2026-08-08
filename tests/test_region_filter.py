# file:    tests/test_region_filter.py
# purpose: Tests TC-E-001 to TC-E-003 for engine.region_filter. Covers
#          single-region exclusion, page-scoped exclusion, and multi-region
#          scenarios with counter-proof tests.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Testfälle TC-E-001, TC-E-002 (P1) und TC-E-003 (P2) für engine.region_filter.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 3.
Fixtures: tests/fixtures/TC-E-001/, tests/fixtures/TC-E-002/ (generiert via
tests/generate_fixtures.py::generate_tc_e_001_002) – ref/cnd unterscheiden
sich nur im Druckdatum im Kopfbereich, auf Seite 1 UND Seite 2.
Fixture TC-E-003 (generate_tc_e_003): 2 Seiten, 3 Regionen (Logo auf Seite 1,
Stempel + Footer auf Seite 2) mit abweichendem Inhalt, Körpertext identisch.
"""
from pathlib import Path

from engine.region_filter import Region, extract_pages_excluding_regions
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"

# Kopfbereich mit "Druckdatum: ..." und "Seite N" liegt bei y ca. 34-65pt,
# x ca. 42-152pt (fitz-Koordinaten, Ursprung oben links).
HEADER_REGION = dict(x=0, y=0, w=250, h=80)


def test_tc_e_001_region_vom_vergleich_ausschliessen():
    """Datum im Kopfbereich unterscheidet sich auf Seite 1 und 2 –
    mit Ausschluss-Region auf beiden Seiten wird das nicht als Delta gemeldet."""
    regions = [Region(page=1, **HEADER_REGION), Region(page=2, **HEADER_REGION)]

    ref_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-001" / "ref.pdf"), regions
    )
    cnd_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-001" / "cnd.pdf"), regions
    )

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_e_002_region_ausschluss_gilt_nur_fuer_definierte_seite():
    """Ausschluss ist nur für Seite 1 konfiguriert – der Datumsunterschied
    im Kopfbereich auf Seite 2 muss weiterhin als Delta erkannt werden."""
    regions = [Region(page=1, **HEADER_REGION)]

    ref_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-002" / "ref.pdf"), regions
    )
    cnd_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-002" / "cnd.pdf"), regions
    )

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert any(delta.page == 2 for delta in result.deltas)


# Logo (Seite 1) bbox ca. x=462-553, y=33-45; Stempel (Seite 2) bbox ca.
# x=439-478, y=412-423; Footer (Seite 2) bbox ca. x=42-185, y=800-810
# (fitz-Koordinaten, Ursprung oben links).
TC_E_003_REGIONS = [
    Region(page=1, x=440, y=20, w=140, h=40),   # Logo
    Region(page=2, x=420, y=400, w=140, h=35),  # Stempel
    Region(page=2, x=0, y=795, w=220, h=20),    # Footer
]


def test_tc_e_003_mehrere_ausschluss_regionen():
    """3 Regionen auf verschiedenen Seiten (Logo S.1, Stempel+Footer S.2)
    unterscheiden sich inhaltlich – mit allen 3 exclude_regions kein Delta,
    da der Körpertext auf beiden Seiten identisch ist."""
    ref_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-003" / "ref.pdf"), TC_E_003_REGIONS
    )
    cnd_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-003" / "cnd.pdf"), TC_E_003_REGIONS
    )

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_e_003_ohne_regionen_ergeben_sich_deltas():
    """Gegenprobe: ohne Ausschluss-Regionen muss der Unterschied in Logo,
    Stempel und Footer tatsächlich als Delta auffallen – stellt sicher,
    dass der vorherige 'kein Delta'-Test nicht zufällig grün ist."""
    ref_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-003" / "ref.pdf"), []
    )
    cnd_pages = extract_pages_excluding_regions(
        str(FIXTURES / "TC-E-003" / "cnd.pdf"), []
    )

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert len(result.deltas) == 3
