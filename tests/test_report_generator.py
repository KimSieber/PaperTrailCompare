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
from pathlib import Path

import fitz

from engine.models import BatchResult, PairResult
from engine.pdf_extractor import extract_pages
from engine.profile_loader import Profile
from engine.report_generator import generate_batch_report, generate_report
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

    with fitz.open(str(ref_path)) as d:
        ref_page_count = len(d)
    with fitz.open(str(cnd_path)) as d:
        cnd_page_count = len(d)
    side_by_side_page_count = max(ref_page_count, cnd_page_count)

    report = fitz.open(str(output_path))
    # Seite 1: Zusammenfassung. Danach die Querformat-Vergleichsseiten,
    # zum Schluss die Delta-Detailliste (mind. 1 Seite, da has_delta=True).
    assert len(report) > 1 + side_by_side_page_count

    summary_text = report[0].get_text()
    assert "ref.pdf" in summary_text
    assert "cnd.pdf" in summary_text
    assert "Deltas gefunden" in summary_text

    ref_doc = fitz.open(str(ref_path))
    cnd_doc = fitz.open(str(cnd_path))
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

    with fitz.open(str(ref_path)) as d:
        ref_page_count = len(d)
    with fitz.open(str(cnd_path)) as d:
        cnd_page_count = len(d)
    side_by_side_page_count = max(ref_page_count, cnd_page_count)

    report = fitz.open(str(output_path))
    ref_doc = fitz.open(str(ref_path))

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

    report = fitz.open(str(output_path))
    ref_doc = fitz.open(str(ref_path))
    cnd_doc = fitz.open(str(cnd_path))
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
    pix = sbs_page.get_pixmap(matrix=fitz.Matrix(3, 3))
    for rect in (ref_number_rect, cnd_number_rect):
        cx, cy = int(rect.x0 * 3) + 1, int((rect.y0 + rect.height / 2) * 3)
        r, g, b = pix.pixel(cx, cy)
        # Gelb-Overlay (fill=(1,1,0), opacity 0.4) auf weißem Hintergrund
        # ergibt einen deutlich abgedunkelten Blaukanal.
        assert b < 200, f"Kein gelbes Delta-Overlay bei ({cx}, {cy}): RGB={r, g, b}"

    report.close()
    ref_doc.close()
    cnd_doc.close()


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

    with fitz.open(str(ref_path)) as d:
        ref_page_count = len(d)
    with fitz.open(str(cnd_path)) as d:
        cnd_page_count = len(d)
    side_by_side_page_count = max(ref_page_count, cnd_page_count)

    report = fitz.open(str(output_path))
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

    report = fitz.open(str(output_path))
    summary_text = report[0].get_text()
    report.close()

    assert "OCR verwendet\nJa" in summary_text


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

    report = fitz.open(str(output_path))
    text = "".join(page.get_text() for page in report)
    report.close()

    # Eine Zeile pro Paar: Dateiname, Delta-Anzahl, Status.
    assert "doc_01_ref.pdf" in text and "doc_01_cnd.pdf" in text
    assert "doc_02_ref.pdf" in text
    assert "doc_03_ref.pdf" in text
    assert "1" in text  # Delta-Anzahl von Paar 1
    assert "0" in text  # Delta-Anzahl von Paar 2
    assert "nicht gefunden" in text  # Fehlerstatus von Paar 3
