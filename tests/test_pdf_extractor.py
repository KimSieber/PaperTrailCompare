# file:    tests/test_pdf_extractor.py
# purpose: Tests for engine.pdf_extractor including TC-X-001/002 (native
#          extraction), TC-T-007/008 (columns, tables), spacewidth
#          calibration, and exclude-region integration.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Testfälle für engine.pdf_extractor.

TC-X-001/002: eigene P1-Basistests für native Textextraktion – die
Testspezifikation definiert dafür keine eigenen Testfall-IDs.

TC-T-007/008: laut Testspezifikation unter "Modul: text_comparator"
gelistet, betreffen inhaltlich aber die PDF-Extraktion (Mehrspaltigkeit,
Tabellenerkennung) und werden daher hier statt in test_text_comparator.py
umgesetzt, siehe CLAUDE.md Modulübersicht (pdf_extractor: "Mehrspaltigkeit,
Tabellen").

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 2.
"""
import shutil
from pathlib import Path

import pytest

import fitz

from engine.pdf_extractor import (
    SpacewidthCalibration,
    _calibrate_from_gaps,
    _reconstruct_line_text,
    calibrate_spacewidths,
    extract_pages,
    extract_pages_for_profile,
)
from engine.profile_loader import ExcludeRegion, OcrConfig, Profile
from engine.text_comparator import compare

FIXTURES = Path(__file__).parent / "fixtures"


def test_tc_x_001_nativen_text_aus_einseitigem_pdf_extrahieren():
    pages = extract_pages(str(FIXTURES / "TC-X-001" / "doc.pdf"))

    assert len(pages) == 1
    assert "einfacher, einseitiger Testtext" in pages[0]


def test_tc_x_002_text_aus_mehrseitigem_pdf_seitenweise_extrahieren():
    pages = extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))

    assert len(pages) == 3
    assert "Seite eins" in pages[0]
    assert "Seite zwei" in pages[1]
    assert "Seite drei" in pages[2]


def test_tc_t_007_mehrspaltiger_text_korrekte_lesereihenfolge():
    ref_pages = extract_pages(str(FIXTURES / "TC-T-007" / "ref.pdf"))
    cnd_pages = extract_pages(str(FIXTURES / "TC-T-007" / "cnd.pdf"))

    assert len(ref_pages) == 1
    page_text = ref_pages[0]

    # Spalte 1 muss vollständig vor Spalte 2 erscheinen (kein Mischtext).
    pos_a = page_text.index("Abschnitt A")
    pos_a4 = page_text.index("A 4: Fazit")
    pos_b = page_text.index("Abschnitt B")
    assert pos_a < pos_a4 < pos_b

    result = compare(ref_pages, cnd_pages)
    assert result.has_delta is False
    assert result.deltas == []


def test_extract_pages_for_profile_ohne_profil_wie_extract_pages():
    pages, ocr_used = extract_pages_for_profile(str(FIXTURES / "TC-X-002" / "doc.pdf"), None)

    assert pages == extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))
    assert ocr_used is False


def test_extract_pages_for_profile_ocr_deaktiviert_wie_extract_pages():
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=False))
    pages, ocr_used = extract_pages_for_profile(str(FIXTURES / "TC-X-002" / "doc.pdf"), profile)

    assert pages == extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))
    assert ocr_used is False


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract-Binary nicht installiert (siehe README.md 'Tesseract OCR')",
)
def test_extract_pages_for_profile_ocr_aktiviert_nutzt_fallback():
    """Bei profile.ocr.enabled=True muss extract_pages_for_profile die
    gescannte Seite (kein nativer Textlayer) via OCR-Fallback lesen,
    statt leeren Text zu liefern (siehe TC-O-002-Fixture)."""
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=True))
    pages, ocr_used = extract_pages_for_profile(str(FIXTURES / "TC-O-002" / "ref.pdf"), profile)

    assert len(pages) == 2
    assert "AB-2026-00099" in pages[0]
    assert "Lieferdatum" in pages[1]  # nur via OCR lesbar (Seite ohne Textlayer)
    assert ocr_used is True


def test_extract_pages_for_profile_mode_off_ignoriert_enabled_flag():
    """mode_reference/mode_candidate gewinnen, sobald sie explizit gesetzt
    sind - auch gegen ein 'enabled=True', das sonst (ohne Modus) fallback
    für beide Seiten bedeuten würde."""
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=True, mode_reference="off"))
    pages, ocr_used = extract_pages_for_profile(
        str(FIXTURES / "TC-O-002" / "ref.pdf"), profile, role="reference"
    )

    assert ocr_used is False
    assert pages[1].strip() == ""  # Seite ohne Textlayer bleibt leer ohne OCR


def test_extract_pages_for_profile_mode_candidate_unabhaengig_von_reference(monkeypatch):
    """mode_reference und mode_candidate sind unabhängig voneinander
    einstellbar (Kernanforderung: Referenz per OCR, Kandidat nativ).

    OCR-Aufruf wird gemockt (siehe engine.ocr_extractor._ocr_page) - ein
    Layer-1-Unit-Test darf nicht von einer installierten Tesseract-Binary
    abhängen. "Lieferdatum" auf Seite 2 stammt hier bewusst aus dem
    gemockten Rückgabewert, nicht aus echter Bilderkennung."""
    import engine.ocr_extractor as ocr_extractor

    monkeypatch.setattr(
        ocr_extractor.pytesseract,
        "image_to_string",
        lambda image, lang=None: "Lieferdatum: 25.07.2026",
    )

    profile = Profile(
        version="1.0",
        ocr=OcrConfig(mode_reference="fallback", mode_candidate="off"),
    )

    ref_pages, ref_ocr_used = extract_pages_for_profile(
        str(FIXTURES / "TC-O-002" / "ref.pdf"), profile, role="reference"
    )
    cnd_pages, cnd_ocr_used = extract_pages_for_profile(
        str(FIXTURES / "TC-O-002" / "ref.pdf"), profile, role="candidate"
    )

    assert ref_ocr_used is True
    assert "Lieferdatum" in ref_pages[1]
    assert cnd_ocr_used is False
    assert cnd_pages[1].strip() == ""


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract-Binary nicht installiert (siehe README.md 'Tesseract OCR')",
)
def test_extract_pages_for_profile_mode_force_liest_auch_native_seiten_per_ocr():
    """'force' muss OCR auch auf Seiten mit vorhandenem, aber unbrauchbarem
    nativem Text anwenden - anders als 'fallback', das nur bei leerem Text
    greift (siehe TC-X-002: Seiten haben sauberen nativen Text, force liest
    trotzdem via Tesseract)."""
    profile = Profile(version="1.0", ocr=OcrConfig(mode_reference="force"))
    pages, ocr_used = extract_pages_for_profile(
        str(FIXTURES / "TC-X-002" / "doc.pdf"), profile, role="reference"
    )

    assert ocr_used is True
    assert len(pages) == 3
    assert "Seite eins" in pages[0]


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract-Binary nicht installiert (siehe README.md 'Tesseract OCR')",
)
def test_extract_pages_for_profile_dpi_wird_an_ocr_durchgereicht(monkeypatch):
    """profile.ocr.dpi (Default 200, siehe Messung) muss bis zum
    OCR-Aufruf durchgereicht werden, nicht der ocr_extractor-eigene
    Default (300) verwendet werden."""
    seen_dpi = {}

    def fake_fallback(pdf_path, lang="deu", dpi=300, regions=None, warnings=None):
        seen_dpi["dpi"] = dpi
        return (["x"], False)

    import engine.pdf_extractor as pdf_extractor_module

    monkeypatch.setattr(
        "engine.ocr_extractor.extract_pages_with_ocr_fallback", fake_fallback
    )
    profile = Profile(version="1.0", ocr=OcrConfig(mode_reference="fallback", dpi=222))
    pdf_extractor_module.extract_pages_for_profile(
        str(FIXTURES / "TC-X-002" / "doc.pdf"), profile, role="reference"
    )

    assert seen_dpi["dpi"] == 222


def _make_rawdict_chars(specs):
    """specs: Liste von (char, x0) mit fester Zeichenbreite 6.0pt/Höhe 10pt -
    Kurzform für handgefertigte rawdict-Zeichen-Tupel in den Tests unten."""
    return [{"c": c, "bbox": (x0, 0.0, x0 + 6.0, 10.0)} for c, x0 in specs]


def _make_line(chars, font="Testfont", size=12.0):
    return {"spans": [{"font": font, "size": size, "chars": chars}]}


def test_calibrate_from_gaps_findet_klaren_sprung():
    """Nachgebaut aus den echten gemessenen Werten der Diagnose-Session:
    Intra-Wort-Rauschen ±0.24pt, Space-Breite 4.08pt."""
    intra = [-0.24, -0.1, 0.0, 0.1, 0.24, -0.2, 0.15, -0.05, 0.05, 0.2] * 3
    inter = [4.08, 3.95, 4.15, 4.0, 4.1] * 5
    spacewidth, criterion_met = _calibrate_from_gaps(intra + inter)
    assert criterion_met is True
    assert 0.24 < spacewidth < 4.0


def test_calibrate_from_gaps_lehnt_gleichmaessige_verteilung_ab():
    """Keine zwei erkennbaren Cluster -> Sicherheits-Fallback statt Rateverfahren."""
    gaps = [i * 0.05 for i in range(100)]  # gleichmäßig 0.0 .. 4.95
    spacewidth, criterion_met = _calibrate_from_gaps(gaps)
    assert criterion_met is False
    assert spacewidth is None


def test_calibrate_from_gaps_lehnt_zu_wenige_messwerte_ab():
    spacewidth, criterion_met = _calibrate_from_gaps([-0.1, 0.1, 4.0, 4.1])
    assert criterion_met is False
    assert spacewidth is None


def test_calibrate_spacewidths_nutzt_echte_leerzeichen_wenn_vorhanden():
    """Ein Dokument mit normalem Fließtext (echte Leerzeichen-Glyphen) muss
    calibrate_spacewidths() über die reale rawdict-Extraktion (nicht über
    handgefertigte Dicts) auf source='real_spaces' kalibrieren."""
    doc = fitz.open(str(FIXTURES / "TC-T-009" / "cnd.pdf"))
    try:
        calibration = calibrate_spacewidths(doc)
    finally:
        doc.close()

    assert calibration, "Es sollte mindestens eine (Font, Größe)-Kalibrierung geben"
    matched = [cal for cal in calibration.values() if cal.source == "real_spaces" and cal.criterion_met]
    assert matched, f"Erwartet mindestens eine real_spaces-Kalibrierung, erhalten: {calibration}"


def test_reconstruct_line_text_setzt_wortgrenzen_bei_belastbarer_kalibrierung():
    """Sperrsatz ohne Leerzeichen-Zeichen, aber mit klar erkennbarer
    Wortgrenze (großer Abstand) - muss zu einem echten Leerzeichen an der
    richtigen Stelle rekonstruiert werden, ohne die Wörter selbst zu zerlegen."""
    chars = _make_rawdict_chars([
        ("S", 0), ("p", 6.24), ("a", 12.0), ("r", 18.24),  # Intra-Wort: ±0.24pt Rauschen
        ("V", 28.32), ("e", 34.32), ("r", 40.56),          # Wortgrenze: Lücke ~4.08pt vor "V"
    ])
    line = _make_line(chars, font="Grossrechner", size=10.0)
    calibration = {
        ("Grossrechner", 10.0): SpacewidthCalibration(
            font="Grossrechner", size=10.0, spacewidth=4.08, source="elbow",
            sample_count=50, criterion_met=True,
        )
    }
    result = _reconstruct_line_text(line, calibration)
    assert result == "Spar Ver"


def test_reconstruct_line_text_erhaelt_echte_leerzeichen_unveraendert():
    """Normaler Text mit echten Leerzeichen darf durch die Rekonstruktion
    nicht verändert werden (No-Op-Anforderung aus dem Plan, Punkt c)."""
    chars = _make_rawdict_chars([
        ("D", 0), ("i", 6), ("e", 12), (" ", 18), ("K", 22.5), ("a", 28.5), ("t", 34.5), ("z", 40.5),
    ])
    line = _make_line(chars, font="Kandidat", size=11.0)
    calibration = {
        ("Kandidat", 11.0): SpacewidthCalibration(
            font="Kandidat", size=11.0, spacewidth=4.5, source="real_spaces",
            sample_count=10, criterion_met=True,
        )
    }
    result = _reconstruct_line_text(line, calibration)
    assert result == "Die Katz"


def test_reconstruct_line_text_faellt_bei_fehlender_kalibrierung_auf_native_zurueck():
    """Ohne belastbare Kalibrierung (criterion_met=False) bleibt der Text
    unverändert - kein Rateverfahren, siehe Plan-Ergänzung des Nutzers."""
    chars = _make_rawdict_chars([("S", 0), ("p", 6), ("a", 12), ("r", 18)])
    line = _make_line(chars, font="Unklar", size=9.0)
    calibration = {
        ("Unklar", 9.0): SpacewidthCalibration(
            font="Unklar", size=9.0, spacewidth=None, source="insufficient_data",
            sample_count=4, criterion_met=False,
        )
    }
    result = _reconstruct_line_text(line, calibration)
    assert result == "Spar"


def test_tc_t_009_sperrsatz_ohne_leerzeichen_faellt_sicher_auf_native_zurueck():
    """Integrationstest über extract_pages_for_profile(): Das reale Muster
    aus dem Großrechner-Befund (jede Buchstabenlücke gleich groß, keine
    Unterscheidung zwischen Intra-Wort- und Wortgrenzen-Abstand möglich)
    muss den Sicherheits-Fallback auslösen, nicht ein falsches Rateergebnis."""
    ref_path = str(FIXTURES / "TC-T-009" / "ref.pdf")
    profile = Profile(version="1.0", text_extraction="reconstruct")

    pages_reconstruct, _ = extract_pages_for_profile(ref_path, profile)
    pages_native = extract_pages(ref_path)

    assert pages_reconstruct == pages_native


def test_tc_t_009_normales_dokument_bleibt_unter_reconstruct_unveraendert():
    """Gegenprobe: ein normales Dokument mit echten Leerzeichen liefert unter
    text_extraction='reconstruct' dieselbe Ausgabe wie im nativen Modus."""
    cnd_path = str(FIXTURES / "TC-T-009" / "cnd.pdf")
    profile = Profile(version="1.0", text_extraction="reconstruct")

    pages_reconstruct, _ = extract_pages_for_profile(cnd_path, profile)
    pages_native = extract_pages(cnd_path)

    assert pages_reconstruct == pages_native


def test_tc_t_008_tabellenerkennung_kein_falsches_delta():
    ref_pages = extract_pages(str(FIXTURES / "TC-T-008" / "ref.pdf"))
    cnd_pages = extract_pages(str(FIXTURES / "TC-T-008" / "cnd.pdf"))

    assert "Artikel Alpha" in ref_pages[0]
    assert "907,97 EUR" in ref_pages[0]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


# Kopfbereich mit "Druckdatum: ..." und "Seite N" liegt bei y ca. 34-65pt,
# x ca. 42-152pt (fitz-Koordinaten) - dieselbe Region wie in
# test_region_filter.py::HEADER_REGION, hier aber über profile.exclude_regions
# und den Produktivpfad extract_pages_for_profile statt über den direkten
# Aufruf von region_filter.extract_pages_excluding_regions.
_HEADER_EXCLUDE_REGION = dict(x=0, y=0, width=250, height=80)


def test_exclude_regions_wirkt_ueber_extract_pages_for_profile_tc_e_001():
    """Verdrahtungstest: profile.exclude_regions muss über den
    Produktivpfad (extract_pages_for_profile, genutzt von CLI und Batch)
    tatsächlich wirken - nicht nur über den direkten Aufruf von
    region_filter.extract_pages_excluding_regions (siehe Befund: die
    Verdrahtung fehlte, obwohl TC-E-001/002 grün waren)."""
    profile = Profile(
        version="1.0",
        exclude_regions=[
            ExcludeRegion(page=1, **_HEADER_EXCLUDE_REGION),
            ExcludeRegion(page=2, **_HEADER_EXCLUDE_REGION),
        ],
    )

    ref_pages, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "ref.pdf"), profile, role="reference")
    cnd_pages, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "cnd.pdf"), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_exclude_regions_gilt_nur_fuer_definierte_seite_tc_e_002():
    """Wie TC-E-002: Ausschluss nur für Seite 1 - der Datumsunterschied im
    Kopfbereich auf Seite 2 muss über den Produktivpfad weiterhin als
    Delta erkannt werden (Seitenbezug bleibt bei der Verdrahtung erhalten)."""
    profile = Profile(
        version="1.0",
        exclude_regions=[ExcludeRegion(page=1, **_HEADER_EXCLUDE_REGION)],
    )

    ref_pages, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-002" / "ref.pdf"), profile, role="reference")
    cnd_pages, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-002" / "cnd.pdf"), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert any(delta.page == 2 for delta in result.deltas)


def test_exclude_regions_auf_tabellenseite_erzeugt_warnung_statt_stiller_wirkungslosigkeit():
    """Tabellenlinearisierung ist nicht block-basiert und kann eine
    konfigurierte Region daher nicht anwenden - das darf nicht klanglos
    passieren, sondern muss über den warnings-Parameter sichtbar werden
    (siehe _warn_if_table_page_has_regions)."""
    profile = Profile(
        version="1.0",
        exclude_regions=[ExcludeRegion(page=1, x=0, y=0, width=10, height=10)],
    )
    warnings: list = []

    extract_pages_for_profile(
        str(FIXTURES / "TC-T-008" / "ref.pdf"), profile, role="reference", warnings=warnings
    )

    assert len(warnings) == 1
    assert "Seite 1" in warnings[0]
    assert "Tabellenerkennung" in warnings[0]


def test_exclude_regions_wirkt_auch_unter_text_extraction_reconstruct():
    """Anforderung (a): der Ausschluss muss auch für
    text_extraction='reconstruct' funktionieren, nicht nur für 'native'."""
    profile = Profile(
        version="1.0",
        text_extraction="reconstruct",
        exclude_regions=[
            ExcludeRegion(page=1, **_HEADER_EXCLUDE_REGION),
            ExcludeRegion(page=2, **_HEADER_EXCLUDE_REGION),
        ],
    )

    ref_pages, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "ref.pdf"), profile, role="reference")
    cnd_pages, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "cnd.pdf"), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []
