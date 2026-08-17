# file:    tests/test_report_generator.py
# purpose: Integration tests TC-R-001 to TC-R-005 for engine.report_generator.
#          Covers delta marking, batch reports, no-delta reports, HTML format,
#          rotated pages, and edge cases.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Testfälle TC-R-001, TC-R-002 (P1) und TC-R-003, TC-R-004 (P2) für
engine.report_generator.

Integrationstest (Schicht 3, siehe CLAUDE.md) – kombiniert
text_comparator/pdf_extractor-Ergebnisse mit PyMuPDF (Markierung) und
ReportLab (Übersichtsseiten) zu einem PDF-Report.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 8.
Fixture: tests/fixtures/TC-R-001/{ref,cnd}.pdf (3 Deltas auf 2 Seiten),
tests/fixtures/TC-T-001/{ref,cnd}.pdf (identischer Text, kein Delta),
siehe tests/generate_fixtures.py::generate_tc_r_001 / generate_tc_t_001.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pymupdf
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

from engine.models import BatchResult, PairResult
from engine.pdf_extractor import extract_pages
from engine.profile_loader import ExcludeRegion, Profile
from engine.report_generator import _find_delta_rects, generate_batch_report, generate_report
from engine.text_comparator import CompareResult, Delta, compare

FIXTURES = Path(__file__).parent / "fixtures"


def test_tc_r_001_delta_markierung_im_einzel_report(tmp_path):
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    assert len(result.deltas) == 3

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path)

    assert output_path.is_file()

    with pymupdf.open(str(ref_path)) as d:
        ref_page_count = len(d)
    with pymupdf.open(str(cnd_path)) as d:
        cnd_page_count = len(d)
    side_by_side_page_count = max(ref_page_count, cnd_page_count)

    report = pymupdf.open(str(output_path))
    # Seite 1: Zusammenfassung. Danach die Querformat-Vergleichsseiten,
    # zum Schluss die Delta-Detailliste (mind. 1 Seite, da has_delta=True).
    assert len(report) > 1 + side_by_side_page_count

    summary_text = report[0].get_text()
    assert "ref.pdf" in summary_text
    assert "cnd.pdf" in summary_text
    assert "Deltas gefunden" in summary_text

    ref_doc = pymupdf.open(str(ref_path))
    cnd_doc = pymupdf.open(str(cnd_path))
    for i in range(1, 1 + side_by_side_page_count):
        page = report[i]
        assert page.rect.width > page.rect.height  # Querformat
        page_text = page.get_text()
        assert "Referenz" in page_text
        assert "Kandidat" in page_text
        assert f"Seite {i} von {side_by_side_page_count}" in page_text
        # Referenz- und Kandidat-Seite werden als Vektor-Inhalt eingebettet
        # (page.show_pdf_page), nicht mehr gerastert - der Text der
        # Originalseite muss unverändert extrahierbar sein, und es dürfen
        # keine Rasterbilder eingebettet sein (Performance-/Größen-Fix).
        assert ref_doc[i - 1].get_text().strip() in page_text
        assert cnd_doc[i - 1].get_text().strip() in page_text
        assert len(page.get_images()) == 0
    ref_doc.close()
    cnd_doc.close()

    detail_text = "".join(
        report[i].get_text() for i in range(1 + side_by_side_page_count, len(report))
    )
    assert "Seite 1" in detail_text
    assert "Seite 2" in detail_text

    report.close()


def test_tc_r_001_seitenumbruch_referenz_markierung_mit_fallback(tmp_path):
    """ref.pdf verteilt den Text auf 2 Seiten, cnd.pdf hat denselben Inhalt
    (mit Delta '100'->'200') auf nur 1 Seite. Delta.page bezieht sich auf
    die Kandidat-Seite (hier 1); '100' liegt im Referenz-Dokument aber auf
    Seite 2 – report_generator muss trotzdem markieren (Seiten-Fallback)."""
    ref_path = FIXTURES / "TC-R-001-seitenumbruch" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001-seitenumbruch" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    assert len(result.deltas) == 1
    delta = result.deltas[0]
    assert delta.page == 1  # Kandidat-Seite von "200"

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path)

    with pymupdf.open(str(ref_path)) as d:
        ref_page_count = len(d)
    with pymupdf.open(str(cnd_path)) as d:
        cnd_page_count = len(d)
    side_by_side_page_count = max(ref_page_count, cnd_page_count)

    report = pymupdf.open(str(output_path))
    ref_doc = pymupdf.open(str(ref_path))

    # Seite 1 ist die Zusammenfassung; danach folgen die Vergleichsseiten.
    # Markierung erfolgt vor dem Einbetten der Seiten (Fallback-Suche über
    # das gesamte Referenz-Dokument). ref.pdf hat 2 Seiten, cnd.pdf nur 1 -
    # die zweite Vergleichsseite zeigt daher nur die Referenz-Seite (als
    # Vektor-Inhalt, kein Rasterbild) plus den Hinweis "Keine entsprechende
    # Seite" für die fehlende Kandidatseite.
    first_page_text = report[1].get_text()
    assert ref_doc[0].get_text().strip() in first_page_text
    assert len(report[1].get_images()) == 0

    last_side_by_side_page = report[side_by_side_page_count]
    assert ref_doc[1].get_text().strip() in last_side_by_side_page.get_text()
    assert len(last_side_by_side_page.get_images()) == 0
    assert "Keine entsprechende Seite" in last_side_by_side_page.get_text()

    report.close()
    ref_doc.close()


def test_tc_r_005_rotierte_seite_wird_unverzerrt_eingebettet_und_delta_korrekt_positioniert(tmp_path):
    """Seite mit /Rotate 90 (z.B. quer eingescanntes Dokument) muss beim
    Vektor-Einbetten (show_pdf_page) unverzerrt erscheinen, und das
    Delta-Rechteck muss trotz Rotation exakt über dem geänderten Text
    liegen (siehe report_generator._place_source_page)."""
    ref_path = FIXTURES / "TC-R-005-rotation" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-005-rotation" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    assert len(result.deltas) == 1

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path)

    report = pymupdf.open(str(output_path))
    ref_doc = pymupdf.open(str(ref_path))
    cnd_doc = pymupdf.open(str(cnd_path))
    sbs_page = report[1]

    # Kein Rasterbild, Original-Text (inkl. Rotation) unverändert extrahierbar.
    assert len(sbs_page.get_images()) == 0
    assert ref_doc[0].get_text().strip() in sbs_page.get_text()
    assert cnd_doc[0].get_text().strip() in sbs_page.get_text()

    # Delta-Overlay (gelbes Füllrechteck) muss über der jeweiligen
    # geänderten Zahl liegen, nicht irgendwo abseits auf der Seite.
    ref_number_rect = sbs_page.search_for("100")[0]
    cnd_number_rect = sbs_page.search_for("200")[0]
    # Highlights werden als Vektor-Overlay (draw_rect), nicht als
    # Annotation gezeichnet - stattdessen über die Pixelfarbe verifizieren:
    # an einem Punkt innerhalb des jeweiligen Zahl-Rechtecks muss die
    # gelbe Overlay-Füllung sichtbar sein.
    pix = sbs_page.get_pixmap(matrix=pymupdf.Matrix(3, 3))
    for rect in (ref_number_rect, cnd_number_rect):
        cx, cy = int(rect.x0 * 3) + 1, int((rect.y0 + rect.height / 2) * 3)
        r, g, b = pix.pixel(cx, cy)
        # Gelb-Overlay (fill=(1,1,0), opacity 0.4) auf weißem Hintergrund
        # ergibt einen deutlich abgedunkelten Blaukanal.
        assert b < 200, f"Kein gelbes Delta-Overlay bei ({cx}, {cy}): RGB={r, g, b}"

    report.close()
    ref_doc.close()
    cnd_doc.close()


def _make_two_occurrence_pdf(path: Path) -> None:
    """Synthetisches Ein-Seiten-PDF (ReportLab, siehe CLAUDE.md Abschnitt 8 -
    ausschließlich synthetische Fixtures): derselbe kurze Text ("Stuttgart")
    kommt zweimal vor - einmal weit oben (fitz-Seitenkoordinate y≈100),
    einmal weit unten (y≈700). ReportLab zählt y von unten, fitz/PDF-
    Seitenkoordinaten (wie auch CompareRegion.y) von oben - daher
    page_h - y beim Zeichnen."""
    page_h = A4[1]
    c = rl_canvas.Canvas(str(path), pagesize=A4)
    c.drawString(50, page_h - 100, "Stuttgart")
    c.drawString(50, page_h - 700, "Stuttgart")
    c.showPage()
    c.save()


def test_find_delta_rects_region_clip_beschraenkt_suche_auf_region(tmp_path):
    """docs/prompt_region_clip_highlighting.md, Test 1: mit region_clip
    gesetzt darf _find_delta_rects den Text NUR innerhalb der Region finden
    - hier das obere Vorkommen (y≈100), nicht das untere (y≈700)."""
    pdf_path = tmp_path / "two_occurrences.pdf"
    _make_two_occurrence_pdf(pdf_path)
    doc = pymupdf.open(str(pdf_path))

    clip = pymupdf.Rect(0, 0, A4[0], 200)  # obere Region (y 0..200)
    texts_by_page = {1: [("Stuttgart", clip)]}

    rects_by_page = _find_delta_rects(doc, texts_by_page)

    assert list(rects_by_page.keys()) == [1]
    rects = rects_by_page[1]
    assert len(rects) == 1
    assert rects[0].y0 < 200  # obere Fundstelle, nicht die bei y≈700

    doc.close()


def test_find_delta_rects_ohne_region_clip_durchsucht_ganze_seite(tmp_path):
    """docs/prompt_region_clip_highlighting.md, Test 2: ohne region_clip
    (None) - Backwards-Kompatibilität für alle nicht-regionsbasierten
    Deltas - werden beide Vorkommen gefunden."""
    pdf_path = tmp_path / "two_occurrences.pdf"
    _make_two_occurrence_pdf(pdf_path)
    doc = pymupdf.open(str(pdf_path))

    texts_by_page = {1: [("Stuttgart", None)]}

    rects_by_page = _find_delta_rects(doc, texts_by_page)

    assert len(rects_by_page[1]) == 2

    doc.close()


def test_find_delta_rects_fallback_ignoriert_region_clip(tmp_path):
    """docs/prompt_region_clip_highlighting.md, Test 3: die Fallback-Suche
    (fallback_search_all_pages=True, für Referenz-Seiten bei abweichendem
    Seitenumbruch) darf den clip NICHT anwenden - genau dafür existiert der
    Fallback, um auf ANDEREN Seiten zu suchen, wo die Region-Koordinaten
    gar nicht gelten. Delta-Seite liegt hier außerhalb des Dokuments, mit
    region_clip gesetzt, das auf der einzigen echten Seite nur die obere
    Fundstelle einschließen würde - der clip-lose Fallback muss aber BEIDE
    Vorkommen finden."""
    pdf_path = tmp_path / "two_occurrences.pdf"
    _make_two_occurrence_pdf(pdf_path)
    doc = pymupdf.open(str(pdf_path))

    clip = pymupdf.Rect(0, 0, A4[0], 200)  # würde die untere Fundstelle ausschließen
    texts_by_page = {999: [("Stuttgart", clip)]}  # Seite außerhalb des Dokuments

    rects_by_page = _find_delta_rects(doc, texts_by_page, fallback_search_all_pages=True)

    assert list(rects_by_page.keys()) == [1]
    assert len(rects_by_page[1]) == 2  # Fallback ignoriert den clip

    doc.close()


# --- Region-Filter für sequenzielle (nicht-Region-)Deltas
# (docs/prompt_region_filter_highlights.md) ---

# fitz-Seitenkoordinaten (top-down, wie CompareRegion/ExcludeRegion.y) der
# drei "Stuttgart"-Vorkommen.
_RFH_BODY_XY = (250, 300)  # Fließtext, außerhalb jeder Region
_RFH_COMPARE_REGION_XY = (250, 750)  # innerhalb einer compare_region
_RFH_EXCLUDE_REGION_XY = (30, 500)  # innerhalb einer exclude_region


def _make_three_occurrence_pdf(path: Path) -> None:
    """Synthetisches Ein-Seiten-PDF (ReportLab): "Stuttgart" kommt DREIMAL
    vor - einmal im Fließtext (außerhalb jeder Region), einmal innerhalb
    einer definierten compare_region, einmal innerhalb einer definierten
    exclude_region. ReportLab zählt y von unten, fitz/PDF-Seitenkoordinaten
    (wie auch CompareRegion.y/ExcludeRegion.y) von oben - daher page_h - y
    beim Zeichnen (siehe auch _make_two_occurrence_pdf)."""
    page_h = A4[1]
    c = rl_canvas.Canvas(str(path), pagesize=A4)
    for x, y in (_RFH_BODY_XY, _RFH_COMPARE_REGION_XY, _RFH_EXCLUDE_REGION_XY):
        c.drawString(x, page_h - y, "Stuttgart")
    c.showPage()
    c.save()


_RFH_COMPARE_REGION_RECT = pymupdf.Rect(150, 700, 450, 800)
_RFH_EXCLUDE_REGION_RECT = pymupdf.Rect(0, 450, 150, 550)
# (page, page_from, rect) - siehe engine.report_generator._find_delta_rects.
_RFH_FILTER_REGIONS = [
    (1, None, _RFH_COMPARE_REGION_RECT),
    (1, None, _RFH_EXCLUDE_REGION_RECT),
]


def test_find_delta_rects_filtert_sequenzielle_treffer_in_regionen(tmp_path):
    """docs/prompt_region_filter_highlights.md, Test 1: ein sequenzieller
    Delta (kein region_clip) darf nur außerhalb aller exclude_regions/
    compare_regions markiert werden - hier bleibt nur das Fließtext-
    Vorkommen (y≈300) übrig."""
    pdf_path = tmp_path / "three_occurrences.pdf"
    _make_three_occurrence_pdf(pdf_path)
    doc = pymupdf.open(str(pdf_path))

    texts_by_page = {1: [("Stuttgart", None)]}

    rects_by_page = _find_delta_rects(doc, texts_by_page, filter_regions=_RFH_FILTER_REGIONS)

    assert list(rects_by_page.keys()) == [1]
    rects = rects_by_page[1]
    assert len(rects) == 1
    assert abs(rects[0].y0 - _RFH_BODY_XY[1]) < 20

    doc.close()


def test_find_delta_rects_region_delta_wird_nicht_gefiltert(tmp_path):
    """docs/prompt_region_filter_highlights.md, Test 2: ein Delta MIT
    region_clip darf vom Region-Filter nicht betroffen sein - der clip
    schränkt bereits ein, das Ergebnis bleibt das Vorkommen innerhalb der
    compare_region (y≈750), obwohl dieselbe Region auch in filter_regions
    steht."""
    pdf_path = tmp_path / "three_occurrences.pdf"
    _make_three_occurrence_pdf(pdf_path)
    doc = pymupdf.open(str(pdf_path))

    texts_by_page = {1: [("Stuttgart", _RFH_COMPARE_REGION_RECT)]}

    rects_by_page = _find_delta_rects(doc, texts_by_page, filter_regions=_RFH_FILTER_REGIONS)

    assert list(rects_by_page.keys()) == [1]
    rects = rects_by_page[1]
    assert len(rects) == 1
    assert abs(rects[0].y0 - _RFH_COMPARE_REGION_XY[1]) < 20

    doc.close()


def test_find_delta_rects_alle_treffer_in_regionen_liefert_leeres_ergebnis(tmp_path):
    """docs/prompt_region_filter_highlights.md, Test 3: fallen ALLE Treffer
    in Regionen, bleibt das Ergebnis leer - KEIN Fallback auf die
    ungefilterte Trefferliste."""
    pdf_path = tmp_path / "three_occurrences.pdf"
    _make_three_occurrence_pdf(pdf_path)
    doc = pymupdf.open(str(pdf_path))

    body_region_rect = pymupdf.Rect(200, 280, 400, 320)  # deckt auch das Fließtext-Vorkommen ab
    filter_regions = _RFH_FILTER_REGIONS + [(1, None, body_region_rect)]
    texts_by_page = {1: [("Stuttgart", None)]}

    rects_by_page = _find_delta_rects(doc, texts_by_page, filter_regions=filter_regions)

    assert rects_by_page == {}

    doc.close()


def test_generate_report_ignoriert_leeren_text_und_seite_ausserhalb_dokument(tmp_path):
    """Deckt die Randfälle in _find_delta_rects ab: ein Delta ohne
    Text (reine Einfügung/Löschung) und eine Delta-Seite außerhalb des
    Dokuments (Fallback-Suche findet dann ebenfalls nichts)."""
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    edge_result = CompareResult(has_delta=True, deltas=[
        Delta(page=1, position=0, ref_text="", cnd_text="Mustermann"),
        Delta(page=999, position=1, ref_text="Nichtvorhanden", cnd_text="Musterfrau"),
    ])

    output_path = tmp_path / "edge_report.pdf"
    generate_report(edge_result, ref_path, cnd_path, output_path)

    assert output_path.is_file()


def test_tc_r_003_detaillierter_report_kein_delta(tmp_path):
    """Vergleich ohne Delta: Report zeigt 'Keine Unterschiede gefunden' und
    enthält keine leere Delta-Tabelle/-Sektion, keine Markierungen."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    assert result.has_delta is False

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path)

    with pymupdf.open(str(ref_path)) as d:
        ref_page_count = len(d)
    with pymupdf.open(str(cnd_path)) as d:
        cnd_page_count = len(d)
    side_by_side_page_count = max(ref_page_count, cnd_page_count)

    report = pymupdf.open(str(output_path))
    # Kein Delta -> keine Detailliste am Ende, nur Zusammenfassung + Vergleichsseiten.
    assert len(report) == 1 + side_by_side_page_count
    summary_text = report[0].get_text()

    assert "Keine Unterschiede" in summary_text
    # Keine Delta-Tabellenzeilen (Format "Seite <n>") wurden gerendert; die
    # Kennzahlen-Kachel "Seiten" ist als Summenwert weiterhin vorhanden.
    assert "Seite 1" not in summary_text and "Seite 2" not in summary_text

    total_annots = sum(len(list(page.annots() or [])) for page in report)
    assert total_annots == 0

    report.close()


def test_ocr_verwendet_zeigt_tatsaechlichen_laufzeitwert_nicht_profil_flag(tmp_path):
    """OCR verwendet: Ja/Nein muss aus CompareResult.ocr_was_used kommen
    (tatsächlicher Laufzeitwert), nicht aus profile.ocr.enabled (Profil-
    Flag sagt nur, dass OCR erlaubt wäre - nicht, dass es gelaufen ist)."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)), ocr_used=True)
    profile = Profile(version="1.0")  # ocr.enabled bleibt False (Default)

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path, profile=profile)

    report = pymupdf.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert "OCR verwendet\nJa" in summary_text


def test_ausgeschlossene_regionen_zeigt_angewendet_ohne_warnungen(tmp_path):
    """Die Regionen-Tabelle im Summary muss die konfigurierte Region zeigen;
    ohne region_warnings darf kein Warnhinweis erscheinen (siehe Block 3:
    detaillierte Auflistung statt reinem Zähler)."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    profile = Profile(version="1.0", exclude_regions=[ExcludeRegion(page=1, x=0, y=0, width=10, height=10)])

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path, profile=profile, region_warnings=[])

    report = pymupdf.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert "Ausgeschlossene Regionen" in summary_text
    assert "Seite 1" in summary_text
    assert "Tabellenerkennung" not in summary_text


def test_ausgeschlossene_regionen_zeigt_warnung_bei_nicht_vollstaendiger_anwendung(tmp_path):
    """Mit region_warnings (z.B. Tabellenseite, siehe
    pdf_extractor._warn_if_table_page_has_regions) muss der Report den
    tatsächlichen Warnhinweis unter der Regionen-Tabelle anzeigen."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    profile = Profile(version="1.0", exclude_regions=[ExcludeRegion(page=1, x=0, y=0, width=10, height=10)])
    warning_text = "Seite 1: Ausschluss-Region(en) konnten wegen Tabellenerkennung nicht angewendet werden."

    output_path = tmp_path / "report.pdf"
    generate_report(
        result, ref_path, cnd_path, output_path, profile=profile,
        region_warnings=[warning_text],
    )

    report = pymupdf.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert warning_text in summary_text


def test_summary_page_shows_profile_settings(tmp_path):
    """Profil-Einstellungen-Sektion muss abweichende (nicht-default) Werte
    aus dem Profil anzeigen, nicht nur einen Profilnamen (siehe Block 3)."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    profile = Profile(
        version="1.0",
        case_sensitive=False,
        compare_mode="hybrid",
        normalize_whitespace=True,
    )

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path, profile=profile)

    report = pymupdf.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert "Profil-Einstellungen" in summary_text
    assert "Vergleichsmodus\nhybrid" in summary_text
    assert "Groß-/Kleinschreibung\nNein" in summary_text
    assert "Leerzeichen-Toleranz\nJa" in summary_text
    assert "Textextraktion\nnative" in summary_text


def test_summary_page_shows_exclude_regions_detail(tmp_path):
    """Die Regionen-Tabelle muss die Seitenbereichs-Anzeige für alle drei
    Varianten korrekt darstellen: konkrete Seite, "Alle Seiten" (page=0)
    und "Ab Seite N" (page_from)."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    profile = Profile(
        version="1.0",
        exclude_regions=[
            ExcludeRegion(page=1, x=0, y=0, width=10, height=10),
            ExcludeRegion(page=0, x=0, y=0, width=20, height=20),
            ExcludeRegion(page_from=2, x=0, y=0, width=30, height=30),
        ],
    )

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path, profile=profile)

    report = pymupdf.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert "Seite 1" in summary_text
    assert "Alle Seiten" in summary_text
    assert "Ab Seite 2" in summary_text


def test_summary_page_without_profile_shows_defaults(tmp_path):
    """Ohne Profil müssen die tatsächlich geltenden Engine-Defaults gezeigt
    werden (siehe engine.__main__: case_sensitive=True,
    normalize_whitespace=False, compare_mode="words"), nicht nur ein
    leerer Profil-Platzhalter."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))

    output_path = tmp_path / "report.pdf"
    generate_report(result, ref_path, cnd_path, output_path)

    report = pymupdf.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert "Profil-Einstellungen" in summary_text
    assert "Vergleichsmodus\nwords" in summary_text
    assert "Groß-/Kleinschreibung\nJa" in summary_text
    assert "Leerzeichen-Toleranz\nNein" in summary_text
    assert "Textextraktion\nnative" in summary_text
    assert "Ausgeschlossene Regionen" not in summary_text


def test_tc_r_004_report_format_konfigurierbar_html(tmp_path):
    """Profil mit report_format='html' -> HTML-Datei statt PDF, mit Datei-
    und Delta-Angaben."""
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    assert result.has_delta is True

    profile = Profile(version="1.0", report_format="html")
    output_path = tmp_path / "report.html"

    returned_path = generate_report(result, ref_path, cnd_path, output_path, profile=profile)

    assert returned_path == output_path
    assert output_path.is_file()

    content = output_path.read_text(encoding="utf-8")
    assert "<html" in content.lower()
    assert "ref.pdf" in content
    assert "cnd.pdf" in content
    assert "Mustermann" in content
    assert "Musterfrau" in content

    # Es wurde kein (marker-fähiges) PDF erzeugt.
    with open(output_path, "rb") as f:
        assert not f.read(5).startswith(b"%PDF")


def test_generate_report_html_ohne_delta(tmp_path):
    """HTML-Report ohne Delta zeigt ebenfalls 'Keine Unterschiede gefunden'
    statt einer leeren Delta-Tabelle."""
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    result = compare(extract_pages(str(ref_path)), extract_pages(str(cnd_path)))
    assert result.has_delta is False

    profile = Profile(version="1.0", report_format="html")
    output_path = tmp_path / "report.html"
    generate_report(result, ref_path, cnd_path, output_path, profile=profile)

    content = output_path.read_text(encoding="utf-8")
    assert "Keine Unterschiede gefunden" in content
    assert "<table" not in content


def test_tc_r_002_batch_report_uebersicht_aller_vergleiche(tmp_path):
    ok_delta_result = CompareResult(
        has_delta=True,
        deltas=[Delta(page=1, position=0, ref_text="A", cnd_text="B")],
    )
    ok_no_delta_result = CompareResult(has_delta=False, deltas=[])

    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path="pairs/doc_01_ref.pdf", cnd_path="pairs/doc_01_cnd.pdf",
            status="ok", compare_result=ok_delta_result,
        ),
        PairResult(
            ref_path="pairs/doc_02_ref.pdf", cnd_path="pairs/doc_02_cnd.pdf",
            status="ok", compare_result=ok_no_delta_result,
        ),
        PairResult(
            ref_path="pairs/doc_03_ref.pdf", cnd_path="pairs/doc_03_cnd.pdf",
            status="error", error="Datei(en) nicht gefunden: doc_03_cnd.pdf",
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(batch_result, output_path)

    assert output_path.is_file()

    report = pymupdf.open(str(output_path))
    text = "".join(page.get_text() for page in report)
    report.close()

    # Eine Zeile pro Paar: Dateiname, Delta-Anzahl, Status.
    assert "doc_01_ref.pdf" in text and "doc_01_cnd.pdf" in text
    assert "doc_02_ref.pdf" in text
    assert "doc_03_ref.pdf" in text
    assert "1" in text  # Delta-Anzahl von Paar 1
    assert "0" in text  # Delta-Anzahl von Paar 2
    assert "nicht gefunden" in text  # Fehlerstatus von Paar 3


def test_tc_r_002_batch_report_kennzahlen_kacheln_erfolgsquote_und_seiten_gesamt(tmp_path):
    """Punkt 4 (prompt_batch_fixes.md): Kennzahlen-Kacheln im Kopfbereich
    zeigen u.a. Erfolgsquote in % und Gesamtzahl verarbeiteter Seiten."""
    ok_result = CompareResult(has_delta=False, deltas=[])
    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path="pairs/doc_01_ref.pdf", cnd_path="pairs/doc_01_cnd.pdf",
            status="ok", compare_result=ok_result, total_pages=2,
        ),
        PairResult(
            ref_path="pairs/doc_02_ref.pdf", cnd_path="pairs/doc_02_cnd.pdf",
            status="ok", compare_result=ok_result, total_pages=3,
        ),
        PairResult(
            ref_path="pairs/doc_03_ref.pdf", cnd_path="pairs/doc_03_cnd.pdf",
            status="ok", compare_result=ok_result, total_pages=1,
        ),
        PairResult(
            ref_path="pairs/doc_04_ref.pdf", cnd_path="pairs/doc_04_cnd.pdf",
            status="error", error="Datei(en) nicht gefunden: doc_04_cnd.pdf",
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(batch_result, output_path, duration_seconds=5.0)

    report = pymupdf.open(str(output_path))
    text = report[0].get_text()
    report.close()

    assert "4" in text  # Dateipaare gesamt
    assert "3" in text  # Erfolgreich
    assert "75 %" in text  # Erfolgsquote (3 von 4)
    assert "6" in text  # Seiten gesamt (2+3+1)
    assert "5.0 s" in text or "5,0 s" in text  # Laufzeit


def test_tc_r_002_batch_report_zeigt_verwendetes_profil(tmp_path):
    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path="pairs/doc_01_ref.pdf", cnd_path="pairs/doc_01_cnd.pdf",
            status="ok", compare_result=CompareResult(has_delta=False, deltas=[]), total_pages=1,
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(
        batch_result, output_path,
        profile=Profile(version="2.0"), profile_path="mein_profil.json",
    )

    report = pymupdf.open(str(output_path))
    text = report[0].get_text()
    report.close()

    assert "mein_profil.json" in text
    assert "2.0" in text


def test_tc_r_002_batch_report_fehlerpaar_zeigt_fehlertext_statt_zahlenwerten(tmp_path):
    """Punkt 4: Fehlerpaare werden nur in der Haupttabelle markiert (Fehler-
    hinweis statt Delta-Anzahl/Übereinstimmung), keine eigene Fehlersektion."""
    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path="pairs/doc_01_ref.pdf", cnd_path="pairs/doc_01_cnd.pdf",
            status="error", error="Datei(en) nicht gefunden: doc_01_cnd.pdf",
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(batch_result, output_path)

    report = pymupdf.open(str(output_path))
    text = "".join(page.get_text() for page in report)
    report.close()

    assert "nicht gefunden" in text
    assert "Fehlerliste" not in text
    assert "Fehlerdetails" not in text


def test_tc_r_002_batch_report_lange_dateinamen_bleiben_im_satzspiegel(tmp_path):
    """Punkt 3 (prompt_batch_fixes.md): sehr lange Dateinamen werden in der
    Haupttabelle umgebrochen statt über den rechten Satzspiegel-Rand
    hinauszulaufen (Satzspiegel: A4 abzüglich 20mm Rand je Seite, wie beim
    Einzel-Report)."""
    long_name = "sehr_" * 20 + "langer_dateiname_aus_altem_drucksystem.pdf"
    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path=f"pairs/{long_name}", cnd_path=f"pairs/{long_name}",
            status="ok", compare_result=CompareResult(has_delta=False, deltas=[]),
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(batch_result, output_path)

    report = pymupdf.open(str(output_path))
    right_edge = report[0].rect.width - 20 * mm
    for page in report:
        for x0, y0, x1, y1, *_ in page.get_text("words"):
            assert x1 <= right_edge + 1, f"Wort ragt über den Satzspiegel hinaus: x1={x1}"
    report.close()


def test_tc_r_002_batch_report_wiederholt_tabellenkopf_auf_folgeseiten(tmp_path):
    """Punkt 3: Tabellenkopf (Spaltenüberschriften) wird bei mehrseitigen
    Batch-Reports auf jeder Folgeseite wiederholt."""
    pairs = [
        PairResult(
            ref_path=f"pairs/doc_{i:03d}_ref.pdf", cnd_path=f"pairs/doc_{i:03d}_cnd.pdf",
            status="ok", compare_result=CompareResult(has_delta=False, deltas=[]),
        )
        for i in range(1, 61)
    ]
    batch_result = BatchResult(pairs=pairs)

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(batch_result, output_path)

    report = pymupdf.open(str(output_path))
    assert len(report) > 1
    for page in report:
        assert "Referenz" in page.get_text()
        assert "Kandidat" in page.get_text()
    report.close()


def test_tc_r_002_batch_report_kopfbereich_dokumentanzahl_laufzeit_zeitpunkt(tmp_path):
    """Kopfbereich des Batch-Reports zeigt Gesamtanzahl Dokumente, Laufzeit
    und den Startzeitpunkt als Subtitle-Zeile (Sprint PTC-2, Task C2: der
    Zeitpunkt wandert von der KPI-Kachel in eine Subtitle-Zeile mit
    Sekundengenauigkeit, siehe prompt_batch_verarbeitung.md)."""
    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path="pairs/doc_01_ref.pdf", cnd_path="pairs/doc_01_cnd.pdf",
            status="ok", compare_result=CompareResult(has_delta=False, deltas=[]),
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    before = datetime.now()
    generate_batch_report(batch_result, output_path, duration_seconds=12.5)
    after = datetime.now()

    report = pymupdf.open(str(output_path))
    text = "".join(page.get_text() for page in report)
    report.close()

    assert "1" in text  # Gesamtanzahl Dokumente/Paare
    assert "12.5" in text or "12,5" in text  # Laufzeit

    match = re.search(r"Batch-Lauf vom (\d{2}\.\d{2}\.\d{4}), (\d{2}:\d{2}:\d{2}) Uhr", text)
    assert match is not None, f"Subtitle-Zeitstempel nicht gefunden in: {text!r}"
    subtitle_dt = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%d.%m.%Y %H:%M:%S")
    assert before.replace(microsecond=0) <= subtitle_dt <= after.replace(microsecond=0) + timedelta(seconds=1)


def test_batch_report_summe_deltas_kachel_ersetzt_zeitpunkt_kachel(tmp_path):
    """Task C1: Die "Zeitpunkt"-Kachel entfällt zugunsten von "Summe Deltas"
    - Summe aller Deltas über alle status="ok"-Paare hinweg, damit beim
    Profil-Feintuning per Batch-Lauf auf einen Blick erkennbar ist, ob ein
    erneuter Lauf das Ergebnis verbessert oder verschlechtert hat."""
    batch_result = BatchResult(pairs=[
        PairResult(
            ref_path="pairs/doc_01_ref.pdf", cnd_path="pairs/doc_01_cnd.pdf",
            status="ok", compare_result=CompareResult(
                has_delta=True,
                deltas=[Delta(page=1, position=0, ref_text="A", cnd_text="B")] * 3,
            ),
        ),
        PairResult(
            ref_path="pairs/doc_02_ref.pdf", cnd_path="pairs/doc_02_cnd.pdf",
            status="ok", compare_result=CompareResult(
                has_delta=True,
                deltas=[Delta(page=1, position=0, ref_text="C", cnd_text="D")] * 2,
            ),
        ),
        PairResult(
            ref_path="pairs/doc_03_ref.pdf", cnd_path="pairs/doc_03_cnd.pdf",
            status="error", error="Datei nicht gefunden",
        ),
    ])

    output_path = tmp_path / "batch_report.pdf"
    generate_batch_report(batch_result, output_path, duration_seconds=1.0)

    report = pymupdf.open(str(output_path))
    text = "".join(page.get_text() for page in report)
    report.close()

    assert "Summe Deltas" in text
    assert "Zeitpunkt" not in text
    lines = text.splitlines()
    label_idx = lines.index("Summe Deltas")
    assert lines[label_idx + 1].strip() == "5"
