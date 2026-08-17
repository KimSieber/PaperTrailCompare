# file:    engine/report_generator.py
# purpose: Generates single-comparison and batch PDF/HTML reports with
#          delta highlighting, side-by-side page views, KPI tiles, and
#          detail tables. Uses PyMuPDF for marking and ReportLab for layout.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Erzeugt Delta-markierte Einzel-Reports und Batch-Übersichts-Reports.

Primäres Format: PDF (Architekturentscheidung #4). Markierung der Delta-
Stellen im Referenz- und Kandidat-Dokument via PyMuPDF (Highlight-
Annotationen), Übersichtsseiten via ReportLab.
"""
from __future__ import annotations

import html
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pymupdf
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engine import __version__
from engine.models import BatchResult, PairResult
from engine.profile_loader import ExcludeRegion, OcrConfig, Profile
from engine.text_comparator import CompareResult

_ASSETS_DIR = Path(__file__).parent / "assets"
_REPORT_ICON_PATH = _ASSETS_DIR / "512x512.png"
_REPORT_ICON_HEIGHT_MM = 19.0

_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("report_title", parent=_STYLES["Heading1"])
_SUBTITLE_STYLE = ParagraphStyle(
    "report_subtitle", parent=_STYLES["Normal"], textColor=colors.HexColor("#666666")
)
_BODY_STYLE = _STYLES["Normal"]
_CELL_STYLE = ParagraphStyle("report_cell", parent=_STYLES["Normal"], fontSize=9, leading=11)
_DETAIL_CELL_STYLE = ParagraphStyle("report_detail_cell", parent=_STYLES["Normal"], fontSize=7, leading=9)
# Eigene Header-Varianten mit explizitem textColor=white: ReportLab-Paragraph-
# Objekte überschreiben TEXTCOLOR aus TableStyle, daher reicht TEXTCOLOR=white
# in _TABLE_STYLE/_DETAIL_TABLE_STYLE allein nicht (Sprint PTC-2, Task B).
_HEADER_CELL_STYLE = ParagraphStyle(
    "report_header_cell", parent=_CELL_STYLE, textColor=colors.white, fontName="Helvetica-Bold"
)
_DETAIL_HEADER_CELL_STYLE = ParagraphStyle(
    "report_detail_header_cell", parent=_DETAIL_CELL_STYLE, textColor=colors.white, fontName="Helvetica-Bold"
)
_TILE_LABEL_STYLE = ParagraphStyle(
    "report_tile_label", parent=_STYLES["Normal"], fontSize=7, textColor=colors.HexColor("#666666")
)
_TILE_VALUE_STYLE = ParagraphStyle(
    "report_tile_value", parent=_STYLES["Normal"], fontSize=16, leading=19, fontName="Helvetica-Bold"
)

_TABLE_STYLE = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
])

_DETAIL_TABLE_COL_WIDTHS = [10 * mm, 20 * mm, 75 * mm, 75 * mm]
_DETAIL_TABLE_STYLE = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
])

_COLOR_OK = colors.HexColor("#2E7D32")
_COLOR_DELTA = colors.HexColor("#C62828")
_COLOR_BADGE_OK_BG = colors.HexColor("#E8F5E9")
_COLOR_BADGE_DELTA_BG = colors.HexColor("#FDECEA")
_COLOR_HAIRLINE = colors.HexColor("#CCCCCC")

_COLOR_TILE_NEUTRAL = colors.HexColor("#888780")
_COLOR_TILE_GREEN = colors.HexColor("#1D9E75")
_COLOR_TILE_ORANGE = colors.HexColor("#D85A30")
_COLOR_TILE_VALUE_GREEN = colors.HexColor("#0F6E56")
_COLOR_TILE_VALUE_ORANGE = colors.HexColor("#993C1D")
_TILE_BORDER = colors.HexColor("#DDDDDD")
_TILE_ACCENT_HEIGHT = 3.5
_TILE_CORNER_RADIUS = 4


def _build_kpi_tile(
    label: str, value: str, accent_color, value_color=colors.black, value_font_size: int = 16
) -> Table:
    """Baut eine einzelne Kennzahlen-Kachel: farbiger Akzentstreifen oben,
    heller Hintergrund, dünner Rahmen, Label klein/grau + Wert groß/fett.

    value_font_size kleiner als der Default erlaubt eine kleinere Schrift
    mit zweizeiligem Umbruch (größere Wertzeile) für textlastige Werte wie
    einen Profil-Dateinamen, die in der Standardgröße nicht in die schmale
    Kachelbreite passen würden (Punkt 4, prompt_batch_fixes.md)."""
    value_style = ParagraphStyle(
        f"tile_value_{id(value_color)}_{value_font_size}", parent=_TILE_VALUE_STYLE,
        textColor=value_color, fontSize=value_font_size, leading=value_font_size + 3,
    )
    value_row_height = 20 if value_font_size >= 14 else 26
    tile = Table(
        [[""], [Paragraph(label, _TILE_LABEL_STYLE)], [Paragraph(value, value_style)]],
        colWidths=[40 * mm],
        rowHeights=[_TILE_ACCENT_HEIGHT, 12, value_row_height],
        cornerRadii=[_TILE_CORNER_RADIUS] * 4,
    )
    tile.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), accent_color),
        ("BACKGROUND", (0, 1), (0, -1), colors.white),
        ("BOX", (0, 0), (0, -1), 0.5, _TILE_BORDER),
        ("LEFTPADDING", (0, 1), (0, -1), 6),
        ("RIGHTPADDING", (0, 1), (0, -1), 6),
        ("TOPPADDING", (0, 1), (0, 1), 6),
        ("BOTTOMPADDING", (0, 1), (0, 1), 2),
        ("TOPPADDING", (0, 2), (0, 2), 0),
        ("BOTTOMPADDING", (0, 2), (0, 2), 6),
        ("TOPPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tile


_TILE_ROW_STYLE = TableStyle([
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ("TOPPADDING", (0, 0), (-1, -1), 0),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (-1, 0), (-1, 0), 0),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
])


def _build_kpi_tile_row(tiles: List[Table]) -> Table:
    """Reiht bis zu 4 Kennzahlen-Kacheln (siehe _build_kpi_tile) gleich
    breit über die volle Satzspiegelbreite (170mm) auf - gemeinsam genutzt
    von Einzel- und Batch-Report-Kopfbereich."""
    tile_width = 170.0 / len(tiles) * mm
    tile_table = Table([tiles], colWidths=[tile_width] * len(tiles))
    tile_table.setStyle(_TILE_ROW_STYLE)
    return tile_table


def _build_report_header_table(title_html: str, badge_text: str, badge_fg, badge_bg) -> Table:
    """Baut die Kopfzeile eines Reports: Logo (falls vorhanden) + Titel +
    Status-Badge - gemeinsam genutzt von Einzel- und Batch-Report, damit
    beide dieselbe Typografie/Farbgebung tragen (Punkt 4, prompt_batch_fixes.md)."""
    badge_style = ParagraphStyle("badge", parent=_STYLES["Normal"], textColor=badge_fg, fontSize=9, alignment=1)
    title_paragraph = Paragraph(title_html, _TITLE_STYLE)
    badge_paragraph = Paragraph(badge_text, badge_style)

    icon_flowable = _build_report_icon_flowable()
    if icon_flowable is not None:
        header_cells = [icon_flowable, title_paragraph, badge_paragraph]
        header_col_widths = [22 * mm, 108 * mm, 40 * mm]
        badge_col = 2
    else:
        header_cells = [title_paragraph, badge_paragraph]
        header_col_widths = [130 * mm, 40 * mm]
        badge_col = 1

    header_table = Table([header_cells], colWidths=header_col_widths)
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (badge_col, 0), (badge_col, 0), badge_bg),
        ("BOX", (badge_col, 0), (badge_col, 0), 0.5, badge_fg),
        ("TOPPADDING", (badge_col, 0), (badge_col, 0), 6),
        ("BOTTOMPADDING", (badge_col, 0), (badge_col, 0), 6),
    ]))
    return header_table


def _build_hairline_table() -> Table:
    """Dünne Trennlinie unter der Kopfzeile, volle Satzspiegelbreite -
    gemeinsam genutzt von Einzel- und Batch-Report."""
    return Table(
        [[""]], colWidths=[170 * mm], rowHeights=[0.5],
        style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.75, _COLOR_HAIRLINE)]),
    )


def _profile_label(profile: Optional[Profile], profile_path: Optional[Union[str, Path]]) -> str:
    """Anzeigename des Vergleichsprofils für die Metadaten-/Kennzahlenanzeige
    - gemeinsam genutzt von Einzel- und Batch-Report."""
    if profile_path is not None:
        label = Path(profile_path).name
        if profile is not None:
            label += f" (v{profile.version})"
        return label
    if profile is not None:
        return f"v{profile.version}"
    return "—"


def _bool_label(value: bool) -> str:
    """Ja/Nein-Anzeige für boolesche Profil-Einstellungen im Summary."""
    return "Ja" if value else "Nein"


def _region_page_label(region: ExcludeRegion) -> str:
    """Seitenbereichs-Anzeige für die Regionen-Tabelle: konkrete Seite,
    "Alle Seiten" (page=0) oder "Ab Seite N" (page_from) - siehe
    pdf_extractor._region_applies_to_page für die zugehörige Matching-
    Logik."""
    if region.page is not None:
        return "Alle Seiten" if region.page == 0 else f"Seite {region.page}"
    return f"Ab Seite {region.page_from}"


def _ocr_mode_display(ocr: OcrConfig, mode_value: Optional[str]) -> str:
    """Effektiver OCR-Modus für die Anzeige, ohne von pdf_extractor zu
    importieren (dieselbe Fallback-Logik wie
    pdf_extractor._effective_ocr_mode, hier nur für role-unabhängige
    Anzeige verkürzt)."""
    if mode_value is not None:
        return mode_value
    return "fallback" if ocr.enabled else "off"


def _tool_version() -> str:
    """Fest eingebettete Version (engine.__version__) statt
    importlib.metadata.version() zur Laufzeit - letzteres setzt
    installierte Distributions-Metadaten voraus, die im PyInstaller-
    gebündelten Zustand nicht garantiert vorhanden sind (siehe Diagnose:
    fataler Git-Fallback in einem *anderen* Codepfad, dem lokalen
    Sidecar-Dev-Wrapper, hat denselben Symptombereich betroffen)."""
    return __version__


_DETAIL_TEXT_MAX_LEN = 300


def _truncate_end(text: str, max_len: int) -> str:
    """Kürzt für die Detailliste (nur Anzeige, nicht die Delta-Daten selbst):
    lange Delta-Texte werden nach max_len Zeichen mit "…" abgeschnitten,
    damit ReportLab keine Tabellenzelle bauen muss, die höher als eine
    Seite ist ("tallest cell ... too large on page")."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _build_report_icon_flowable() -> Optional[RLImage]:
    """Lädt das App-Icon (engine/assets/512x512.png, bereits mit
    transparentem Hintergrund) für die Zusammenfassungsseite - Pfad relativ
    zum Modul, damit es unabhängig vom aktuellen Arbeitsverzeichnis
    funktioniert. Höhe fix auf _REPORT_ICON_HEIGHT_MM, Breite aus dem
    tatsächlichen Seitenverhältnis der Bilddatei abgeleitet (aktuell
    quadratisch, aber nicht angenommen). None, falls die Datei fehlt -
    Aufrufer fällt dann auf das ursprüngliche Zweispalten-Layout ohne Icon
    zurück, statt den Report-Bau abzubrechen."""
    if not _REPORT_ICON_PATH.exists():
        return None
    with PILImage.open(_REPORT_ICON_PATH) as im:
        width_px, height_px = im.size
    height = _REPORT_ICON_HEIGHT_MM * mm
    width = height * (width_px / height_px)
    return RLImage(str(_REPORT_ICON_PATH), width=width, height=height)


def _build_summary_page_pdf_bytes(
    compare_result: CompareResult,
    ref_pdf_path: Path,
    cnd_pdf_path: Path,
    total_pages: int,
    comparisons: int,
    profile: Optional[Profile],
    profile_path: Optional[Union[str, Path]],
    duration_seconds: Optional[float],
    region_warnings: Optional[List[str]] = None,
) -> bytes:
    """Baut Seite 1 (Zusammenfassung, TC-R-001): Status-Badge, Kennzahlen-
    Kacheln, Fortschrittsbalken und Metadaten-Tabelle. Flaches Design ohne
    Schatten/Verläufe, dünne Trennlinien statt Rahmen."""
    delta_pages = sorted({d.page for d in compare_result.deltas})
    pages_with_delta = len(delta_pages)
    pages_without_delta = max(total_pages - pages_with_delta, 0)
    match_ratio = (pages_without_delta / total_pages) if total_pages else 1.0

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story: List = []

    if compare_result.has_delta:
        badge_text, badge_fg, badge_bg = "Deltas gefunden", _COLOR_DELTA, _COLOR_BADGE_DELTA_BG
    else:
        badge_text, badge_fg, badge_bg = "Keine Unterschiede", _COLOR_OK, _COLOR_BADGE_OK_BG

    story.append(_build_report_header_table(
        "Vergleichs-Zusammenfassung<br/><font size=9 color='#666666'>"
        "PaperTrail Compare · Vergleichsreport</font>",
        badge_text, badge_fg, badge_bg,
    ))
    story.append(Spacer(1, 4))
    story.append(_build_hairline_table())
    story.append(Spacer(1, 12))

    has_deltas = len(compare_result.deltas) > 0
    delta_accent = _COLOR_TILE_ORANGE if has_deltas else _COLOR_TILE_GREEN
    delta_value_color = _COLOR_TILE_VALUE_ORANGE if has_deltas else _COLOR_TILE_VALUE_GREEN

    tiles = [
        _build_kpi_tile("Seiten", str(total_pages), _COLOR_TILE_NEUTRAL),
        _build_kpi_tile("Vergleiche", str(comparisons), _COLOR_TILE_NEUTRAL),
        _build_kpi_tile("Deltas", str(len(compare_result.deltas)), delta_accent, delta_value_color),
        _build_kpi_tile(
            "Übereinstimmung", f"{match_ratio * 100:.0f} %",
            _COLOR_TILE_GREEN, _COLOR_TILE_VALUE_GREEN,
        ),
    ]
    story.append(_build_kpi_tile_row(tiles))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Seiten mit Deltas", _TILE_LABEL_STYLE))
    story.append(Spacer(1, 4))
    bar_width_mm = 170.0
    ok_width = bar_width_mm * match_ratio
    delta_width = bar_width_mm - ok_width
    bar_row = []
    bar_widths = []
    bar_colors = []
    if ok_width > 0:
        bar_row.append("")
        bar_widths.append(ok_width * mm)
        bar_colors.append(_COLOR_OK)
    if delta_width > 0:
        bar_row.append("")
        bar_widths.append(delta_width * mm)
        bar_colors.append(_COLOR_DELTA)
    if not bar_row:
        bar_row, bar_widths, bar_colors = [""], [bar_width_mm * mm], [_COLOR_OK]
    bar_table = Table([bar_row], colWidths=bar_widths, rowHeights=[4 * mm])
    bar_style = [("GRID", (0, 0), (-1, -1), 0, colors.white)]
    for idx, color in enumerate(bar_colors):
        bar_style.append(("BACKGROUND", (idx, 0), (idx, 0), color))
    bar_table.setStyle(TableStyle(bar_style))
    story.append(bar_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"{pages_without_delta} von {total_pages} Seiten ohne Delta · "
        f"{pages_with_delta} Seiten betroffen",
        _BODY_STYLE,
    ))
    story.append(Spacer(1, 16))

    profile_label = _profile_label(profile, profile_path)

    # "Profil-Einstellungen": alle vergleichsrelevanten Profilfelder statt
    # nur des Profilnamens (siehe Block 3) - auch ohne Profil werden die
    # tatsächlich geltenden Engine-Defaults gezeigt (siehe engine.__main__).
    profile_settings_rows = [
        ["Profil", profile_label],
        ["Vergleichsmodus", profile.compare_mode if profile else "words"],
        ["Groß-/Kleinschreibung", _bool_label(profile.case_sensitive if profile else True)],
        ["Leerzeichen-Toleranz", _bool_label(profile.normalize_whitespace if profile else False)],
        ["Textextraktion", profile.text_extraction if profile else "native"],
    ]
    if profile is not None and profile.ocr.enabled:
        profile_settings_rows.append(
            ["OCR Referenz", _ocr_mode_display(profile.ocr, profile.ocr.mode_reference)]
        )
        profile_settings_rows.append(
            ["OCR Kandidat", _ocr_mode_display(profile.ocr, profile.ocr.mode_candidate)]
        )

    story.append(Paragraph("Profil-Einstellungen", _TILE_LABEL_STYLE))
    story.append(Spacer(1, 4))
    profile_settings_table = Table(
        [[Paragraph(f"<b>{html.escape(label)}</b>", _CELL_STYLE), Paragraph(html.escape(str(value)), _CELL_STYLE)]
         for label, value in profile_settings_rows],
        colWidths=[55 * mm, 115 * mm],
    )
    profile_settings_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _COLOR_HAIRLINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(profile_settings_table)
    story.append(Spacer(1, 14))

    meta_rows = [
        ["Referenz-Datei", ref_pdf_path.name],
        ["Kandidat-Datei", cnd_pdf_path.name],
        ["OCR verwendet", "Ja" if compare_result.ocr_was_used else "Nein"],
        ["Verarbeitungsdauer", f"{duration_seconds:.2f} s" if duration_seconds is not None else "—"],
        ["Vergleichsdatum", datetime.now().strftime("%d.%m.%Y %H:%M:%S")],
        ["Tool-Version", _tool_version()],
    ]
    meta_table = Table(
        [[Paragraph(f"<b>{html.escape(label)}</b>", _CELL_STYLE), Paragraph(html.escape(value), _CELL_STYLE)]
         for label, value in meta_rows],
        colWidths=[55 * mm, 115 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _COLOR_HAIRLINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_table)

    # "Ausgeschlossene Regionen": detaillierte Tabelle statt reinem Zähler
    # (siehe Block 3) - nur wenn tatsächlich Regionen konfiguriert sind.
    if profile is not None and profile.exclude_regions:
        story.append(Spacer(1, 14))
        story.append(Paragraph("Ausgeschlossene Regionen", _TILE_LABEL_STYLE))
        story.append(Spacer(1, 4))
        region_rows = [["Seitenbereich", "x", "y", "Breite", "Höhe"]] + [
            [
                _region_page_label(region),
                f"{region.x:g}", f"{region.y:g}", f"{region.width:g}", f"{region.height:g}",
            ]
            for region in profile.exclude_regions
        ]
        region_table = Table(region_rows, colWidths=[45 * mm] + [30 * mm] * 4)
        region_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, _COLOR_HAIRLINE),
            ("BACKGROUND", (0, 0), (-1, 0), _COLOR_HAIRLINE),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(region_table)
        if region_warnings:
            story.append(Spacer(1, 6))
            for warning in region_warnings:
                story.append(Paragraph(html.escape(warning), _BODY_STYLE))

    doc.build(story)
    return buf.getvalue()


def _build_delta_detail_pdf_bytes(compare_result: CompareResult) -> bytes:
    """Baut die Detailliste der Deltas (Seiten-/Dateiangabe je Delta) als
    eigene(s) Seite(n) ans Ende des Reports, kleinere Schrift, feste
    Spaltenbreiten mit Zeilenumbruch statt Überlauf (TC-R-001)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story: List = [
        Paragraph("Delta-Details", _TITLE_STYLE),
        Spacer(1, 8),
        Paragraph(f"Anzahl Deltas: {len(compare_result.deltas)}", _BODY_STYLE),
        Spacer(1, 10),
    ]

    table_rows = [["#", "Seite", "Referenz", "Kandidat"]]
    for i, delta in enumerate(compare_result.deltas, start=1):
        ref_text = _truncate_end(delta.ref_text, _DETAIL_TEXT_MAX_LEN)
        cnd_text = _truncate_end(delta.cnd_text, _DETAIL_TEXT_MAX_LEN)
        table_rows.append([
            Paragraph(str(i), _DETAIL_CELL_STYLE),
            Paragraph(f"Seite {delta.page}", _DETAIL_CELL_STYLE),
            Paragraph(html.escape(ref_text), _DETAIL_CELL_STYLE),
            Paragraph(html.escape(cnd_text), _DETAIL_CELL_STYLE),
        ])
    table_rows[0] = [Paragraph(c, _DETAIL_HEADER_CELL_STYLE) for c in table_rows[0]]

    # splitByRow=1 (Default) erlaubt ReportLab, die Tabelle zwischen Zeilen
    # über Seiten zu brechen; ohne die Text-Kürzung oben würde eine einzelne
    # zu hohe Zeile ("tallest cell ... too large on page") das trotzdem
    # verhindern, da eine Zeile selbst nie über Seiten gesplittet wird.
    table = Table(
        table_rows, colWidths=_DETAIL_TABLE_COL_WIDTHS, hAlign="LEFT",
        repeatRows=1, splitByRow=1,
    )
    table.setStyle(_DETAIL_TABLE_STYLE)
    story.append(table)

    doc.build(story)
    return buf.getvalue()


def _region_applies_to_page(page: Optional[int], page_from: Optional[int], page_num: int) -> bool:
    """Dasselbe page/page_from-Wildcard-Matching wie
    pdf_extractor._region_applies_to_page (page=0 wirkt auf jeder Seite,
    page=N nur auf Seite N, page_from=N ab Seite N) - hier als eigenständige
    Funktion auf den rohen (page, page_from)-Werten statt auf einem
    Region-Objekt, weil _find_delta_rects absichtlich nur die flache
    (page, page_from, rect)-Tupelliste kennt, nicht die profile_loader-
    Typen (siehe docs/prompt_region_filter_highlights.md: keine
    Modulabhängigkeit von report_generator auf pdf_extractor)."""
    if page is not None:
        return page == 0 or page == page_num
    if page_from is not None:
        return page_num >= page_from
    return False


def _build_delta_filter_regions(
    profile: Optional[Profile],
) -> List[Tuple[Optional[int], Optional[int], pymupdf.Rect]]:
    """Baut die flache filter_regions-Liste für _find_delta_rects aus
    profile.exclude_regions UND profile.compare_regions (siehe
    docs/prompt_region_filter_highlights.md) - beide Regionsarten markieren
    Seitenbereiche, in denen ein sequenzieller Delta-Treffer als False-
    Positive gilt (Ausschluss- ebenso wie Vergleichsregionen enthalten
    typischerweise wiederkehrenden Text wie Fußzeilen oder Absenderblöcke).
    profile=None liefert eine leere Liste - _find_delta_rects filtert dann
    nichts (siehe dort)."""
    if profile is None:
        return []
    regions = list(profile.exclude_regions) + list(profile.compare_regions)
    return [
        (region.page, region.page_from, pymupdf.Rect(region.x, region.y, region.x + region.width, region.y + region.height))
        for region in regions
    ]


def _find_delta_rects(
    doc: pymupdf.Document,
    texts_by_page: Dict[int, List[Tuple[str, Optional[pymupdf.Rect]]]],
    fallback_search_all_pages: bool = False,
    filter_regions: Optional[Sequence[Tuple[Optional[int], Optional[int], pymupdf.Rect]]] = None,
) -> Dict[int, List[pymupdf.Rect]]:
    """Sucht die übergebenen Delta-Textstellen im PDF und liefert ihre
    Fundstellen-Rechtecke je Seite (1-basiert), transformiert in das
    page.rect-Koordinatensystem (berücksichtigt page.rotation - siehe
    page.rotation_matrix; search_for() liefert sonst rohe, unrotierte
    Mediabox-Koordinaten).

    Mutiert das Dokument NICHT mehr (keine Highlight-Annotationen) - die
    Delta-Markierung erfolgt seit dem Umbau auf Vektor-Einbettung
    (show_pdf_page) als eigenes Overlay direkt auf der Report-Seite, siehe
    _place_source_page().

    Findet sich der Text nicht auf der erwarteten Seite (z.B. weil
    Referenz- und Kandidat-Dokument unterschiedlich umgebrochen sind – die
    von text_comparator gemeldete Delta-Seite bezieht sich nur auf das
    Kandidat-Dokument), wird mit fallback_search_all_pages=True über das
    gesamte Dokument gesucht, statt die Markierung zu verwerfen.

    texts_by_page-Einträge sind (delta_text, clip)-Paare (siehe
    docs/prompt_region_clip_highlighting.md): ist clip gesetzt (compare_region-
    Delta, siehe compare_region_comparator), wird die Suche auf der
    erwarteten Seite auf page.search_for(text, clip=clip) eingeschränkt -
    das verhindert, dass ein Regions-Delta anderswo auf der Seite (Sender-
    Block, Fußzeile) oder gar Textfragmente daraus in völlig unbeteiligten
    Seitenbereichen ("Ghost-Highlights") gefunden werden. Die Fallback-Suche
    über das gesamte Dokument verwendet den clip NIE - der Fallback sucht
    per Definition auf ANDEREN Seiten, für die die Region-Koordinaten gar
    nicht gelten.

    filter_regions (docs/prompt_region_filter_highlights.md) ist eine flache
    Liste von (page, page_from, rect)-Tupeln aus profile.exclude_regions UND
    profile.compare_regions (siehe generate_report) - page/page_from folgen
    derselben Wildcard-Konvention wie überall sonst (siehe
    _region_applies_to_page). Wirkt NUR auf sequenzielle Deltas (clip is
    None): eine ungebremste search_for() findet einen häufigen Wortdelta-
    Text (z.B. "SparkassenVersicherung") oft mehrfach auf derselben Seite -
    Fußzeile, Absenderblock, Adressfenster -, obwohl nur EINE Fundstelle die
    tatsächliche Delta-Position ist. Ein Treffer wird verworfen, wenn sein
    Mittelpunkt in IRGENDEINER der für diese Seite aktiven Regionen liegt.
    Sind danach alle Treffer verworfen, bleibt das Ergebnis für diesen Text
    absichtlich leer - KEIN Fallback auf die ungefilterte Liste, das wäre
    wieder die falsche Markierung. Region-Deltas (clip is not None) sind
    bereits über den clip korrekt eingeschränkt und werden NICHT zusätzlich
    gefiltert.
    """
    filter_regions = filter_regions or []
    rects_by_page: Dict[int, List[pymupdf.Rect]] = {}
    for page_num, texts in texts_by_page.items():
        for text, clip in texts:
            if not text:
                continue

            found_rects: List[pymupdf.Rect] = []
            found_page_num: Optional[int] = None

            if 1 <= page_num <= len(doc):
                page = doc[page_num - 1]
                raw_rects = page.search_for(text, clip=clip) if clip is not None else page.search_for(text)
                if raw_rects:
                    found_rects = [r * page.rotation_matrix for r in raw_rects]
                    found_page_num = page_num

            if not found_rects and fallback_search_all_pages:
                for idx, page in enumerate(doc, start=1):
                    raw_rects = page.search_for(text)
                    if raw_rects:
                        found_rects = [r * page.rotation_matrix for r in raw_rects]
                        found_page_num = idx
                        break

            if clip is None and found_rects and found_page_num is not None:
                active_rects = [
                    region_rect
                    for region_page, region_page_from, region_rect in filter_regions
                    if _region_applies_to_page(region_page, region_page_from, found_page_num)
                ]
                if active_rects:
                    found_rects = [
                        rect for rect in found_rects
                        if not any(
                            region_rect.contains(pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2))
                            for region_rect in active_rects
                        )
                    ]

            if found_rects and found_page_num is not None:
                rects_by_page.setdefault(found_page_num, []).extend(found_rects)

    return rects_by_page


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
_SBS_NO_PAGE_TEXT = "Keine entsprechende Seite"
_DELTA_OVERLAY_FILL = (1, 1, 0)
_DELTA_OVERLAY_FILL_OPACITY = 0.4


def _place_source_page(
    page: pymupdf.Page, doc: Optional[pymupdf.Document], src_page_num: Optional[int],
    delta_rects: List[pymupdf.Rect],
    x0: float, y0: float, x1: float, y1: float,
) -> None:
    """Bettet Seite src_page_num (1-basiert) aus doc als Vektor-Inhalt
    (page.show_pdf_page) proportional skaliert und zentriert in das
    Rechteck (x0, y0, x1, y1) ein - keine Rasterung. Fehlt die Seite, wird
    ein Hinweis eingeblendet (unterschiedliche Seitenzahlen durch
    Seitenumbruch). delta_rects (in page.rect-Koordinaten der Quellseite,
    siehe _find_delta_rects) werden in dasselbe Zielrechteck transformiert
    und als halbtransparentes Vektor-Overlay auf die Report-Seite
    gezeichnet, statt in die Seite hineingerastert zu werden.

    Zu page.show_pdf_page()/rotierten Seiten (empirisch verifiziert, siehe
    PR-Diskussion): show_pdf_page() übernimmt die eigene page.rotation der
    Quellseite NICHT automatisch und liefert bei einer Quellseite mit
    page.rotation != 0 UND zusätzlich gesetztem rotate-Parameter falsch
    zugeschnittenen/verschobenen Inhalt (Clip-Rect wird gegen die
    unrotierte Mediabox statt gegen page.rect berechnet). Der einzige
    Weg, der in Tests mit /Rotate 90/180/270 exakt dem direkten
    page.get_pixmap()-Rendering entsprach: die page.rotation der
    Quellseite auf 0 setzen (reine In-Memory-Mutation des offenen
    pymupdf.Document, nicht der Originaldatei) und stattdessen die
    komplementäre Drehung (360 - rotation) % 360 explizit über den
    rotate-Parameter anfordern.
    """
    target = pymupdf.Rect(x0, y0, x1, y1)
    if doc is None or src_page_num is None or not (1 <= src_page_num <= len(doc)):
        page.insert_textbox(target, _SBS_NO_PAGE_TEXT, fontsize=10, align=1)
        return

    src_page = doc[src_page_num - 1]
    src_rect = src_page.rect
    rotation = src_page.rotation

    avail_w, avail_h = target.width, target.height
    scale = min(avail_w / src_rect.width, avail_h / src_rect.height)
    w, h = src_rect.width * scale, src_rect.height * scale
    rx0 = x0 + (avail_w - w) / 2
    ry0 = y0 + (avail_h - h) / 2
    embed_rect = pymupdf.Rect(rx0, ry0, rx0 + w, ry0 + h)

    if rotation:
        src_page.set_rotation(0)
    page.show_pdf_page(embed_rect, doc, pno=src_page_num - 1, rotate=(360 - rotation) % 360)

    for rect in delta_rects:
        overlay_rect = pymupdf.Rect(
            rx0 + (rect.x0 - src_rect.x0) * scale,
            ry0 + (rect.y0 - src_rect.y0) * scale,
            rx0 + (rect.x1 - src_rect.x0) * scale,
            ry0 + (rect.y1 - src_rect.y0) * scale,
        )
        page.draw_rect(
            overlay_rect, color=None,
            fill=_DELTA_OVERLAY_FILL, fill_opacity=_DELTA_OVERLAY_FILL_OPACITY,
        )


def _build_side_by_side_document(
    ref_doc: pymupdf.Document, cnd_doc: pymupdf.Document,
    ref_rects_by_page: Dict[int, List[pymupdf.Rect]],
    cnd_rects_by_page: Dict[int, List[pymupdf.Rect]],
) -> pymupdf.Document:
    """Erzeugt den Seite-für-Seite Nebeneinander-Vergleich in Querformat:
    links die Referenz-, rechts die Kandidat-Seite, jeweils als
    eingebetteter Vektor-Inhalt mit Delta-Overlay (siehe _place_source_page)."""
    page_count = max(len(ref_doc), len(cnd_doc))
    out_doc = pymupdf.open()

    for i in range(page_count):
        page = out_doc.new_page(width=_SBS_PAGE_W, height=_SBS_PAGE_H)

        page.insert_textbox(
            pymupdf.Rect(_SBS_MARGIN_LR, _SBS_MARGIN_TOP, _SBS_DIVIDER_X - 1, _SBS_CONTENT_TOP),
            "Referenz", fontsize=8,
        )
        page.insert_textbox(
            pymupdf.Rect(_SBS_DIVIDER_X + 1, _SBS_MARGIN_TOP, _SBS_PAGE_W - _SBS_MARGIN_LR, _SBS_CONTENT_TOP),
            "Kandidat", fontsize=8,
        )
        page.draw_line(
            pymupdf.Point(_SBS_DIVIDER_X, _SBS_MARGIN_TOP),
            pymupdf.Point(_SBS_DIVIDER_X, _SBS_PAGE_H - _SBS_MARGIN_BOTTOM),
            width=1,
        )

        ref_page_num = i + 1 if i < len(ref_doc) else None
        cnd_page_num = i + 1 if i < len(cnd_doc) else None
        _place_source_page(
            page, ref_doc, ref_page_num, ref_rects_by_page.get(ref_page_num, []),
            _SBS_MARGIN_LR, _SBS_CONTENT_TOP, _SBS_DIVIDER_X - 1, _SBS_CONTENT_BOTTOM,
        )
        _place_source_page(
            page, cnd_doc, cnd_page_num, cnd_rects_by_page.get(cnd_page_num, []),
            _SBS_DIVIDER_X + 1, _SBS_CONTENT_TOP, _SBS_PAGE_W - _SBS_MARGIN_LR, _SBS_CONTENT_BOTTOM,
        )

        page.insert_textbox(
            pymupdf.Rect(0, _SBS_PAGE_H - _SBS_FOOTER_HEIGHT, _SBS_PAGE_W, _SBS_PAGE_H),
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
    profile_path: Optional[Union[str, Path]] = None,
    duration_seconds: Optional[float] = None,
    region_warnings: Optional[List[str]] = None,
) -> Path:
    """Erzeugt einen Einzel-Report (TC-R-001): Zusammenfassungsseite
    (Hochformat) mit Status, Kennzahlen und Metadaten, gefolgt von einer
    Querformat-Seite pro Dokumentenseite mit Referenz (links) und Kandidat
    (rechts) nebeneinander (jeweils mit markierten Delta-Stellen), und
    abschließend der Delta-Detailliste mit Seiten- und Dateiangabe.

    Die Delta.page-Angabe bezieht sich nur auf das Kandidat-Dokument (siehe
    text_comparator.Delta). Im Referenz-Dokument wird zuerst auf derselben
    Seitenzahl gesucht; bei unterschiedlichem Seitenumbruch zwischen
    Referenz und Kandidat (Kernprinzip des Vergleichs, siehe TC-T-003) und
    fehlendem Treffer wird über das gesamte Referenz-Dokument gesucht
    (TC-R-001-seitenumbruch).

    duration_seconds erlaubt es Aufrufern, die Dauer des gesamten
    Vergleichsvorgangs (inkl. text_comparator.compare()) für die
    Zusammenfassungsseite zu übergeben, statt nur die Report-Erzeugung
    selbst zu messen. profile_path wird nur zur Anzeige des Profil-
    Dateinamens auf der Zusammenfassungsseite verwendet.

    profile.report_format="html" erzeugt statt des PDF-Reports einen
    einfachen HTML-Bericht ohne Delta-Markierung im Dokument (TC-R-004) –
    PDF bleibt das primäre Format (Architekturentscheidung #4).

    region_warnings (siehe pdf_extractor.extract_pages_for_profile) macht
    auf der Zusammenfassungsseite sichtbar, wenn profile.exclude_regions
    nicht vollständig angewendet werden konnte (z.B. Tabellenseiten),
    statt den Ausschluss dort nur als reine Konfigurationszahl ohne
    Aussage über die tatsächliche Anwendung zu zeigen.
    """
    ref_pdf_path = Path(ref_pdf_path)
    cnd_pdf_path = Path(cnd_pdf_path)
    output_path = Path(output_path)

    if profile is not None and profile.report_format == "html":
        return _generate_report_html(compare_result, ref_pdf_path, cnd_pdf_path, output_path)

    # region_clip (siehe text_comparator.Delta, docs/prompt_region_clip_highlighting.md)
    # ist ein (x0, y0, x1, y1)-Tupel - für _find_delta_rects wird es hier in
    # ein pymupdf.Rect umgewandelt (None bleibt None: nicht-regionsbasierte
    # Deltas durchsuchen weiterhin die ganze Seite).
    ref_texts_by_page: Dict[int, List[Tuple[str, Optional[pymupdf.Rect]]]] = {}
    cnd_texts_by_page: Dict[int, List[Tuple[str, Optional[pymupdf.Rect]]]] = {}
    for delta in compare_result.deltas:
        clip = pymupdf.Rect(*delta.region_clip) if delta.region_clip is not None else None
        ref_texts_by_page.setdefault(delta.page, []).append((delta.ref_text, clip))
        cnd_texts_by_page.setdefault(delta.page, []).append((delta.cnd_text, clip))

    filter_regions = _build_delta_filter_regions(profile)

    ref_doc = pymupdf.open(str(ref_pdf_path))
    try:
        cnd_doc = pymupdf.open(str(cnd_pdf_path))
        try:
            ref_rects_by_page = _find_delta_rects(
                ref_doc, ref_texts_by_page, fallback_search_all_pages=True, filter_regions=filter_regions
            )
            cnd_rects_by_page = _find_delta_rects(cnd_doc, cnd_texts_by_page, filter_regions=filter_regions)
            total_pages = max(len(ref_doc), len(cnd_doc))

            summary_bytes = _build_summary_page_pdf_bytes(
                compare_result, ref_pdf_path, cnd_pdf_path,
                total_pages=total_pages, comparisons=1,
                profile=profile, profile_path=profile_path,
                duration_seconds=duration_seconds,
                region_warnings=region_warnings,
            )
            report_doc = pymupdf.open(stream=summary_bytes, filetype="pdf")
            try:
                side_by_side = _build_side_by_side_document(
                    ref_doc, cnd_doc, ref_rects_by_page, cnd_rects_by_page
                )
                try:
                    report_doc.insert_pdf(side_by_side)

                    if compare_result.has_delta:
                        detail_bytes = _build_delta_detail_pdf_bytes(compare_result)
                        detail_doc = pymupdf.open(stream=detail_bytes, filetype="pdf")
                        try:
                            report_doc.insert_pdf(detail_doc)
                        finally:
                            detail_doc.close()

                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    # garbage=4 dedupliziert Ressourcen (dieselbe Quellseite wird ggf.
                    # mehrfach als Form-XObject referenziert), deflate=True komprimiert
                    # die Streams - beides senkt die Dateigröße zusätzlich zum Wegfall
                    # der Rasterbilder.
                    report_doc.save(str(output_path), garbage=4, deflate=True)
                finally:
                    side_by_side.close()
            finally:
                report_doc.close()
        finally:
            cnd_doc.close()
    finally:
        ref_doc.close()

    return output_path


_BATCH_TABLE_COL_WIDTHS = [55 * mm, 55 * mm, 25 * mm, 35 * mm]


def _pair_match_percent(pair: PairResult) -> Optional[int]:
    """Übereinstimmung in % je Paar - dieselbe Formel wie die
    Zusammenfassungsseite des Einzel-Reports (Seiten ohne Delta / Gesamt-
    seitenzahl) bzw. das GUI-Äquivalent in BatchView.tsx::matchPercent."""
    if pair.status != "ok" or pair.compare_result is None or not pair.total_pages:
        return None
    delta_pages = {d.page for d in pair.compare_result.deltas}
    match_ratio = (pair.total_pages - len(delta_pages)) / pair.total_pages
    return round(match_ratio * 100)


def _build_batch_table(batch_result: BatchResult) -> Table:
    """Haupttabelle aller Paare (Referenz, Kandidat, Deltas, Übereinstimmung).
    Fehlerpaare werden nur hier markiert (rote Zeile, Fehlertext über beide
    Zahlenspalten hinweg statt Delta-Anzahl/Übereinstimmung) - keine eigene
    Fehlersektion (Punkt 4, prompt_batch_fixes.md). Zellen sind Paragraph-
    Objekte, damit lange Dateinamen/Fehlertexte innerhalb der festen
    Spaltenbreiten umbrechen statt über den Satzspiegel hinauszulaufen
    (Punkt 3); repeatRows=1 wiederholt die Kopfzeile auf Folgeseiten."""
    table_rows = [
        [Paragraph(c, _HEADER_CELL_STYLE) for c in ["Referenz", "Kandidat", "Deltas", "Übereinstimmung"]]
    ]
    style_commands = list(_TABLE_STYLE.getCommands())

    for row_index, pair in enumerate(batch_result.pairs, start=1):
        ref_name = Path(pair.ref_path).name
        cnd_name = Path(pair.cnd_path).name
        if pair.status == "ok":
            delta_count = str(len(pair.compare_result.deltas)) if pair.compare_result else "0"
            percent = _pair_match_percent(pair)
            match_text = f"{percent} %" if percent is not None else "—"
            table_rows.append([
                Paragraph(html.escape(ref_name), _CELL_STYLE),
                Paragraph(html.escape(cnd_name), _CELL_STYLE),
                Paragraph(delta_count, _CELL_STYLE),
                Paragraph(match_text, _CELL_STYLE),
            ])
        else:
            table_rows.append([
                Paragraph(html.escape(ref_name), _CELL_STYLE),
                Paragraph(html.escape(cnd_name), _CELL_STYLE),
                Paragraph(html.escape(f"Fehler: {pair.error}"), _CELL_STYLE),
                "",
            ])
            style_commands.append(("SPAN", (2, row_index), (3, row_index)))
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), _COLOR_BADGE_DELTA_BG))
            style_commands.append(("TEXTCOLOR", (0, row_index), (-1, row_index), _COLOR_DELTA))

    table = Table(
        table_rows, colWidths=_BATCH_TABLE_COL_WIDTHS, hAlign="LEFT",
        repeatRows=1 if len(table_rows) > 1 else 0,
    )
    table.setStyle(TableStyle(style_commands))
    return table


def generate_batch_report(
    batch_result: BatchResult,
    output_path: Union[str, Path],
    profile: Optional[Profile] = None,
    profile_path: Optional[Union[str, Path]] = None,
    duration_seconds: Optional[float] = None,
    start_time: Optional[datetime] = None,
) -> Path:
    """Erzeugt den Batch-Report (TC-R-002) im Layout-Vokabular des Einzel-
    Reports (Logo, Titel, Status-Badge, Kennzahlen-Kacheln - siehe
    _build_report_header_table/_build_kpi_tile_row), gefolgt von der
    Haupttabelle aller Paare (siehe _build_batch_table). Punkt 4,
    prompt_batch_fixes.md."""
    output_path = Path(output_path)
    if start_time is None:
        start_time = datetime.now()

    total = len(batch_result.pairs)
    ok_count = batch_result.ok_count
    error_count = batch_result.error_count
    success_rate = (ok_count / total * 100) if total else 0.0
    total_pages = sum(p.total_pages or 0 for p in batch_result.pairs)
    sum_deltas = sum(
        len(p.compare_result.deltas)
        for p in batch_result.pairs
        if p.status == "ok" and p.compare_result is not None
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story: List = []

    if error_count == 0:
        badge_text, badge_fg, badge_bg = "Alle Paare OK", _COLOR_OK, _COLOR_BADGE_OK_BG
    else:
        badge_text, badge_fg, badge_bg = f"{error_count} Fehler", _COLOR_DELTA, _COLOR_BADGE_DELTA_BG

    story.append(_build_report_header_table(
        "Batch-Zusammenfassung<br/><font size=9 color='#666666'>"
        "PaperTrail Compare · Batch-Report</font>",
        badge_text, badge_fg, badge_bg,
    ))
    story.append(Spacer(1, 4))
    story.append(_build_hairline_table())
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Batch-Lauf vom {start_time.strftime('%d.%m.%Y, %H:%M:%S')} Uhr", _SUBTITLE_STYLE,
    ))
    story.append(Spacer(1, 6))

    rate_accent = _COLOR_TILE_GREEN if error_count == 0 else _COLOR_TILE_ORANGE
    rate_value_color = _COLOR_TILE_VALUE_GREEN if error_count == 0 else _COLOR_TILE_VALUE_ORANGE
    error_accent = _COLOR_TILE_ORANGE if error_count else _COLOR_TILE_GREEN
    error_value_color = _COLOR_TILE_VALUE_ORANGE if error_count else _COLOR_TILE_VALUE_GREEN
    delta_sum_accent = _COLOR_TILE_ORANGE if sum_deltas > 0 else _COLOR_TILE_GREEN
    delta_sum_value_color = _COLOR_TILE_VALUE_ORANGE if sum_deltas > 0 else _COLOR_TILE_VALUE_GREEN

    story.append(_build_kpi_tile_row([
        _build_kpi_tile("Dateipaare gesamt", str(total), _COLOR_TILE_NEUTRAL),
        _build_kpi_tile("Erfolgreich", str(ok_count), _COLOR_TILE_GREEN, _COLOR_TILE_VALUE_GREEN),
        _build_kpi_tile("Fehler", str(error_count), error_accent, error_value_color),
        _build_kpi_tile("Erfolgsquote", f"{success_rate:.0f} %", rate_accent, rate_value_color),
    ]))
    story.append(Spacer(1, 8))
    story.append(_build_kpi_tile_row([
        _build_kpi_tile("Seiten gesamt", str(total_pages), _COLOR_TILE_NEUTRAL),
        _build_kpi_tile(
            "Laufzeit", f"{duration_seconds:.1f} s" if duration_seconds is not None else "—",
            _COLOR_TILE_NEUTRAL,
        ),
        _build_kpi_tile("Summe Deltas", str(sum_deltas), delta_sum_accent, delta_sum_value_color),
        _build_kpi_tile(
            "Profil", _profile_label(profile, profile_path), _COLOR_TILE_NEUTRAL,
            value_font_size=10,
        ),
    ]))
    story.append(Spacer(1, 16))

    story.append(_build_batch_table(batch_result))

    doc.build(story)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(buf.getvalue())

    return output_path
