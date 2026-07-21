"""Erzeugt Delta-markierte Einzel-Reports und Batch-Übersichts-Reports.

Primäres Format: PDF (Architekturentscheidung #4). Markierung der Delta-
Stellen im Referenz- und Kandidat-Dokument via PyMuPDF (Highlight-
Annotationen), Übersichtsseiten via ReportLab.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Union

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engine.batch_processor import BatchResult
from engine.text_comparator import CompareResult

_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("report_title", parent=_STYLES["Heading1"])
_BODY_STYLE = _STYLES["Normal"]

_TABLE_STYLE = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
])


def _build_summary_pdf_bytes(
    title: str, intro_lines: List[str], table_data: List[List[str]]
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story = [Paragraph(title, _TITLE_STYLE), Spacer(1, 8)]
    for line in intro_lines:
        story.append(Paragraph(line, _BODY_STYLE))
    if table_data:
        story.append(Spacer(1, 10))
        table = Table(table_data, hAlign="LEFT")
        table.setStyle(_TABLE_STYLE)
        story.append(table)
    doc.build(story)
    return buf.getvalue()


def _mark_deltas_in_document(
    pdf_path: Union[str, Path],
    texts_by_page: Dict[int, List[str]],
    fallback_search_all_pages: bool = False,
) -> fitz.Document:
    """Öffnet ein PDF und markiert (Highlight-Annotation) die übergebenen
    Textstellen je Seite. texts_by_page: {Seite (1-basiert): [Text, ...]}.

    Findet sich der Text nicht auf der erwarteten Seite (z.B. weil
    Referenz- und Kandidat-Dokument unterschiedlich umgebrochen sind – die
    von text_comparator gemeldete Delta-Seite bezieht sich nur auf das
    Kandidat-Dokument), wird mit fallback_search_all_pages=True über das
    gesamte Dokument gesucht, statt die Markierung zu verwerfen.
    """
    doc = fitz.open(str(pdf_path))
    for page_num, texts in texts_by_page.items():
        for text in texts:
            if not text:
                continue

            rects = []
            if 1 <= page_num <= len(doc):
                rects = doc[page_num - 1].search_for(text)
                for rect in rects:
                    doc[page_num - 1].add_highlight_annot(rect)

            if not rects and fallback_search_all_pages:
                for page in doc:
                    fallback_rects = page.search_for(text)
                    if fallback_rects:
                        for rect in fallback_rects:
                            page.add_highlight_annot(rect)
                        break
    return doc


def generate_report(
    compare_result: CompareResult,
    ref_pdf_path: Union[str, Path],
    cnd_pdf_path: Union[str, Path],
    output_path: Union[str, Path],
) -> Path:
    """Erzeugt einen Einzel-Report (TC-R-001): Übersichtsseite mit Datei-
    und Seitenangabe je Delta, gefolgt vom Referenz- und Kandidat-Dokument
    mit markierten Delta-Stellen.

    Die Delta.page-Angabe bezieht sich nur auf das Kandidat-Dokument (siehe
    text_comparator.Delta). Im Referenz-Dokument wird zuerst auf derselben
    Seitenzahl gesucht; bei unterschiedlichem Seitenumbruch zwischen
    Referenz und Kandidat (Kernprinzip des Vergleichs, siehe TC-T-003) und
    fehlendem Treffer wird über das gesamte Referenz-Dokument gesucht
    (TC-R-001-seitenumbruch).
    """
    ref_pdf_path = Path(ref_pdf_path)
    cnd_pdf_path = Path(cnd_pdf_path)
    output_path = Path(output_path)

    ref_texts_by_page: Dict[int, List[str]] = {}
    cnd_texts_by_page: Dict[int, List[str]] = {}
    table_rows = [["#", "Seite", "Referenz", "Kandidat"]]
    for i, delta in enumerate(compare_result.deltas, start=1):
        ref_texts_by_page.setdefault(delta.page, []).append(delta.ref_text)
        cnd_texts_by_page.setdefault(delta.page, []).append(delta.cnd_text)
        table_rows.append([str(i), f"Seite {delta.page}", delta.ref_text, delta.cnd_text])

    intro = [
        f"Referenzdatei: {ref_pdf_path.name}",
        f"Kandidatdatei: {cnd_pdf_path.name}",
        f"Anzahl Deltas: {len(compare_result.deltas)}"
        if compare_result.has_delta else "Keine Unterschiede gefunden.",
    ]

    summary_bytes = _build_summary_pdf_bytes(
        "PaperTrail Compare – Einzel-Report",
        intro,
        table_rows if compare_result.has_delta else [],
    )

    report_doc = fitz.open(stream=summary_bytes, filetype="pdf")
    ref_marked = _mark_deltas_in_document(
        ref_pdf_path, ref_texts_by_page, fallback_search_all_pages=True
    )
    cnd_marked = _mark_deltas_in_document(cnd_pdf_path, cnd_texts_by_page)

    report_doc.insert_pdf(ref_marked)
    report_doc.insert_pdf(cnd_marked)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_doc.save(str(output_path))

    report_doc.close()
    ref_marked.close()
    cnd_marked.close()

    return output_path


def generate_batch_report(
    batch_result: BatchResult, output_path: Union[str, Path]
) -> Path:
    """Erzeugt eine Batch-Übersicht (TC-R-002): eine Zeile pro Dateipaar
    mit Dateiname, Delta-Anzahl und Status."""
    output_path = Path(output_path)

    table_rows = [["Referenz", "Kandidat", "Deltas", "Status"]]
    for pair in batch_result.pairs:
        ref_name = Path(pair.ref_path).name
        cnd_name = Path(pair.cnd_path).name
        if pair.status == "ok":
            delta_count = str(len(pair.compare_result.deltas)) if pair.compare_result else "0"
            status_text = "OK"
        else:
            delta_count = "-"
            status_text = f"Fehler: {pair.error}"
        table_rows.append([ref_name, cnd_name, delta_count, status_text])

    intro = [
        f"Anzahl verarbeiteter Paare: {len(batch_result.pairs)}",
        f"Erfolgreich: {batch_result.ok_count}",
        f"Fehler: {batch_result.error_count}",
    ]

    summary_bytes = _build_summary_pdf_bytes(
        "PaperTrail Compare – Batch-Report", intro, table_rows
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(summary_bytes)

    return output_path
