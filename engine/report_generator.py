"""Erzeugt Delta-markierte Einzel-Reports und Batch-Übersichts-Reports.

Primäres Format: PDF (Architekturentscheidung #4). Markierung der Delta-
Stellen im Referenz- und Kandidat-Dokument via PyMuPDF (Highlight-
Annotationen), Übersichtsseiten via ReportLab.
"""
from __future__ import annotations

import html
import io
from pathlib import Path
from typing import Dict, List, Optional, Union

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engine.models import BatchResult
from engine.profile_loader import Profile
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


_SBS_PAGE_W = 842.0
_SBS_PAGE_H = 595.0
_SBS_MARGIN_TOP = 30.0
_SBS_MARGIN_BOTTOM = 20.0
_SBS_MARGIN_LR = 20.0
_SBS_DIVIDER_X = _SBS_PAGE_W / 2  # 421
_SBS_HEADER_HEIGHT = 15.0
_SBS_FOOTER_HEIGHT = 15.0
_SBS_CONTENT_TOP = _SBS_MARGIN_TOP + _SBS_HEADER_HEIGHT
_SBS_CONTENT_BOTTOM = _SBS_PAGE_H - _SBS_MARGIN_BOTTOM - _SBS_FOOTER_HEIGHT
_SBS_RENDER_ZOOM = 2.0
_SBS_NO_PAGE_TEXT = "Keine entsprechende Seite"


def _insert_scaled_page_image(
    page: fitz.Page, doc: Optional[fitz.Document], src_page_num: Optional[int],
    x0: float, y0: float, x1: float, y1: float,
) -> None:
    """Rendert Seite src_page_num (1-basiert) aus doc als Pixmap (inkl.
    Highlight-Annotationen) und fügt sie proportional skaliert und zentriert
    in das Rechteck (x0, y0, x1, y1) ein. Fehlt die Seite, wird ein Hinweis
    eingeblendet (unterschiedliche Seitenzahlen durch Seitenumbruch)."""
    target = fitz.Rect(x0, y0, x1, y1)
    if doc is None or src_page_num is None or not (1 <= src_page_num <= len(doc)):
        page.insert_textbox(target, _SBS_NO_PAGE_TEXT, fontsize=10, align=1)
        return

    src_page = doc[src_page_num - 1]
    pixmap = src_page.get_pixmap(matrix=fitz.Matrix(_SBS_RENDER_ZOOM, _SBS_RENDER_ZOOM), annots=True)

    avail_w, avail_h = target.width, target.height
    scale = min(avail_w / pixmap.width, avail_h / pixmap.height)
    w, h = pixmap.width * scale, pixmap.height * scale
    rx0 = x0 + (avail_w - w) / 2
    ry0 = y0 + (avail_h - h) / 2
    page.insert_image(fitz.Rect(rx0, ry0, rx0 + w, ry0 + h), pixmap=pixmap)


def _build_side_by_side_document(
    ref_marked: fitz.Document, cnd_marked: fitz.Document,
) -> fitz.Document:
    """Erzeugt den Seite-für-Seite Nebeneinander-Vergleich in Querformat:
    links die Referenz-, rechts die Kandidat-Seite, jeweils inkl. der
    bereits gesetzten Delta-Highlight-Annotationen."""
    page_count = max(len(ref_marked), len(cnd_marked))
    out_doc = fitz.open()

    for i in range(page_count):
        page = out_doc.new_page(width=_SBS_PAGE_W, height=_SBS_PAGE_H)

        page.insert_textbox(
            fitz.Rect(_SBS_MARGIN_LR, _SBS_MARGIN_TOP, _SBS_DIVIDER_X - 1, _SBS_CONTENT_TOP),
            "Referenz", fontsize=8,
        )
        page.insert_textbox(
            fitz.Rect(_SBS_DIVIDER_X + 1, _SBS_MARGIN_TOP, _SBS_PAGE_W - _SBS_MARGIN_LR, _SBS_CONTENT_TOP),
            "Kandidat", fontsize=8,
        )
        page.draw_line(
            fitz.Point(_SBS_DIVIDER_X, _SBS_MARGIN_TOP),
            fitz.Point(_SBS_DIVIDER_X, _SBS_PAGE_H - _SBS_MARGIN_BOTTOM),
            width=1,
        )

        ref_page_num = i + 1 if i < len(ref_marked) else None
        cnd_page_num = i + 1 if i < len(cnd_marked) else None
        _insert_scaled_page_image(
            page, ref_marked, ref_page_num,
            _SBS_MARGIN_LR, _SBS_CONTENT_TOP, _SBS_DIVIDER_X - 1, _SBS_CONTENT_BOTTOM,
        )
        _insert_scaled_page_image(
            page, cnd_marked, cnd_page_num,
            _SBS_DIVIDER_X + 1, _SBS_CONTENT_TOP, _SBS_PAGE_W - _SBS_MARGIN_LR, _SBS_CONTENT_BOTTOM,
        )

        page.insert_textbox(
            fitz.Rect(0, _SBS_PAGE_H - _SBS_FOOTER_HEIGHT, _SBS_PAGE_W, _SBS_PAGE_H),
            f"Seite {i + 1} von {page_count}", fontsize=8, align=1,
        )

    return out_doc


def _generate_report_html(
    compare_result: CompareResult,
    ref_pdf_path: Path,
    cnd_pdf_path: Path,
    output_path: Path,
) -> Path:
    """Alternatives Report-Format (TC-R-004): reiner Textbericht ohne
    Delta-Markierung im Dokument selbst – HTML ist laut Architektur-
    entscheidung #4 die konfigurierbare Alternative zum PDF-Default."""
    if compare_result.has_delta:
        rows = "".join(
            f"<tr><td>{i}</td><td>Seite {d.page}</td>"
            f"<td>{html.escape(d.ref_text)}</td><td>{html.escape(d.cnd_text)}</td></tr>"
            for i, d in enumerate(compare_result.deltas, start=1)
        )
        body_html = (
            f"<p>Anzahl Deltas: {len(compare_result.deltas)}</p>"
            "<table border=\"1\" cellpadding=\"4\">"
            "<tr><th>#</th><th>Seite</th><th>Referenz</th><th>Kandidat</th></tr>"
            f"{rows}</table>"
        )
    else:
        body_html = "<p>Keine Unterschiede gefunden.</p>"

    content = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>PaperTrail Compare – Einzel-Report</title></head>
<body>
<h1>PaperTrail Compare – Einzel-Report</h1>
<p>Referenzdatei: {html.escape(ref_pdf_path.name)}</p>
<p>Kandidatdatei: {html.escape(cnd_pdf_path.name)}</p>
{body_html}
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def generate_report(
    compare_result: CompareResult,
    ref_pdf_path: Union[str, Path],
    cnd_pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    profile: Optional[Profile] = None,
) -> Path:
    """Erzeugt einen Einzel-Report (TC-R-001): Übersichtsseite (Hochformat)
    mit Datei- und Seitenangabe je Delta, gefolgt von einer Querformat-
    Seite pro Dokumentenseite mit Referenz (links) und Kandidat (rechts)
    nebeneinander, jeweils mit markierten Delta-Stellen.

    Die Delta.page-Angabe bezieht sich nur auf das Kandidat-Dokument (siehe
    text_comparator.Delta). Im Referenz-Dokument wird zuerst auf derselben
    Seitenzahl gesucht; bei unterschiedlichem Seitenumbruch zwischen
    Referenz und Kandidat (Kernprinzip des Vergleichs, siehe TC-T-003) und
    fehlendem Treffer wird über das gesamte Referenz-Dokument gesucht
    (TC-R-001-seitenumbruch).

    profile.report_format="html" erzeugt statt des PDF-Reports einen
    einfachen HTML-Bericht ohne Delta-Markierung im Dokument (TC-R-004) –
    PDF bleibt das primäre Format (Architekturentscheidung #4).
    """
    ref_pdf_path = Path(ref_pdf_path)
    cnd_pdf_path = Path(cnd_pdf_path)
    output_path = Path(output_path)

    if profile is not None and profile.report_format == "html":
        return _generate_report_html(compare_result, ref_pdf_path, cnd_pdf_path, output_path)

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

    side_by_side = _build_side_by_side_document(ref_marked, cnd_marked)
    report_doc.insert_pdf(side_by_side)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_doc.save(str(output_path))

    report_doc.close()
    side_by_side.close()
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
