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

    report = fitz.open(str(output_path))
    summary_page_count = len(report) - ref_page_count - cnd_page_count
    assert summary_page_count >= 1

    summary_text = "".join(
        report[i].get_text() for i in range(summary_page_count)
    )
    assert "ref.pdf" in summary_text
    assert "cnd.pdf" in summary_text
    assert "Seite 1" in summary_text
    assert "Seite 2" in summary_text

    ref_start = summary_page_count
    cnd_start = summary_page_count + ref_page_count

    ref_annot_count = sum(
        len(list(report[i].annots() or [])) for i in range(ref_start, ref_start + ref_page_count)
    )
    cnd_annot_count = sum(
        len(list(report[i].annots() or [])) for i in range(cnd_start, cnd_start + cnd_page_count)
    )

    assert ref_annot_count == 3
    assert cnd_annot_count == 3

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

    report = fitz.open(str(output_path))
    summary_page_count = len(report) - ref_page_count - cnd_page_count
    ref_start = summary_page_count
    cnd_start = summary_page_count + ref_page_count

    # "100" steht im Referenz-Dokument auf Seite 2 (0-basiert: ref_start+1),
    # nicht auf der gemeldeten Delta-Seite 1 -> Fallback muss dort markieren.
    ref_page2_annots = list(report[ref_start + 1].annots() or [])
    assert len(ref_page2_annots) == 1
    ref_page1_annots = list(report[ref_start].annots() or [])
    assert len(ref_page1_annots) == 0

    cnd_page1_annots = list(report[cnd_start].annots() or [])
    assert len(cnd_page1_annots) == 1

    report.close()


def test_generate_report_ignoriert_leeren_text_und_seite_ausserhalb_dokument(tmp_path):
    """Deckt die Randfälle in _mark_deltas_in_document ab: ein Delta ohne
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

    report = fitz.open(str(output_path))
    summary_page_count = len(report) - ref_page_count - cnd_page_count
    summary_text = "".join(report[i].get_text() for i in range(summary_page_count))

    assert "Keine Unterschiede gefunden" in summary_text
    # Keine Delta-Tabelle wurde gerendert (Zeilen enthielten "Seite <n>").
    assert "Seite" not in summary_text

    total_annots = sum(len(list(page.annots() or [])) for page in report)
    assert total_annots == 0

    report.close()


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
