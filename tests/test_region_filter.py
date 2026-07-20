"""P1-Testfälle TC-E-001 und TC-E-002 für engine.region_filter.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 3.
Fixtures: tests/fixtures/TC-E-001/, tests/fixtures/TC-E-002/ (generiert via
tests/generate_fixtures.py::generate_tc_e_001_002) – ref/cnd unterscheiden
sich nur im Druckdatum im Kopfbereich, auf Seite 1 UND Seite 2.
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
