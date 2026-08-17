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

import pymupdf
from reportlab.pdfgen import canvas

from engine.pdf_extractor import (
    Region,
    SpacewidthCalibration,
    _calibrate_from_gaps,
    _extract_page_text_columns,
    _reconstruct_line_text,
    calibrate_spacewidths,
    extract_pages,
    extract_pages_for_profile,
    filter_blocks_by_regions,
    get_text_blocks,
    separate_compare_region_blocks,
    split_wide_blocks,
)
from engine.profile_loader import ExcludeRegion, OcrConfig, Profile, CompareRegion
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
    pages, ocr_used, _ = extract_pages_for_profile(str(FIXTURES / "TC-X-002" / "doc.pdf"), None)

    assert pages == extract_pages(str(FIXTURES / "TC-X-002" / "doc.pdf"))
    assert ocr_used is False


def test_extract_pages_for_profile_ocr_deaktiviert_wie_extract_pages():
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=False))
    pages, ocr_used, _ = extract_pages_for_profile(str(FIXTURES / "TC-X-002" / "doc.pdf"), profile)

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
    pages, ocr_used, _ = extract_pages_for_profile(str(FIXTURES / "TC-O-002" / "ref.pdf"), profile)

    assert len(pages) == 2
    assert "AB-2026-00099" in pages[0]
    assert "Lieferdatum" in pages[1]  # nur via OCR lesbar (Seite ohne Textlayer)
    assert ocr_used is True


def test_extract_pages_for_profile_mode_off_ignoriert_enabled_flag():
    """mode_reference/mode_candidate gewinnen, sobald sie explizit gesetzt
    sind - auch gegen ein 'enabled=True', das sonst (ohne Modus) fallback
    für beide Seiten bedeuten würde."""
    profile = Profile(version="1.0", ocr=OcrConfig(enabled=True, mode_reference="off"))
    pages, ocr_used, _ = extract_pages_for_profile(
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

    ref_pages, ref_ocr_used, _ = extract_pages_for_profile(
        str(FIXTURES / "TC-O-002" / "ref.pdf"), profile, role="reference"
    )
    cnd_pages, cnd_ocr_used, _ = extract_pages_for_profile(
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
    pages, ocr_used, _ = extract_pages_for_profile(
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

    def fake_fallback(pdf_path, lang="deu", dpi=300, regions=None, warnings=None, compare_regions=None):
        seen_dpi["dpi"] = dpi
        return (["x"], False, [{}])

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
    doc = pymupdf.open(str(FIXTURES / "TC-T-009" / "cnd.pdf"))
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

    pages_reconstruct, _, _ = extract_pages_for_profile(ref_path, profile)
    pages_native = extract_pages(ref_path)

    assert pages_reconstruct == pages_native


def test_tc_t_009_normales_dokument_bleibt_unter_reconstruct_unveraendert():
    """Gegenprobe: ein normales Dokument mit echten Leerzeichen liefert unter
    text_extraction='reconstruct' dieselbe Ausgabe wie im nativen Modus."""
    cnd_path = str(FIXTURES / "TC-T-009" / "cnd.pdf")
    profile = Profile(version="1.0", text_extraction="reconstruct")

    pages_reconstruct, _, _ = extract_pages_for_profile(cnd_path, profile)
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

    ref_pages, _, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "ref.pdf"), profile, role="reference")
    cnd_pages, _, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "cnd.pdf"), profile, role="candidate")

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

    ref_pages, _, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-002" / "ref.pdf"), profile, role="reference")
    cnd_pages, _, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-002" / "cnd.pdf"), profile, role="candidate")

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

    ref_pages, _, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "ref.pdf"), profile, role="reference")
    cnd_pages, _, _ = extract_pages_for_profile(str(FIXTURES / "TC-E-001" / "cnd.pdf"), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


# Kopfregion (fitz-Koordinaten, Ursprung oben links): x=0, y=0, w=250, h=80
# -> Reportlab-y (Ursprung unten links, Standard-Letter-Seite 612x792pt)
# liegt bei drawString(30, 750) innerhalb dieses Bandes (712-792).
_MULTI_PAGE_HEADER_REGION = dict(x=0, y=0, width=250, height=80)
# Fußregion: fitz y=700..800 -> Reportlab-y 0..92, drawString(30, 50) liegt
# innerhalb dieses Bandes.
_MULTI_PAGE_FOOTER_REGION = dict(x=0, y=700, width=612, height=100)


def _write_multi_page_pdf(path: Path, pages: list) -> None:
    """Erzeugt ein N-seitiges PDF; jede Seite bekommt einen Kopfbereich
    (oben, innerhalb von _MULTI_PAGE_HEADER_REGION) und einen Fußbereich
    (unten, innerhalb von _MULTI_PAGE_FOOTER_REGION) mit unterscheidbarem
    Text, sowie einen unveränderten Fließtext-Body dazwischen."""
    c = canvas.Canvas(str(path))
    for index, (header, footer) in enumerate(pages, start=1):
        c.drawString(30, 750, header)
        c.drawString(30, 400, f"Body Seite {index} unveraendert.")
        c.drawString(30, 50, footer)
        c.showPage()
    c.save()


def test_exclude_region_page_zero_applies_to_all_pages(tmp_path):
    """ExcludeRegion(page=0, ...) muss die Kopfregion auf allen Seiten
    ausschließen, obwohl sie sich zwischen ref und cnd auf jeder Seite
    unterscheidet."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_multi_page_pdf(ref_path, [
        (f"Ref-Header Seite {n}", "Fusszeile gleich") for n in range(1, 4)
    ])
    _write_multi_page_pdf(cnd_path, [
        (f"Cnd-Header Seite {n}", "Fusszeile gleich") for n in range(1, 4)
    ])

    profile = Profile(
        version="1.0",
        exclude_regions=[ExcludeRegion(page=0, **_MULTI_PAGE_HEADER_REGION)],
    )

    ref_pages, _, _ = extract_pages_for_profile(str(ref_path), profile, role="reference")
    cnd_pages, _, _ = extract_pages_for_profile(str(cnd_path), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_exclude_region_page_from_applies_from_given_page(tmp_path):
    """ExcludeRegion(page_from=2, ...) muss die Kopfregion ab Seite 2 bis
    zum Dokumentende ausschließen - der Unterschied auf Seite 1 muss aber
    weiterhin als Delta erkannt werden."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_multi_page_pdf(ref_path, [
        (f"Ref-Header Seite {n}", "Fusszeile gleich") for n in range(1, 4)
    ])
    _write_multi_page_pdf(cnd_path, [
        (f"Cnd-Header Seite {n}", "Fusszeile gleich") for n in range(1, 4)
    ])

    profile = Profile(
        version="1.0",
        exclude_regions=[ExcludeRegion(page_from=2, **_MULTI_PAGE_HEADER_REGION)],
    )

    ref_pages, _, _ = extract_pages_for_profile(str(ref_path), profile, role="reference")
    cnd_pages, _, _ = extract_pages_for_profile(str(cnd_path), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert {delta.page for delta in result.deltas} == {1}


# --- split_wide_blocks() (Sprint PTC-S3 Task B, siehe docs/prompt_split_wide_blocks.md) ---
#
# Hintergrund: PyMuPDF liefert je nach Reihenfolge der Text-Zeigeoperationen im
# Content-Stream unterschiedliche Blockgrenzen für visuell identische mehrspaltige
# Bereiche (Fußzeilen, Adressblöcke) - schreibt der Formatierer zeilenweise über
# alle Spalten hinweg, verschmilzt PyMuPDF sie zu einem breiten Block mit einer
# "Zeile" pro Spalten-Zelle; schreibt er spaltenweise, bleiben es schmale
# Einzelblöcke. split_wide_blocks() gleicht das an, indem es breite Blöcke anhand
# der rawdict-Zeilengeometrie (x0-Anker) wieder in Spalten-Teilblöcke zerlegt.


def _write_row_major_columns_pdf(path: Path, rows: list, xs: list) -> None:
    """Schreibt Text zeilenweise über mehrere Spalten hinweg (row-major) - genau
    das Muster, das PyMuPDF zu einem breiten Mehrspalten-Block verschmilzt.
    rows: Liste von Zeilen, jede Zeile eine Liste von Zell-Texten (eine pro x in xs)."""
    c = canvas.Canvas(str(path))
    y = 700
    for row in rows:
        for x, text in zip(xs, row):
            c.drawString(x, y, text)
        y -= 15
    c.showPage()
    c.save()


def test_split_wide_blocks_schmale_bloecke_bleiben_unveraendert(tmp_path):
    """Schmale, klar getrennte Blöcke (<= _SPLIT_THRESHOLD_PT) haben keine
    Mehrspalten-Struktur, die aufgelöst werden müsste - split_wide_blocks()
    darf sie unverändert durchreichen."""
    pdf_path = tmp_path / "narrow.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(70, 700, "Column A")
    c.drawString(200, 650, "Column B")
    c.drawString(330, 600, "Column C")
    c.drawString(460, 550, "Column D")
    c.showPage()
    c.save()

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)

    assert len(blocks) == 4
    assert all(b[2] - b[0] <= 150 for b in blocks)  # alle deutlich unter der Schwelle

    result = split_wide_blocks(blocks, page)

    assert result == blocks
    doc.close()


def test_split_wide_blocks_breiter_block_wird_pro_spalte_aufgeteilt(tmp_path):
    """Zeilenweise über 3 Spalten geschriebener Text verschmilzt bei PyMuPDF zu
    einem einzigen breiten Block mit 9 Zeilen (3 Zeilen x 3 Spalten) - siehe
    Diagnose-Session. split_wide_blocks() muss ihn wieder in 3 spalten-reine
    Teilblöcke zerlegen, sortiert nach x0-Anker."""
    pdf_path = tmp_path / "wide_row_major.pdf"
    xs = [70, 200, 330]
    rows = [
        ["Col0Row0", "Col1Row0", "Col2Row0"],
        ["Col0Row1", "Col1Row1", "Col2Row1"],
        ["Col0Row2", "Col1Row2", "Col2Row2"],
    ]
    _write_row_major_columns_pdf(pdf_path, rows, xs)

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)

    # Vorbedingung (siehe Diagnose): PyMuPDF verschmilzt tatsächlich zu 1 Block.
    assert len(blocks) == 1
    assert blocks[0][2] - blocks[0][0] > 300

    result = split_wide_blocks(blocks, page)

    assert len(result) == 3
    result_sorted = sorted(result, key=lambda b: b[0])
    for sub_block, x in zip(result_sorted, xs):
        assert sub_block[0] == pytest.approx(x, abs=1)
        lines = [line for line in sub_block[4].split("\n") if line.strip()]
        assert lines == [f"Col{xs.index(x)}Row{r}" for r in range(3)]
    doc.close()


def test_split_wide_blocks_breiter_block_mit_einer_spalte_bleibt_unveraendert(tmp_path):
    """Eine breite Überschrift über mehrere Zeilen, aber mit durchgehend
    gleichem linken Rand, hat keine Mehrspalten-Struktur - hier darf
    split_wide_blocks() NICHT aufteilen, obwohl der Block > _SPLIT_THRESHOLD_PT
    breit ist."""
    pdf_path = tmp_path / "wide_single_group.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.setFont("Helvetica", 10)
    c.drawString(70, 700, "This is a wide heading spanning many points across the full page width now")
    c.drawString(70, 688, "Second line same left edge")
    c.drawString(70, 676, "Third line same left edge too")
    c.showPage()
    c.save()

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)

    assert len(blocks) == 1
    assert blocks[0][2] - blocks[0][0] > 300  # Vorbedingung: Block ist "breit"

    result = split_wide_blocks(blocks, page)

    assert result == blocks
    doc.close()


def test_split_wide_blocks_integration_ergibt_spaltenweise_lesereihenfolge(tmp_path):
    """Integrationstest über _extract_page_text_columns(): zeilenweise über 3
    Spalten geschriebener Text muss nach split_wide_blocks() + sort_blocks_columns()
    spaltenweise gelesen werden (alle Zeilen von Spalte 0, dann Spalte 1, dann
    Spalte 2) statt zeilenweise über die Spalten hinweg."""
    pdf_path = tmp_path / "wide_row_major_integration.pdf"
    xs = [70, 200, 330]
    rows = [
        ["Col0Row0", "Col1Row0", "Col2Row0"],
        ["Col0Row1", "Col1Row1", "Col2Row1"],
        ["Col0Row2", "Col1Row2", "Col2Row2"],
    ]
    _write_row_major_columns_pdf(pdf_path, rows, xs)

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    text, _ = _extract_page_text_columns(page)
    doc.close()

    pos_col0_last = text.index("Col0Row2")
    pos_col1_first = text.index("Col1Row0")
    pos_col1_last = text.index("Col1Row2")
    pos_col2_first = text.index("Col2Row0")

    # Spalte 0 vollständig vor Spalte 1, Spalte 1 vollständig vor Spalte 2.
    assert pos_col0_last < pos_col1_first
    assert pos_col1_last < pos_col2_first


def test_exclude_region_page_zero_and_page_from_combined(tmp_path):
    """Ein page=0-Region (Kopfbereich, wirkt auf allen Seiten) und ein
    page_from=2-Region (Fußbereich, wirkt ab Seite 2) müssen beide korrekt
    und unabhängig voneinander angewendet werden: der Kopf-Unterschied
    verschwindet überall, der Fuß-Unterschied nur ab Seite 2 - auf Seite 1
    bleibt der Fuß-Unterschied als Delta bestehen."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_multi_page_pdf(ref_path, [
        (f"Ref-Header Seite {n}", f"Ref-Footer Seite {n}") for n in range(1, 4)
    ])
    _write_multi_page_pdf(cnd_path, [
        (f"Cnd-Header Seite {n}", f"Cnd-Footer Seite {n}") for n in range(1, 4)
    ])

    profile = Profile(
        version="1.0",
        exclude_regions=[
            ExcludeRegion(page=0, **_MULTI_PAGE_HEADER_REGION),
            ExcludeRegion(page_from=2, **_MULTI_PAGE_FOOTER_REGION),
        ],
    )

    ref_pages, _, _ = extract_pages_for_profile(str(ref_path), profile, role="reference")
    cnd_pages, _, _ = extract_pages_for_profile(str(cnd_path), profile, role="candidate")

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert {delta.page for delta in result.deltas} == {1}


# --- separate_compare_region_blocks() (Sprint PTC-S3 Task C, siehe docs/prompt_table_regions.md) ---
#
# Fußregion fitz-Koordinaten x=0..300, y=700..800 (dasselbe Band wie
# _MULTI_PAGE_FOOTER_REGION oben) - drawString(30, 30) liegt bei Standard-
# Letter (792pt Höhe) bei fitz-y=762, innerhalb des Bandes. Eine zweite
# Fußregion darunter (y=800..900) für Tests mit mehreren compare_regions auf
# derselben Seite - unterschiedliche y-Bänder statt nur x-Versatz, damit
# PyMuPDF beide als eigene Blöcke erkennt (gleiche Zeile würde sie sonst zu
# einem einzigen breiten Block verschmelzen, siehe split_wide_blocks-Diagnose).
_COMPARE_REGION_LEFT = dict(x=0, y=700, width=300, height=100)
_COMPARE_REGION_RIGHT = dict(x=0, y=800, width=300, height=100)


def _write_footer_pdf(path: Path, footer_text: str, pages: int = 1, second_footer_text: str = None) -> None:
    """Erzeugt ein PDF mit Fließtext oben (außerhalb jeder Fußregion) und
    footer_text im Band _COMPARE_REGION_LEFT. second_footer_text (falls
    gesetzt) liegt im Band _COMPARE_REGION_RIGHT (eigene y-Zeile, siehe oben)."""
    c = canvas.Canvas(str(path))
    for _ in range(pages):
        c.drawString(30, 700, "Fliesstext im Hauptteil der Seite, unveraendert.")
        c.drawString(30, 70, footer_text)  # fitz-y ~ 722, innerhalb _COMPARE_REGION_LEFT
        if second_footer_text:
            c.drawString(30, 20, second_footer_text)  # fitz-y ~ 772, innerhalb _COMPARE_REGION_RIGHT
        c.showPage()
    c.save()


def test_separate_compare_region_blocks_trennt_blocke_bei_match(tmp_path):
    """Blöcke innerhalb einer zutreffenden compare_region mit passender
    condition werden abgetrennt - compare_region_texts enthält (whitespace-
    freier Text, lesbarer Text), remaining_blocks enthält sie nicht mehr."""
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company")

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)
    compare_regions = [CompareRegion(condition="ACME Insurance", page=1, **_COMPARE_REGION_LEFT)]

    remaining, compare_region_texts = separate_compare_region_blocks(blocks, 1, compare_regions)

    assert compare_region_texts == {0: ("ACMEInsuranceCompany", "ACME Insurance Company")}
    assert not any("ACME" in b[4] for b in remaining)
    assert len(remaining) == len(blocks) - 1
    doc.close()


def test_separate_compare_region_blocks_condition_matcht_nicht(tmp_path):
    """Trifft condition nicht zu, bleiben die Blöcke unverändert im
    normalen Vergleich - compare_region_texts bleibt für diese Region leer."""
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company")

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)
    compare_regions = [CompareRegion(condition="Nicht Vorhanden", page=1, **_COMPARE_REGION_LEFT)]

    remaining, compare_region_texts = separate_compare_region_blocks(blocks, 1, compare_regions)

    assert compare_region_texts == {}
    assert len(remaining) == len(blocks)
    assert any("ACME" in b[4] for b in remaining)
    doc.close()


def test_separate_compare_region_blocks_page_zero_wirkt_auf_jeder_seite(tmp_path):
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company", pages=2)

    doc = pymupdf.open(str(pdf_path))
    compare_regions = [CompareRegion(condition="ACME Insurance", page=0, **_COMPARE_REGION_LEFT)]

    for page_index in (0, 1):
        blocks = get_text_blocks(doc[page_index])
        _, compare_region_texts = separate_compare_region_blocks(blocks, page_index + 1, compare_regions)
        assert compare_region_texts == {0: ("ACMEInsuranceCompany", "ACME Insurance Company")}
    doc.close()


def test_separate_compare_region_blocks_page_from_wirkt_erst_ab_angegebener_seite(tmp_path):
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company", pages=2)

    doc = pymupdf.open(str(pdf_path))
    compare_regions = [CompareRegion(condition="ACME Insurance", page_from=2, **_COMPARE_REGION_LEFT)]

    blocks_page1 = get_text_blocks(doc[0])
    _, compare_region_texts_page1 = separate_compare_region_blocks(blocks_page1, 1, compare_regions)
    assert compare_region_texts_page1 == {}

    blocks_page2 = get_text_blocks(doc[1])
    _, compare_region_texts_page2 = separate_compare_region_blocks(blocks_page2, 2, compare_regions)
    assert compare_region_texts_page2 == {0: ("ACMEInsuranceCompany", "ACME Insurance Company")}
    doc.close()


def test_separate_compare_region_blocks_mehrere_regionen_unabhaengig_gematcht(tmp_path):
    """Zwei compare_regions auf derselben Seite werden unabhängig voneinander
    ausgewertet - beide matchen, beide werden abgetrennt."""
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company", second_footer_text="Contact Support Team")

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)
    compare_regions = [
        CompareRegion(condition="ACME Insurance", page=1, **_COMPARE_REGION_LEFT),
        CompareRegion(condition="Contact Support", page=1, **_COMPARE_REGION_RIGHT),
    ]

    remaining, compare_region_texts = separate_compare_region_blocks(blocks, 1, compare_regions)

    assert compare_region_texts == {
        0: ("ACMEInsuranceCompany", "ACME Insurance Company"),
        1: ("ContactSupportTeam", "Contact Support Team"),
    }
    assert not any("ACME" in b[4] or "Contact" in b[4] for b in remaining)
    doc.close()


def test_separate_compare_region_blocks_nach_exclude_region_kein_crash(tmp_path):
    """exclude_regions laufen VOR separate_compare_region_blocks (siehe
    Pipeline in _extract_page_text_columns) - überlappt eine exclude_region
    die compare_region vollständig, bleiben dort keine Blöcke mehr übrig;
    separate_compare_region_blocks darf dabei nicht abstürzen, findet aber
    naturgemäß keinen Match mehr."""
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company")

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    exclude_regions = [Region(page=1, x=0, y=700, w=300, h=100, page_from=None)]
    blocks_after_exclude = filter_blocks_by_regions(get_text_blocks(page), 1, exclude_regions)
    compare_regions = [CompareRegion(condition="ACME Insurance", page=1, **_COMPARE_REGION_LEFT)]

    remaining, compare_region_texts = separate_compare_region_blocks(blocks_after_exclude, 1, compare_regions)

    assert compare_region_texts == {}
    assert not any("ACME" in b[4] for b in remaining)  # bereits von exclude_regions entfernt
    doc.close()


def test_extract_page_text_columns_integriert_compare_regions(tmp_path):
    """Integrationstest: _extract_page_text_columns() entfernt matchende
    compare_region-Blöcke aus dem Seitentext und liefert deren normalisierten
    Text separat zurück."""
    pdf_path = tmp_path / "footer.pdf"
    _write_footer_pdf(pdf_path, "ACME Insurance Company")

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    compare_regions = [CompareRegion(condition="ACME Insurance", page=1, **_COMPARE_REGION_LEFT)]

    text, compare_region_texts = _extract_page_text_columns(page, 1, (), compare_regions)

    assert "ACME" not in text
    assert "Fliesstext" in text
    assert compare_region_texts == {0: ("ACMEInsuranceCompany", "ACME Insurance Company")}
    doc.close()


def test_separate_compare_region_blocks_condition_matcht_trotz_type3_fragmentierung(tmp_path):
    """Reproduziert das reale Diagnose-Muster (siehe
    docs/prompt_table_regions_whitespace_free.md): Type3-Schriften (Size=1.0)
    liefern über PyMuPDFs Leerzeichen-Heuristik Silbenfragmente mit falschen
    Zwischenräumen ("SV Spa r ka ssen Ver si ch eru n g" statt "SV
    SparkassenVersicherung"). Der Whitespace-freie condition-Abgleich muss
    trotzdem matchen, wo der alte "auf ein Leerzeichen kollabieren"-Abgleich
    fehlschlug.

    Fragmente mit 3pt Zwischenraum (empirisch geprüft, siehe Diagnose-
    Session): PyMuPDF fügt zwischen JEDES Fragment ein Leerzeichen ein,
    exakt das reale Bugmuster - bei zu kleinem Zwischenraum rekonstruiert
    PyMuPDFs eigene Heuristik das Wort bereits korrekt (keine Fragmentierung
    zum Testen)."""
    pdf_path = tmp_path / "fragmented_footer.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(30, 700, "Fliesstext im Hauptteil der Seite, unveraendert.")
    c.setFont("Helvetica", 10)
    x = 30
    y = 70  # fitz-y ~722, innerhalb _COMPARE_REGION_LEFT
    for frag in ["SV", "Spa", "r", "ka", "ssen", "Ver", "si", "ch", "eru", "n", "g"]:
        c.drawString(x, y, frag)
        x += c.stringWidth(frag, "Helvetica", 10) + 3
    c.showPage()
    c.save()

    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    blocks = get_text_blocks(page)

    # Vorbedingung: PyMuPDF liefert tatsächlich das fragmentierte Muster
    # (mit Leerzeichen zwischen jedem Fragment) - sonst testet dieser Test
    # nichts.
    footer_block = next(b for b in blocks if "Spa" in b[4])
    assert footer_block[4].strip() == "SV Spa r ka ssen Ver si ch eru n g"

    compare_regions = [CompareRegion(condition="SV SparkassenVersicherung", page=1, **_COMPARE_REGION_LEFT)]
    remaining, compare_region_texts = separate_compare_region_blocks(blocks, 1, compare_regions)

    assert 0 in compare_region_texts
    assert compare_region_texts[0] == ("SVSparkassenVersicherung", "SV Spa r ka ssen Ver si ch eru n g")
    assert not any("Spa" in b[4] for b in remaining)
    doc.close()
