"""
PaperTrail Compare – Fixture Generator
=======================================
Erzeugt synthetische Test-PDFs für alle Testfälle der Testspezifikation.

Aufruf:
    python tests/fixtures/generate_fixtures.py

Ausgabe:
    tests/fixtures/<tc-id>/ref.pdf   – Referenzdokument
    tests/fixtures/<tc-id>/cnd.pdf   – Kandidatendokument
    tests/fixtures/<tc-id>/README.md – Kurzbeschreibung des Fixtures

Abhängigkeiten:
    pip install reportlab pymupdf

Konventionen:
    - Alle Texte sind synthetisch – keine echten Kundendaten.
    - Jede Hilfsfunktion erzeugt genau ein Pärchen (ref, cnd).
    - Die Dateinamen entsprechen 1:1 den Testfall-IDs der Testspezifikation.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER

import fitz

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
W, H = A4  # 595 x 842 pt

STYLES = getSampleStyleSheet()
NORMAL = STYLES["Normal"]
NORMAL.fontName = "Helvetica"
NORMAL.fontSize = 11
NORMAL.leading = 14

BODY = ParagraphStyle(
    "body",
    parent=NORMAL,
    spaceAfter=6,
)

HEADING = ParagraphStyle(
    "heading",
    parent=NORMAL,
    fontSize=13,
    leading=18,
    spaceBefore=10,
    spaceAfter=4,
    fontName="Helvetica-Bold",
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def fixture_dir(tc_id: str) -> Path:
    d = FIXTURES_DIR / tc_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def simple_pdf(path: Path, pages: list[list[str]], title: str = "") -> None:
    """Erzeugt ein einfaches mehrseitiges PDF aus Text-Absätzen."""
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        title=title,
    )
    story = []
    for i, page_paragraphs in enumerate(pages):
        if i > 0:
            story.append(PageBreak())
        for text in page_paragraphs:
            story.append(Paragraph(text, BODY))
            story.append(Spacer(1, 3))
    doc.build(story)


def write_readme(tc_id: str, title: str, description: str, ref_desc: str, cnd_desc: str) -> None:
    d = fixture_dir(tc_id)
    text = textwrap.dedent(f"""\
        # Fixture: {tc_id}

        **{title}**

        {description}

        ## ref.pdf
        {ref_desc}

        ## cnd.pdf
        {cnd_desc}
    """)
    (d / "README.md").write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# TC-X-001  Nativen Text aus einseitigem PDF extrahieren (pdf_extractor, P1)
# ---------------------------------------------------------------------------
# Nicht Teil der Testspezifikation (die definiert für pdf_extractor keine
# eigenen Grundlagen-Testfälle) – ergänzt als P1-Basis für die reine native
# Textextraktion, auf der TC-T-007/008 aufbauen.

def generate_tc_x_001() -> None:
    tc = "TC-X-001"
    d = fixture_dir(tc)
    simple_pdf(d / "doc.pdf", [["Dies ist ein einfacher, einseitiger Testtext."]])
    write_readme(
        tc,
        "Nativen Text aus einseitigem PDF extrahieren",
        "Ein einzelnes PDF mit einer Seite und einfachem Fließtext ohne "
        "Spalten oder Tabellen.",
        "doc.pdf: eine Seite, ein Absatz.",
        "(kein Vergleich – reiner Extraktionstest)",
    )


# ---------------------------------------------------------------------------
# TC-X-002  Text aus mehrseitigem PDF seitenweise extrahieren (pdf_extractor, P1)
# ---------------------------------------------------------------------------

def generate_tc_x_002() -> None:
    tc = "TC-X-002"
    d = fixture_dir(tc)
    simple_pdf(d / "doc.pdf", [
        ["Text auf Seite eins."],
        ["Text auf Seite zwei."],
        ["Text auf Seite drei."],
    ])
    write_readme(
        tc,
        "Text aus mehrseitigem PDF seitenweise extrahieren",
        "Ein PDF mit drei Seiten, jede mit eindeutigem Text, um zu prüfen, "
        "dass die Extraktion pro Seite einen eigenen Text liefert (Liste "
        "mit einem Eintrag pro Seite).",
        "doc.pdf: drei Seiten mit je einem eindeutigen Satz.",
        "(kein Vergleich – reiner Extraktionstest)",
    )


# ---------------------------------------------------------------------------
# TC-T-001  Identische Texte – kein Delta
# ---------------------------------------------------------------------------

def generate_tc_t_001() -> None:
    tc = "TC-T-001"
    d = fixture_dir(tc)

    text_block = [
        "Sehr geehrte Damen und Herren,",
        "hiermit bestätigen wir den Eingang Ihrer Bestellung vom 15. Juli 2026.",
        "Der Gesamtbetrag beläuft sich auf 1.234,56 EUR.",
        "Bitte überweisen Sie den Betrag innerhalb von 14 Tagen.",
        "Mit freundlichen Grüßen",
        "Musterunternehmen GmbH",
    ]

    simple_pdf(d / "ref.pdf", [text_block], title=f"{tc} ref")
    simple_pdf(d / "cnd.pdf", [text_block], title=f"{tc} cnd")

    write_readme(
        tc,
        "Identische Texte – kein Delta",
        "Beide Dokumente sind inhaltlich und strukturell identisch. "
        "Der Vergleich muss has_delta == False liefern.",
        "Einseitiges Dokument mit Standardtext.",
        "Exakte Kopie von ref.pdf (anderer PDF-Generator-Zeitstempel, gleicher Text).",
    )


# ---------------------------------------------------------------------------
# TC-T-002  Silbentrennung am Zeilenende normalisieren
# ---------------------------------------------------------------------------

def generate_tc_t_002() -> None:
    tc = "TC-T-002"
    d = fixture_dir(tc)

    # ref: enthält Silbentrennungen mit weichem Bindestrich am Zeilenende
    ref_paragraphs = [
        "Die Auftrags­be­stä­ti­gung wurde erfolgreich verar­beitet.",
        "Der Gesamt­betrag beläuft sich auf 1.234,56 EUR.",
        "Bitte über­weisen Sie den Betrag inner­halb von 14 Tagen.",
        "Ihre Kunden­nummer lautet: KD-2026-00815.",
        "Für Rück­fragen stehen wir Ihnen gerne zur Ver­fügung.",
    ]

    # cnd: gleicher Text, aber ohne Silbentrennung (Fließtext)
    cnd_paragraphs = [
        "Die Auftragsbestätigung wurde erfolgreich verarbeitet.",
        "Der Gesamtbetrag beläuft sich auf 1.234,56 EUR.",
        "Bitte überweisen Sie den Betrag innerhalb von 14 Tagen.",
        "Ihre Kundennummer lautet: KD-2026-00815.",
        "Für Rückfragen stehen wir Ihnen gerne zur Verfügung.",
    ]

    simple_pdf(d / "ref.pdf", [ref_paragraphs], title=f"{tc} ref")
    simple_pdf(d / "cnd.pdf", [cnd_paragraphs], title=f"{tc} cnd")

    write_readme(
        tc,
        "Silbentrennung am Zeilenende normalisieren",
        "ref.pdf enthält Wörter mit Soft-Hyphens (­). "
        "cnd.pdf enthält dieselben Wörter ohne Trennung. "
        "Der Comparator muss vor dem Vergleich Silbentrennungen auflösen.",
        "Text mit Soft-Hyphens (­) in mehreren Wörtern.",
        "Gleicher Text, keine Silbentrennungen.",
    )


# ---------------------------------------------------------------------------
# TC-T-003  Unterschiedlicher Seitenumbruch – gleicher Text
# ---------------------------------------------------------------------------

def generate_tc_t_003() -> None:
    tc = "TC-T-003"
    d = fixture_dir(tc)

    absatz_1 = [
        "Sehr geehrte Damen und Herren,",
        "wir freuen uns, Ihnen mitteilen zu können, dass Ihre Bestellung eingegangen ist.",
    ]
    absatz_2 = [
        "Die Lieferung erfolgt voraussichtlich innerhalb von fünf Werktagen.",
        "Sollten Sie Fragen haben, stehen wir Ihnen jederzeit zur Verfügung.",
    ]
    absatz_3 = [
        "Mit freundlichen Grüßen",
        "Musterunternehmen GmbH · Musterstraße 1 · 60311 Frankfurt am Main",
    ]

    # ref: Absatz 1+2 auf Seite 1, Absatz 3 auf Seite 2
    simple_pdf(
        d / "ref.pdf",
        [absatz_1 + absatz_2, absatz_3],
        title=f"{tc} ref",
    )

    # cnd: Absatz 1 auf Seite 1, Absatz 2+3 auf Seite 2
    simple_pdf(
        d / "cnd.pdf",
        [absatz_1, absatz_2 + absatz_3],
        title=f"{tc} cnd",
    )

    write_readme(
        tc,
        "Unterschiedlicher Seitenumbruch – gleicher Text",
        "Beide Dokumente enthalten denselben Text, aber der Seitenumbruch "
        "liegt an unterschiedlichen Stellen. Der Comparator muss Seitenumbrüche "
        "ignorieren und nur den Fließtext vergleichen.",
        "Absätze 1+2 auf Seite 1, Absatz 3 auf Seite 2.",
        "Absatz 1 auf Seite 1, Absätze 2+3 auf Seite 2.",
    )


# ---------------------------------------------------------------------------
# TC-T-004  Echter Textunterschied ergibt Delta
# ---------------------------------------------------------------------------

def generate_tc_t_004() -> None:
    tc = "TC-T-004"
    d = fixture_dir(tc)

    ref_paragraphs = [
        "Rechnungsnummer: RE-2026-00042",
        "Rechnungsdatum: 15.07.2026",
        "Betrag: 100 EUR",
        "Mehrwertsteuer (19 %): 19,00 EUR",
        "Gesamtbetrag: 119,00 EUR",
    ]

    cnd_paragraphs = [
        "Rechnungsnummer: RE-2026-00042",
        "Rechnungsdatum: 15.07.2026",
        "Betrag: 200 EUR",          # ← Delta: Betrag geändert
        "Mehrwertsteuer (19 %): 38,00 EUR",  # ← Delta: MwSt geändert
        "Gesamtbetrag: 238,00 EUR",          # ← Delta: Gesamt geändert
    ]

    simple_pdf(d / "ref.pdf", [ref_paragraphs], title=f"{tc} ref")
    simple_pdf(d / "cnd.pdf", [cnd_paragraphs], title=f"{tc} cnd")

    write_readme(
        tc,
        "Echter Textunterschied ergibt Delta",
        "ref.pdf und cnd.pdf unterscheiden sich in drei Zeilen (Betrag, MwSt, Gesamt). "
        "Der Comparator muss has_delta == True liefern und alle drei Deltas melden.",
        "Rechnung mit Betrag 100 EUR.",
        "Rechnung mit Betrag 200 EUR (+ angepasste MwSt und Gesamt).",
    )


# ---------------------------------------------------------------------------
# TC-T-005  Leerzeichennormalisierung
# ---------------------------------------------------------------------------

def generate_tc_t_005() -> None:
    tc = "TC-T-005"
    d = fixture_dir(tc)

    # ref: mehrfache Leerzeichen und Tabs
    ref_paragraphs = [
        "Kundennummer:   KD-2026-00815",
        "Vertragsart:      Wartungsvertrag",
        "Laufzeit:            12  Monate",
        "Jahresbeitrag:  1.200,00   EUR",
    ]

    # cnd: einfache Leerzeichen (normalisiert)
    cnd_paragraphs = [
        "Kundennummer: KD-2026-00815",
        "Vertragsart: Wartungsvertrag",
        "Laufzeit: 12 Monate",
        "Jahresbeitrag: 1.200,00 EUR",
    ]

    simple_pdf(d / "ref.pdf", [ref_paragraphs], title=f"{tc} ref")
    simple_pdf(d / "cnd.pdf", [cnd_paragraphs], title=f"{tc} cnd")

    write_readme(
        tc,
        "Leerzeichennormalisierung",
        "ref.pdf enthält mehrfache Leerzeichen als Ausrichthilfe. "
        "cnd.pdf verwendet einfache Leerzeichen. Kein Delta erwartet.",
        "Felder mit mehrfachen Leerzeichen als Ausrichthilfe.",
        "Gleiche Felder, einfache Leerzeichen.",
    )


# ---------------------------------------------------------------------------
# TC-T-006  Groß-/Kleinschreibung (konfigurierbar)
# ---------------------------------------------------------------------------

def generate_tc_t_006() -> None:
    tc = "TC-T-006"
    d = fixture_dir(tc)

    ref_paragraphs = [
        "MUSTERUNTERNEHMEN GMBH",
        "MUSTERSTRASSE 1",
        "60311 FRANKFURT AM MAIN",
        "Betreff: AUFTRAGSBESTÄTIGUNG NR. 2026-00042",
    ]

    cnd_paragraphs = [
        "Musterunternehmen GmbH",
        "Musterstraße 1",
        "60311 Frankfurt am Main",
        "Betreff: Auftragsbestätigung Nr. 2026-00042",
    ]

    simple_pdf(d / "ref.pdf", [ref_paragraphs], title=f"{tc} ref")
    simple_pdf(d / "cnd.pdf", [cnd_paragraphs], title=f"{tc} cnd")

    write_readme(
        tc,
        "Groß-/Kleinschreibung (konfigurierbar)",
        "ref.pdf ist vollständig in Großbuchstaben. cnd.pdf in gemischter Schreibung. "
        "Mit case_sensitive=false → kein Delta. Mit case_sensitive=true → Deltas.",
        "Text vollständig in Großbuchstaben.",
        "Gleicher Text in normaler Groß-/Kleinschreibung.",
    )


# ---------------------------------------------------------------------------
# TC-T-007  Mehrspaltiger Text – korrekte Lesereihenfolge
# ---------------------------------------------------------------------------

def generate_tc_t_007() -> None:
    """Zweispaltiges Layout via Canvas (platypus unterstützt kein echtes 2-col)."""
    tc = "TC-T-007"
    d = fixture_dir(tc)

    def draw_two_column(path: Path, col1_lines: list[str], col2_lines: list[str]) -> None:
        c = rl_canvas.Canvas(str(path), pagesize=A4)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(25 * mm, H - 25 * mm, "Zweispaltiges Dokument")

        c.setFont("Helvetica", 10)
        col1_x = 25 * mm
        col2_x = W / 2 + 5 * mm
        y_start = H - 45 * mm
        line_h = 14

        for i, line in enumerate(col1_lines):
            c.drawString(col1_x, y_start - i * line_h, line)
        for i, line in enumerate(col2_lines):
            c.drawString(col2_x, y_start - i * line_h, line)

        # Trennlinie zwischen den Spalten
        c.setStrokeColor(colors.lightgrey)
        c.line(W / 2, 25 * mm, W / 2, H - 35 * mm)

        c.save()

    col1 = ["Abschnitt A", "A 1: Einleitung", "A 2: Methodik", "A 3: Ergebnisse", "A 4: Fazit"]
    col2 = ["Abschnitt B", "B 1: Datengrundlage", "B 2: Analyse", "B 3: Schlussfolgerung", "B 4: Ausblick"]

    draw_two_column(d / "ref.pdf", col1, col2)
    draw_two_column(d / "cnd.pdf", col1, col2)

    write_readme(
        tc,
        "Mehrspaltiger Text – korrekte Lesereihenfolge",
        "Beide PDFs haben ein zweispaltiges Layout. Der Extractor muss "
        "spaltenweise (links komplett, dann rechts) lesen, nicht zeilenweise.",
        "Zweispaltiges Layout: Spalte 1 = Abschnitt A, Spalte 2 = Abschnitt B.",
        "Identisches zweispaltiges Layout.",
    )


# ---------------------------------------------------------------------------
# TC-T-008  Tabellenerkennung
# ---------------------------------------------------------------------------

def generate_tc_t_008() -> None:
    tc = "TC-T-008"
    d = fixture_dir(tc)

    table_data = [
        ["Pos.", "Bezeichnung", "Menge", "Einzelpreis", "Gesamtpreis"],
        ["1", "Artikel Alpha", "10", "12,50 EUR", "125,00 EUR"],
        ["2", "Artikel Beta", "5", "48,00 EUR", "240,00 EUR"],
        ["3", "Artikel Gamma", "2", "199,00 EUR", "398,00 EUR"],
        ["", "", "", "Nettosumme:", "763,00 EUR"],
        ["", "", "", "MwSt. 19 %:", "144,97 EUR"],
        ["", "", "", "Gesamt:", "907,97 EUR"],
    ]

    table_style_ref = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (-2, -3), (-1, -1), "Helvetica-Bold"),
    ])

    # cnd: gleiche Daten, aber schmalere Spalten und anderes Farbschema
    table_style_cnd = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#375623")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (-2, -3), (-1, -1), "Helvetica-Bold"),
    ])

    col_widths_ref = [25, 120, 40, 80, 80]
    col_widths_cnd = [30, 110, 45, 85, 75]

    for path, style, widths in [
        (d / "ref.pdf", table_style_ref, col_widths_ref),
        (d / "cnd.pdf", table_style_cnd, col_widths_cnd),
    ]:
        doc = SimpleDocTemplate(str(path), pagesize=A4,
                                leftMargin=25*mm, rightMargin=25*mm,
                                topMargin=25*mm, bottomMargin=25*mm)
        t = Table(table_data, colWidths=[w * mm for w in widths])
        t.setStyle(style)
        doc.build([
            Paragraph("Auftragsbestätigung – Positionsliste", HEADING),
            Spacer(1, 6),
            t,
        ])

    write_readme(
        tc,
        "Tabellenerkennung",
        "Beide PDFs enthalten dieselbe Rechnungstabelle, aber mit unterschiedlichem "
        "Farbschema und leicht abweichenden Spaltenbreiten. Der Comparator muss den "
        "Tabelleninhalt korrekt extrahieren und vergleichen.",
        "Rechnungstabelle, blauer Header, alternierende Zeilen.",
        "Rechnungstabelle, grüner Header, ohne Zebra-Muster – gleicher Inhalt.",
    )


# ---------------------------------------------------------------------------
# TC-E-001 / TC-E-002  Ausschluss-Regionen
# ---------------------------------------------------------------------------

def generate_tc_e_001_002() -> None:
    """
    Erzeugt Fixtures für TC-E-001 (Region ausschließen) und
    TC-E-002 (Ausschluss gilt nur für definierte Seite).
    """
    for tc in ("TC-E-001", "TC-E-002"):
        d = fixture_dir(tc)

        def draw_page_with_date(c: rl_canvas.Canvas, date_str: str,
                                body_text: str, page_num: int) -> None:
            """Zeichnet eine Seite mit Datum im Kopfbereich (Ausschluss-Region)."""
            # Ausschluss-Region: x=0, y=H-50pt, w=200pt, h=50pt  →  PDF-Koordinaten
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.grey)
            c.drawString(15 * mm, H - 15 * mm, f"Druckdatum: {date_str}")
            c.drawString(15 * mm, H - 22 * mm, f"Seite {page_num}")

            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(25 * mm, H - 45 * mm, f"Inhalt – Seite {page_num}")
            c.setFont("Helvetica", 10)
            y = H - 60 * mm
            for line in body_text.split("\n"):
                c.drawString(25 * mm, y, line)
                y -= 14

        body_p1 = (
            "Dieser Text ist auf Seite 1 und muss verglichen werden.\n"
            "Zeile 2: Auftragsnummer AUF-2026-00042\n"
            "Zeile 3: Lieferdatum 20.07.2026\n"
            "Zeile 4: Gesamtbetrag 1.234,56 EUR"
        )
        body_p2 = (
            "Dieser Text ist auf Seite 2 und muss ebenfalls verglichen werden.\n"
            "Zeile 2: Lieferbedingungen gemäß AGB\n"
            "Zeile 3: Zahlungsziel 14 Tage netto\n"
            "Zeile 4: Bankverbindung IBAN DE00 1234 5678 9012 3456 78"
        )

        for filename, date_s1, date_s2 in [
            ("ref.pdf", "01.07.2026 08:00", "01.07.2026 08:00"),
            ("cnd.pdf", "15.07.2026 14:30", "15.07.2026 14:30"),  # Datum anders
        ]:
            c = rl_canvas.Canvas(str(d / filename), pagesize=A4)
            draw_page_with_date(c, date_s1, body_p1, page_num=1)
            c.showPage()
            draw_page_with_date(c, date_s2, body_p2, page_num=2)
            c.showPage()
            c.save()

        if tc == "TC-E-001":
            write_readme(
                tc,
                "Region vom Vergleich ausschließen",
                "Das Druckdatum im Kopfbereich (Region x=0,y=792,w=200,h=50 in pt) "
                "unterscheidet sich. Mit exclude_region auf Seite 1 → kein Delta. "
                "Profil: exclude_region {page:1, x:0, y:770, w:200, h:55}",
                "Seite 1+2 mit Druckdatum 01.07.2026.",
                "Seite 1+2 mit Druckdatum 15.07.2026 (Datum in Ausschluss-Region).",
            )
        else:
            write_readme(
                tc,
                "Region-Ausschluss gilt nur für definierte Seite",
                "Gleiche Struktur wie TC-E-001. Der Ausschluss ist nur für Seite 1 "
                "konfiguriert. Auf Seite 2 liegt das Datum in der gleichen Position "
                "und muss als Delta erkannt werden (da exclude nur für page:1 gilt).",
                "Seite 1+2, Datum 01.07.2026 oben links.",
                "Seite 1+2, Datum 15.07.2026 oben links – Delta auf Seite 2 erwartet.",
            )


# ---------------------------------------------------------------------------
# TC-E-003  Mehrere Ausschluss-Regionen
# ---------------------------------------------------------------------------

def generate_tc_e_003() -> None:
    tc = "TC-E-003"
    d = fixture_dir(tc)

    def draw(path: Path, stamp: str, logo_text: str, footer: str, body: str) -> None:
        c = rl_canvas.Canvas(str(path), pagesize=A4)
        # Region 1: Logo oben rechts
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.darkblue)
        c.drawRightString(W - 15 * mm, H - 15 * mm, logo_text)

        # Region 2: Stempel Mitte-Rechts
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.red)
        c.drawString(W - 55 * mm, H / 2, stamp)

        # Region 3: Footer mit Datum
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        c.drawString(15 * mm, 12 * mm, footer)

        # Körpertext (wird verglichen)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)
        y = H - 45 * mm
        for line in body.split("\n"):
            c.drawString(25 * mm, y, line)
            y -= 14
        c.save()

    body = (
        "Vertragsbestätigung Nr. VB-2026-00099\n"
        "Vertragspartner: Muster AG, Frankfurt\n"
        "Leistungszeitraum: 01.08.2026 – 31.07.2027\n"
        "Monatliche Rate: 850,00 EUR\n"
        "Gesamtvolumen: 10.200,00 EUR"
    )

    draw(d / "ref.pdf",
         stamp="ORIGINAL",
         logo_text="Muster GmbH © 2025",
         footer="Gedruckt: 01.07.2026 | System: PrintServer-A",
         body=body)

    draw(d / "cnd.pdf",
         stamp="KOPIE",                            # Region 2 – anders
         logo_text="Muster GmbH © 2026",           # Region 1 – anders
         footer="Gedruckt: 20.07.2026 | System: PrintServer-B",  # Region 3 – anders
         body=body)                                # Inhalt identisch

    write_readme(
        tc,
        "Mehrere Ausschluss-Regionen",
        "Drei unterschiedliche Regionen (Logo, Stempel, Footer) haben abweichenden "
        "Inhalt. Mit drei konfigurierten exclude_regions → kein Delta. "
        "Der Körpertext ist identisch.",
        "Logo '2025', Stempel 'ORIGINAL', Footer mit Datum 01.07.2026.",
        "Logo '2026', Stempel 'KOPIE', Footer mit Datum 20.07.2026 – gleicher Körpertext.",
    )


# ---------------------------------------------------------------------------
# TC-G-001 / TC-G-002 / TC-G-003  Seitengruppen
# ---------------------------------------------------------------------------

def generate_tc_g_001_003() -> None:
    """Erzeugt ein Batch-PDF mit mehreren Dokumenten pro Datei."""

    def make_batch_pdf(path: Path, docs: list[dict]) -> None:
        """
        docs: Liste von {"type": str, "number": str, "amount": str, "pages": int}
        Jedes Dokument beginnt mit einer Titelzeile (Such-Pattern) und hat n Seiten.
        """
        c = rl_canvas.Canvas(str(path), pagesize=A4)
        for doc in docs:
            for page in range(doc["pages"]):
                c.setFont("Helvetica-Bold", 13)
                if page == 0:
                    # Erste Seite: Pattern-Text für Seitengruppen-Erkennung
                    c.drawString(25 * mm, H - 30 * mm,
                                 f"{doc['type']} Nr. {doc['number']}")
                    c.setFont("Helvetica", 10)
                    c.drawString(25 * mm, H - 45 * mm,
                                 f"Betrag: {doc['amount']}")
                    c.drawString(25 * mm, H - 58 * mm,
                                 f"Datum: 15.07.2026")
                else:
                    c.setFont("Helvetica", 10)
                    c.drawString(25 * mm, H - 30 * mm,
                                 f"{doc['type']} Nr. {doc['number']} – Seite {page + 1}")
                    c.drawString(25 * mm, H - 44 * mm,
                                 "Fortsetzung des Dokuments...")

                c.setFont("Helvetica", 7)
                c.setFillColor(colors.grey)
                c.drawString(25 * mm, 12 * mm,
                             f"Batch-Dokument | Seite {page + 1}/{doc['pages']}")
                c.setFillColor(colors.black)
                c.showPage()
        c.save()

    # TC-G-001 & TC-G-002: Batch mit Rechnungen und Mahnungen
    for tc in ("TC-G-001", "TC-G-002"):
        d = fixture_dir(tc)

        docs_ref = [
            {"type": "Rechnung", "number": "RE-2026-0001", "amount": "119,00 EUR", "pages": 1},
            {"type": "Mahnung",  "number": "MA-2026-0001", "amount": "119,00 EUR", "pages": 1},
            {"type": "Rechnung", "number": "RE-2026-0002", "amount": "238,00 EUR", "pages": 2},
            {"type": "Mahnung",  "number": "MA-2026-0002", "amount": "238,00 EUR", "pages": 1},
            {"type": "Rechnung", "number": "RE-2026-0003", "amount": "595,00 EUR", "pages": 1},
        ]
        docs_cnd = [
            {"type": "Rechnung", "number": "RE-2026-0001", "amount": "119,00 EUR", "pages": 1},
            {"type": "Mahnung",  "number": "MA-2026-0001", "amount": "119,00 EUR", "pages": 1},
            {"type": "Rechnung", "number": "RE-2026-0002", "amount": "238,00 EUR", "pages": 2},
            {"type": "Mahnung",  "number": "MA-2026-0002", "amount": "238,00 EUR", "pages": 1},
            {"type": "Rechnung", "number": "RE-2026-0003", "amount": "595,00 EUR", "pages": 1},
        ]

        make_batch_pdf(d / "ref.pdf", docs_ref)
        make_batch_pdf(d / "cnd.pdf", docs_cnd)

        if tc == "TC-G-001":
            write_readme(
                tc,
                "Seitengruppe per Such-Pattern identifizieren",
                "Batch-PDF mit 3 Rechnungen und 2 Mahnungen, abwechselnd. "
                "Pattern 'Rechnung Nr.*' bzw. 'Mahnung Nr.*' markiert jeweils den Start "
                "einer neuen Seitengruppe.",
                "Batch: RE-0001 (1S), MA-0001 (1S), RE-0002 (2S), MA-0002 (1S), RE-0003 (1S).",
                "Identische Struktur.",
            )
        else:
            write_readme(
                tc,
                "Nur bestimmte Seitengruppen vergleichen",
                "Gleiche Batch-PDFs wie TC-G-001. Mit group_filter=['Rechnung'] "
                "werden nur die 3 Rechnungen verglichen, die 2 Mahnungen ignoriert.",
                "Batch mit Rechnungen und Mahnungen.",
                "Identische Batch-Struktur.",
            )

    # TC-G-003: Seitengruppen mit unterschiedlichem Seitenumfang
    tc = "TC-G-003"
    d = fixture_dir(tc)

    docs_ref = [
        {"type": "Rechnung", "number": "RE-2026-0010", "amount": "350,00 EUR", "pages": 2},
        {"type": "Rechnung", "number": "RE-2026-0011", "amount": "780,00 EUR", "pages": 3},
    ]
    docs_cnd = [
        {"type": "Rechnung", "number": "RE-2026-0010", "amount": "350,00 EUR", "pages": 3},  # 1 Seite mehr
        {"type": "Rechnung", "number": "RE-2026-0011", "amount": "780,00 EUR", "pages": 4},  # 1 Seite mehr
    ]

    make_batch_pdf(d / "ref.pdf", docs_ref)
    make_batch_pdf(d / "cnd.pdf", docs_cnd)

    write_readme(
        tc,
        "Seitengruppen mit unterschiedlichem Seitenumfang",
        "Beide Batch-PDFs enthalten 2 Rechnungen mit identischem Inhalt, "
        "aber das cnd.pdf hat je eine Seite mehr (neuer Seitenumbruch). "
        "Kein inhaltliches Delta erwartet.",
        "RE-0010: 2 Seiten, RE-0011: 3 Seiten.",
        "RE-0010: 3 Seiten, RE-0011: 4 Seiten – gleicher Inhalt.",
    )


# ---------------------------------------------------------------------------
# TC-O-001 / TC-O-002  OCR-Fixtures
# ---------------------------------------------------------------------------

def _render_text_as_scanned_page(path: Path, lines: list[str]) -> None:
    """Rendert Text via Pillow auf ein Bild und bettet dieses Bild ohne
    Textlayer in ein einseitiges PDF ein – echte "gescannte" Seite, kein
    nativer Text, damit OCR (Tesseract) tatsächlich erforderlich ist."""
    from PIL import Image, ImageDraw, ImageFont

    px_w, px_h = 1600, 2262  # ~ A4 bei 200dpi
    img = Image.new("RGB", (px_w, px_h), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
    except OSError:
        font = ImageFont.load_default()

    y = 150
    for line in lines:
        draw.text((120, y), line, fill="black", font=font)
        y += 70

    img_path = path.with_suffix(".png")
    img.save(img_path)

    c = rl_canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(str(img_path), 0, 0, width=W, height=H)
    c.showPage()
    c.save()
    img_path.unlink()


def generate_tc_o_001() -> None:
    """TC-O-001: reines Scan-PDF (Text als eingebettetes Bild, kein
    nativer Textlayer) – erfordert echtes OCR zur Extraktion."""
    tc = "TC-O-001"
    d = fixture_dir(tc)

    lines = [
        "Auftragsbestaetigung Nr. AB-2026-00099",
        "Kundenname: Mustermann, Max",
        "Lieferdatum: 25.07.2026",
        "Gesamtbetrag: 1234,56 EUR",
    ]
    _render_text_as_scanned_page(d / "ref.pdf", lines)
    _render_text_as_scanned_page(d / "cnd.pdf", lines)

    write_readme(
        tc,
        "Gescannten Text via OCR erkennen",
        "Beide PDFs bestehen aus einer eingebetteten Bitmap (Pillow-Rendering) "
        "ohne Textlayer. PyMuPDF liefert für diese Seite leeren Text; "
        "engine.ocr_extractor muss den Inhalt via Tesseract (deu) erkennen.",
        "Gerenderte Scan-Seite mit Auftragsdaten.",
        "Identische gerenderte Scan-Seite.",
    )


def generate_tc_o_002() -> None:
    """TC-O-002: gemischtes PDF – Seite 1 nativ, Seite 2 als echtes
    Bild ohne Textlayer (P2, hier nur zur Vollständigkeit vorbereitet)."""
    tc = "TC-O-002"
    d = fixture_dir(tc)

    c = rl_canvas.Canvas(str(d / "ref.pdf"), pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(25 * mm, H - 30 * mm, "Seite 1 – nativer Text (kein OCR)")
    c.setFont("Helvetica", 10)
    for i, line in enumerate(["Auftragsbestätigung Nr. AB-2026-00099", "Kundenname: Mustermann, Max"]):
        c.drawString(25 * mm, H - 50 * mm - i * 14, line)
    c.showPage()
    c.save()

    _render_text_as_scanned_page(
        d / "_page2_only.pdf",
        ["SCAN-SEITE 2", "Lieferdatum: 25.07.2026", "Gesamtbetrag: 1234,56 EUR"],
    )

    doc = fitz.open(str(d / "ref.pdf"))
    page2_doc = fitz.open(str(d / "_page2_only.pdf"))
    doc.insert_pdf(page2_doc)
    doc.saveIncr()
    doc.close()
    page2_doc.close()
    (d / "_page2_only.pdf").unlink()

    import shutil
    shutil.copy(d / "ref.pdf", d / "cnd.pdf")

    write_readme(
        tc,
        "Gemischtes PDF: nativer + gescannter Text",
        "Seite 1 enthält nativen Text (direkt extrahierbar). Seite 2 ist eine "
        "echte Bitmap ohne Textlayer. Beide Verfahren müssen kombiniert "
        "funktionieren.",
        "Seite 1 nativ, Seite 2 als echter Scan.",
        "Identisch mit ref.pdf.",
    )


# ---------------------------------------------------------------------------
# TC-P-001 / TC-P-002  Profile
# ---------------------------------------------------------------------------

def generate_tc_p_001_002() -> None:
    import json

    for tc in ("TC-P-001", "TC-P-002"):
        d = fixture_dir(tc)

        # Wiederverwendung von TC-T-004-PDFs (echter Unterschied)
        simple_pdf(d / "ref.pdf", [["Betrag: 100 EUR"]], title=f"{tc} ref")
        simple_pdf(d / "cnd.pdf", [["Betrag: 200 EUR"]], title=f"{tc} cnd")

    # Valides Profil für TC-P-001
    valid_profile = {
        "version": "1.0",
        "case_sensitive": False,
        "normalize_whitespace": True,
        "exclude_regions": [
            {"page": 1, "x": 0, "y": 770, "width": 200, "height": 55}
        ],
        "page_groups": [
            {"pattern": "Rechnung Nr\\..*", "name": "Rechnung"}
        ],
        "report_format": "pdf",
        "ocr": {
            "enabled": False,
            "confidence_threshold": 0.85
        }
    }
    (fixture_dir("TC-P-001") / "profile.json").write_text(
        json.dumps(valid_profile, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    write_readme(
        "TC-P-001",
        "Valides JSON-Profil laden",
        "profile.json mit vollständig korrekter Struktur. load_profile() muss "
        "das Profil ohne Fehler laden.",
        "Einseitig mit 'Betrag: 100 EUR'.",
        "Einseitig mit 'Betrag: 200 EUR'.",
    )

    # Invalides Profil für TC-P-002 (Syntaxfehler)
    invalid_profile_text = """{
  "version": "1.0",
  "case_sensitive": false,
  "exclude_regions": [
    {"page": 1, "x": 0, "y": 770  <- SYNTAXFEHLER: fehlendes Komma und }
  ]
}"""
    (fixture_dir("TC-P-002") / "profile_invalid.json").write_text(
        invalid_profile_text,
        encoding="utf-8"
    )

    write_readme(
        "TC-P-002",
        "Invalides JSON-Profil – Fehlerbehandlung",
        "profile_invalid.json enthält einen Syntaxfehler. load_profile() muss "
        "eine ValidationError-Exception mit sprechendem Fehlertext werfen.",
        "Einseitig mit 'Betrag: 100 EUR'.",
        "Einseitig mit 'Betrag: 200 EUR'.",
    )


# ---------------------------------------------------------------------------
# TC-B-001 / TC-B-002 / TC-B-003  Batch-Fixtures
# ---------------------------------------------------------------------------

def generate_tc_b_001_003() -> None:
    import csv, json

    # TC-B-001: Dateiliste mit 10 Paaren
    tc = "TC-B-001"
    d = fixture_dir(tc)
    pairs_dir = d / "pairs"
    pairs_dir.mkdir(exist_ok=True)

    filelist_rows = []
    for i in range(1, 11):
        ref_path = pairs_dir / f"doc_{i:02d}_ref.pdf"
        cnd_path = pairs_dir / f"doc_{i:02d}_cnd.pdf"
        text = [f"Dokument {i:02d}: Auftragsnummer AU-2026-{i:04d}",
                f"Betrag: {i * 100},00 EUR"]
        simple_pdf(ref_path, [text])
        simple_pdf(cnd_path, [text])
        filelist_rows.append([str(ref_path), str(cnd_path)])

    with open(d / "filelist.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ref", "cnd"])
        writer.writerows(filelist_rows)

    write_readme(
        tc,
        "Batch per Dateiliste – alle Paare verarbeitet",
        "filelist.csv mit 10 Dateipaaren, alle vorhanden und inhaltlich identisch.",
        "10 ref-PDFs (pairs/doc_01_ref.pdf … doc_10_ref.pdf).",
        "10 cnd-PDFs (pairs/doc_01_cnd.pdf … doc_10_cnd.pdf).",
    )

    # TC-B-002: Dateiliste mit einer fehlenden Datei
    tc = "TC-B-002"
    d = fixture_dir(tc)
    pairs_dir = d / "pairs"
    pairs_dir.mkdir(exist_ok=True)

    filelist_rows = []
    for i in range(1, 6):
        ref_path = pairs_dir / f"doc_{i:02d}_ref.pdf"
        cnd_path = pairs_dir / f"doc_{i:02d}_cnd.pdf"
        text = [f"Dokument {i:02d}"]
        simple_pdf(ref_path, [text])
        if i != 3:  # Datei 03_cnd.pdf absichtlich nicht erzeugen
            simple_pdf(cnd_path, [text])
        filelist_rows.append([str(ref_path), str(cnd_path)])

    with open(d / "filelist.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ref", "cnd"])
        writer.writerows(filelist_rows)

    write_readme(
        tc,
        "Batch – fehlende Datei wird protokolliert",
        "filelist.csv mit 5 Paaren. doc_03_cnd.pdf fehlt absichtlich. "
        "Der Batch soll weiterlaufen und den Fehler protokollieren.",
        "5 ref-PDFs (alle vorhanden).",
        "4 von 5 cnd-PDFs (doc_03_cnd.pdf fehlt).",
    )

    # TC-B-003: XMP-Metadaten-Matching
    tc = "TC-B-003"
    d = fixture_dir(tc)

    def make_pdf_with_xmp(path: Path, doc_id: str, variant: str) -> None:
        """PDF mit eingebetteter XMP-Document-ID."""
        c = rl_canvas.Canvas(str(path), pagesize=A4)
        c.setAuthor("PaperTrail-Fixture-Generator")
        c.setSubject(f"XMP-Test | doc_id={doc_id}")
        c.setKeywords(f"document_id:{doc_id}")  # Simuliert XMP Document-ID
        c.setFont("Helvetica", 10)
        c.drawString(25*mm, H-30*mm, f"Document-ID: {doc_id}")
        c.drawString(25*mm, H-44*mm, f"Variante: {variant}")
        c.save()

    for i in range(1, 11):
        doc_id = f"DOC-2026-{i:04d}"
        make_pdf_with_xmp(d / f"ref_{i:02d}.pdf", doc_id, "ref")
        make_pdf_with_xmp(d / f"cnd_{i:02d}.pdf", doc_id, "cnd")

    write_readme(
        tc,
        "Batch per XMP-Metadaten (Document-ID)",
        "20 PDFs (10 ref + 10 cnd). Jedes Pärchen teilt dieselbe XMP Document-ID "
        "(im Keywords-Feld als 'document_id:<id>' hinterlegt). "
        "batch_compare_by_xmp() muss die 10 Paare korrekt zuordnen.",
        "ref_01.pdf … ref_10.pdf, je mit Document-ID DOC-2026-0001 … 0010.",
        "cnd_01.pdf … cnd_10.pdf, gleiche Document-IDs.",
    )


# ---------------------------------------------------------------------------
# TC-S-001 / TC-S-002  Privacy-Fixtures (einfache PDFs)
# ---------------------------------------------------------------------------

def generate_tc_s_001_002() -> None:
    for tc in ("TC-S-001", "TC-S-002"):
        d = fixture_dir(tc)
        text = [
            "Vertrauliches Dokument – nur für interne Zwecke.",
            "Dieser Text darf das System nicht verlassen.",
            "Kundennummer: KD-PRIVACY-00001",
            "Betrag: 9.999,99 EUR",
        ]
        simple_pdf(d / "ref.pdf", [text])
        simple_pdf(d / "cnd.pdf", [text])

        if tc == "TC-S-001":
            write_readme(
                tc,
                "Keine Netzwerkverbindung während Verarbeitung",
                "Standard-PDF-Pärchen. Der Systemtest prüft via Netzwerk-Monitor, "
                "dass während des Vergleichs kein ausgehender Traffic entsteht.",
                "Einseitig mit vertraulichem Beispieltext.",
                "Identisch mit ref.pdf.",
            )
        else:
            write_readme(
                tc,
                "Temporäre Dateien werden bereinigt",
                "Standard-PDF-Pärchen. Der Systemtest prüft, dass nach dem Vergleich "
                "keine temporären Dateien mit Dokumenteninhalt im /tmp-Verzeichnis "
                "verbleiben.",
                "Einseitig mit vertraulichem Beispieltext.",
                "Identisch mit ref.pdf.",
            )


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

GENERATORS = [
    ("TC-X-001", generate_tc_x_001),
    ("TC-X-002", generate_tc_x_002),
    ("TC-T-001", generate_tc_t_001),
    ("TC-T-002", generate_tc_t_002),
    ("TC-T-003", generate_tc_t_003),
    ("TC-T-004", generate_tc_t_004),
    ("TC-T-005", generate_tc_t_005),
    ("TC-T-006", generate_tc_t_006),
    ("TC-T-007", generate_tc_t_007),
    ("TC-T-008", generate_tc_t_008),
    ("TC-E-001 + TC-E-002", generate_tc_e_001_002),
    ("TC-E-003", generate_tc_e_003),
    ("TC-G-001 – TC-G-003", generate_tc_g_001_003),
    ("TC-O-001", generate_tc_o_001),
    ("TC-O-002", generate_tc_o_002),
    ("TC-P-001 + TC-P-002", generate_tc_p_001_002),
    ("TC-B-001 – TC-B-003", generate_tc_b_001_003),
    ("TC-S-001 + TC-S-002", generate_tc_s_001_002),
]


def main() -> None:
    print(f"Fixture-Generator | Ausgabe: {FIXTURES_DIR}\n")
    print(f"{'TC-ID':<30} {'Status'}")
    print("-" * 50)

    ok = 0
    for label, fn in GENERATORS:
        try:
            fn()
            print(f"  {label:<28} ✓")
            ok += 1
        except Exception as exc:
            print(f"  {label:<28} ✗  {exc}")

    print("-" * 50)
    print(f"\n{ok}/{len(GENERATORS)} Fixture-Gruppen erfolgreich erzeugt.")

    # Übersicht der erzeugten Dateien
    all_files = sorted(FIXTURES_DIR.rglob("*.pdf"))
    json_files = sorted(FIXTURES_DIR.rglob("*.json"))
    csv_files  = sorted(FIXTURES_DIR.rglob("*.csv"))

    print(f"\nErzeugte Dateien:")
    print(f"  PDF:  {len(all_files)}")
    print(f"  JSON: {len(json_files)}")
    print(f"  CSV:  {len(csv_files)}")


if __name__ == "__main__":
    main()
