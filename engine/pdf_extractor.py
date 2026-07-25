"""PDF-Textextraktion: liefert pro Seite einen normalisierten Text-String,
passend als Eingabe für engine.text_comparator.compare().

Nutzt PyMuPDF (fitz) als primäre Extraktions-Engine (Koordinaten, Spalten)
und pdfplumber ergänzend für Tabellenerkennung, siehe
doc/PaperTrailCompare_Architekturspezifikation.docx Abschnitt 4/6.2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import fitz
import pdfplumber

from engine.profile_loader import Profile

_TEXT_BLOCK_TYPE = 0
_COLUMN_BUCKET_PT = 50  # Blockbreite-Toleranz zur Spaltenerkennung

# PyMuPDF-Textblock: (x0, y0, x1, y1, text, block_no, block_type)
TextBlock = Tuple[float, float, float, float, str, int, int]

# rawdict-Zeichen-Tupel für die Wortrekonstruktion: (char, bbox, font, size)
RawChar = Tuple[str, Tuple[float, float, float, float], str, float]

# Anteil der kalibrierten Space-Breite, unterhalb dessen ein rawdict-Leerzeichen-
# Eintrag als von PyMuPDFs Lücken-Heuristik synthetisiert (statt real) gilt bzw.
# oberhalb dessen eine Glyphenlücke als Wortgrenze gewertet wird. Empirisch an
# echten Dokumenten belegt (siehe CLAUDE-Diagnose-Session): synthetische
# Platzhalter lagen bei ca. 6 % der Space-Breite, echte Leerzeichen bei 82-100 %
# - der große Abstand dazwischen lässt viel Spielraum für diesen Schwellwert.
_SPACEWIDTH_THRESHOLD_FRACTION = 0.4

_MIN_REAL_SPACE_SAMPLES = 3  # weniger echte Leerzeichen gelten als nicht belastbar
_MAX_REAL_SPACE_COEFF_OF_VARIATION = 0.25  # zu breite Streuung -> vermutlich gemischte Population

# Echte Space-Glyphen sind i.d.R. nicht drastisch schmaler als der schmalste
# echte Buchstabe derselben Schrift. An echten Dokumenten belegt: eine
# Type3-Schrift ohne Space-Glyph lieferte c==' '-Platzhalter mit 0,24pt
# Breite bei einer schmalsten echten Glyphe von 1,68pt (Verhältnis ~14 %) -
# perfekt gleichmäßig (niedrige Streuung) und wäre ohne dieses Kriterium
# fälschlich als "echte Leerzeichen" akzeptiert worden. Eine normale Schrift
# mit echten Leerzeichen lag dagegen bei ~91 % (1,84pt Space vs. 2,02pt
# schmalste Glyphe). Der große Abstand zwischen 14 % und 91 % erlaubt hier
# einen robusten Schwellwert.
_MIN_SPACEWIDTH_TO_MIN_GLYPH_FRACTION = 0.4

_MIN_GAP_SAMPLES = 20  # weniger Lückenmessungen reichen nicht für eine Elbow-Analyse
_MIN_ELBOW_CLUSTER_SIZE = 5  # beide Cluster müssen so viele Messwerte haben
_MIN_ELBOW_CLUSTER_RATIO = 3.0  # High-Cluster muss mindestens so viel größer sein als Low-Cluster


@dataclass
class SpacewidthCalibration:
    """Ergebnis der Space-Breiten-Kalibrierung für eine (Font, Größe)-Kombination.

    spacewidth ist None, wenn keine belastbare Kalibrierung möglich war - dann
    wird für diese Schrift NICHT rekonstruiert, sondern die native rawdict-
    Zeichenkette unverändert übernommen (lieber ein unveränderter Bereich als
    eine geratene, möglicherweise falsche Wortgrenze)."""

    font: str
    size: float
    spacewidth: Optional[float]
    source: str  # "real_spaces" | "elbow" | "insufficient_data"
    sample_count: int
    criterion_met: bool


def get_text_blocks(page: "fitz.Page") -> List[TextBlock]:
    """Liefert die nicht-leeren Textblöcke einer Seite, unsortiert.

    Wiederverwendbarer Baustein für andere Schicht-1-Module (z.B.
    region_filter), die dieselbe Block-Extraktion benötigen, aber vor der
    Sortierung noch Blöcke herausfiltern müssen (Regionen-Ausschluss)."""
    return [
        b for b in page.get_text("blocks")
        if b[6] == _TEXT_BLOCK_TYPE and b[4].strip()
    ]


def sort_blocks_columns(blocks: Sequence[TextBlock]) -> List[TextBlock]:
    """Sortiert Textblöcke spaltenweise (links vor rechts), statt strikt
    zeilenweise – nötig für mehrspaltige Layouts (TC-T-007)."""
    return sorted(blocks, key=lambda b: (round(b[0] / _COLUMN_BUCKET_PT), round(b[1])))


def join_block_text(blocks: Sequence[TextBlock]) -> str:
    """Fügt die Texte bereits sortierter Blöcke zu einem Seitentext zusammen."""
    return "\n".join(b[4].strip() for b in blocks)


def _extract_page_text_columns(page: "fitz.Page") -> str:
    """Liest den Text einer Seite spaltenweise (links vor rechts), statt
    strikt zeilenweise."""
    return join_block_text(sort_blocks_columns(get_text_blocks(page)))


def _linearize_tables(tables: List[List[List[Optional[str]]]]) -> str:
    """Wandelt erkannte Tabellen (Zeilen aus Zellen) in Text um, zeilenweise,
    layoutunabhängig von Spaltenbreiten/Farbschema (TC-T-008)."""
    lines: List[str] = []
    for table in tables:
        for row in table:
            cells = [cell.strip() for cell in row if cell and cell.strip()]
            if cells:
                lines.append(" ".join(cells))
    return "\n".join(lines)


def _iter_rawdict_lines(doc: "fitz.Document"):
    """Iteriert alle horizontalen Textzeilen aller Seiten als rawdict-Zeilen-
    Dicts. Vertikale/rotierte Zeilen (dir != (1,0)/(-1,0)) werden ausgelassen -
    die Wortrekonstruktion beschränkt sich bewusst auf den Normalfall."""
    for page in doc:
        rawdict = page.get_text("rawdict")
        for block in rawdict.get("blocks", []):
            if block.get("type") != _TEXT_BLOCK_TYPE:
                continue
            for line in block.get("lines", []):
                direction = line.get("dir", (1.0, 0.0))
                if abs(direction[1]) > 1e-6:
                    continue
                yield line


def _flatten_line_chars(line) -> List[RawChar]:
    flat: List[RawChar] = []
    for span in line.get("spans", []):
        font = span.get("font")
        size = span.get("size")
        for ch in span.get("chars", []):
            flat.append((ch["c"], ch["bbox"], font, size))
    return flat


def _collect_font_measurements(doc: "fitz.Document") -> Dict[Tuple[str, float], dict]:
    """Sammelt pro (Font, Größe) die Breiten echter Leerzeichen-Einträge, die
    Breiten der Nicht-Leerzeichen-Glyphen (als Plausibilitäts-Referenz) sowie
    die horizontalen Lücken zwischen aufeinanderfolgenden Nicht-Leerzeichen
    innerhalb derselben Zeile - Rohdaten für calibrate_spacewidths()."""
    measurements: Dict[Tuple[str, float], dict] = {}

    def bucket(font, size):
        key = (font, size)
        if key not in measurements:
            measurements[key] = {"real_space_widths": [], "nonspace_widths": [], "gaps": []}
        return measurements[key]

    for line in _iter_rawdict_lines(doc):
        flat = _flatten_line_chars(line)
        prev = None
        for char, bbox, font, size in flat:
            if char == " ":
                bucket(font, size)["real_space_widths"].append(bbox[2] - bbox[0])
                prev = None  # Lücken über ein Leerzeichen hinweg sind nicht "intra-word"
                continue
            bucket(font, size)["nonspace_widths"].append(bbox[2] - bbox[0])
            if prev is not None and prev[2] == font and prev[3] == size:
                gap = bbox[0] - prev[1][2]
                bucket(font, size)["gaps"].append(gap)
            prev = (char, bbox, font, size)

    return measurements


def _calibrate_from_gaps(gaps: List[float]) -> Tuple[Optional[float], bool]:
    """Elbow-Analyse: größter Sprung zwischen sortierten Lückenwerten, der
    beide Seiten in ausreichend große, ausreichend unterschiedliche Cluster
    teilt. Gibt (kalibrierte_spacewidth_oder_None, kriterium_erfuellt) zurück."""
    if len(gaps) < _MIN_GAP_SAMPLES:
        return None, False

    sorted_gaps = sorted(gaps)
    best_idx = None
    best_diff = -1.0
    for i in range(_MIN_ELBOW_CLUSTER_SIZE - 1, len(sorted_gaps) - _MIN_ELBOW_CLUSTER_SIZE):
        diff = sorted_gaps[i + 1] - sorted_gaps[i]
        if diff > best_diff:
            best_diff = diff
            best_idx = i

    if best_idx is None:
        return None, False

    low_cluster = sorted_gaps[: best_idx + 1]
    high_cluster = sorted_gaps[best_idx + 1 :]
    low_max = low_cluster[-1]
    high_min = high_cluster[0]

    if low_max <= 0:
        # Referenzpunkt für das Verhältnis wäre 0/negativ - Verhältnis-Kriterium
        # unten unbrauchbar; stattdessen absoluten Mindestabstand verlangen.
        criterion_met = high_min >= 1.0
    else:
        criterion_met = (high_min / low_max) >= _MIN_ELBOW_CLUSTER_RATIO

    if not criterion_met:
        return None, False

    return (low_max + high_min) / 2, True


def calibrate_spacewidths(doc: "fitz.Document") -> Dict[Tuple[str, float], SpacewidthCalibration]:
    """Ermittelt je (Font, Größe) eine belastbare Space-Breite für die
    Wortrekonstruktion (siehe Modul-Docstring von get_text_blocks_reconstructed).

    Zwei Quellen, in dieser Reihenfolge:
    1. Echte, im Content-Stream vorhandene Leerzeichen-Glyphen dieser Schrift
       (zuverlässigste Quelle, falls genug vorhanden und nicht zu breit gestreut).
    2. Fallback per Elbow-Analyse der Glyphenabstände (für Schriften ganz ohne
       Space-Glyph, z.B. Type3-Schriften von Großrechner-Drucksystemen).

    Ist keine der beiden Quellen belastbar, bleibt spacewidth=None und
    criterion_met=False - für diese Schrift wird nicht rekonstruiert."""
    measurements = _collect_font_measurements(doc)
    calibrations: Dict[Tuple[str, float], SpacewidthCalibration] = {}

    for (font, size), data in measurements.items():
        nonspace_widths = data["nonspace_widths"]
        min_glyph_width = min(nonspace_widths) if nonspace_widths else None

        real_widths = data["real_space_widths"]
        if len(real_widths) >= _MIN_REAL_SPACE_SAMPLES:
            mean_width = sum(real_widths) / len(real_widths)
            variance = sum((w - mean_width) ** 2 for w in real_widths) / len(real_widths)
            coeff_of_variation = (variance ** 0.5 / mean_width) if mean_width else float("inf")
            plausible_vs_glyphs = (
                min_glyph_width is None
                or mean_width >= _MIN_SPACEWIDTH_TO_MIN_GLYPH_FRACTION * min_glyph_width
            )
            if (
                mean_width > 0
                and coeff_of_variation <= _MAX_REAL_SPACE_COEFF_OF_VARIATION
                and plausible_vs_glyphs
            ):
                calibrations[(font, size)] = SpacewidthCalibration(
                    font=font, size=size, spacewidth=mean_width, source="real_spaces",
                    sample_count=len(real_widths), criterion_met=True,
                )
                continue

        spacewidth, criterion_met = _calibrate_from_gaps(data["gaps"])
        if criterion_met and min_glyph_width is not None and spacewidth < _MIN_SPACEWIDTH_TO_MIN_GLYPH_FRACTION * min_glyph_width:
            spacewidth, criterion_met = None, False
        calibrations[(font, size)] = SpacewidthCalibration(
            font=font, size=size, spacewidth=spacewidth if criterion_met else None,
            source="elbow" if criterion_met else "insufficient_data",
            sample_count=len(data["gaps"]), criterion_met=criterion_met,
        )

    return calibrations


def _reconstruct_line_text(line, calibration: Dict[Tuple[str, float], SpacewidthCalibration]) -> str:
    """Baut den Text einer rawdict-Zeile selbst zusammen: verwirft von
    PyMuPDFs Lücken-Heuristik synthetisierte Leerzeichen-Platzhalter und setzt
    Wortgrenzen anhand echter Glyphenabstände neu (siehe calibrate_spacewidths).
    Schriften ohne belastbare Kalibrierung bleiben unverändert (native
    rawdict-Zeichenkette), um kein Wort anhand eines geratenen Schwellwerts
    falsch zu zerlegen."""
    flat = _flatten_line_chars(line)
    if not flat:
        return ""

    if not all(calibration.get((font, size), SpacewidthCalibration(font, size, None, "insufficient_data", 0, False)).criterion_met for _, _, font, size in flat):
        return "".join(char for char, _, _, _ in flat)

    kept: List[RawChar] = []
    for char, bbox, font, size in flat:
        if char == " ":
            spacewidth = calibration[(font, size)].spacewidth
            width = bbox[2] - bbox[0]
            if width < _SPACEWIDTH_THRESHOLD_FRACTION * spacewidth:
                continue
        kept.append((char, bbox, font, size))

    out: List[str] = []
    prev: Optional[RawChar] = None
    for char, bbox, font, size in kept:
        if prev is not None and prev[0] != " " and char != " ":
            spacewidth = calibration[(prev[2], prev[3])].spacewidth
            gap = bbox[0] - prev[1][2]
            if gap > _SPACEWIDTH_THRESHOLD_FRACTION * spacewidth:
                out.append(" ")
        out.append(char)
        prev = (char, bbox, font, size)
    return "".join(out)


def get_text_blocks_reconstructed(
    page: "fitz.Page", calibration: Dict[Tuple[str, float], SpacewidthCalibration]
) -> List[TextBlock]:
    """Wie get_text_blocks(), liefert aber Blocktext über die eigene
    Wortrekonstruktion (_reconstruct_line_text) statt über rawdicts eigene,
    von der Leerzeichen-Heuristik betroffene Zeichenverkettung. Block- und
    Zeilengeometrie stammen unverändert aus rawdict (siehe Modul-Docstring)."""
    rawdict = page.get_text("rawdict")
    blocks: List[TextBlock] = []
    for block_no, block in enumerate(rawdict.get("blocks", [])):
        if block.get("type") != _TEXT_BLOCK_TYPE:
            continue
        lines_text = [_reconstruct_line_text(line, calibration) for line in block.get("lines", [])]
        text = "\n".join(lines_text) + "\n"
        if not text.strip():
            continue
        x0, y0, x1, y1 = block["bbox"]
        blocks.append((x0, y0, x1, y1, text, block_no, _TEXT_BLOCK_TYPE))
    return blocks


def _extract_page_text_columns_reconstructed(
    page: "fitz.Page", calibration: Dict[Tuple[str, float], SpacewidthCalibration]
) -> str:
    return join_block_text(sort_blocks_columns(get_text_blocks_reconstructed(page, calibration)))


def _extract_pages_reconstructed(pdf_path: str) -> List[str]:
    """Wie extract_pages(), nutzt für Nicht-Tabellenseiten aber die eigene
    Wortrekonstruktion statt PyMuPDFs Leerzeichen-Heuristik. Tabellenerkennung
    (pdfplumber) bleibt unverändert und hat weiterhin Vorrang, wie in
    extract_pages() - siehe Plan Punkt (e)."""
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        calibration = calibrate_spacewidths(doc)
        with pdfplumber.open(pdf_path) as plumber_pdf:
            for page_index, page in enumerate(doc):
                plumber_page = plumber_pdf.pages[page_index]
                tables = plumber_page.extract_tables()
                if tables:
                    pages_text.append(_linearize_tables(tables))
                else:
                    pages_text.append(_extract_page_text_columns_reconstructed(page, calibration))
    finally:
        doc.close()
    return pages_text


def extract_pages(pdf_path: str) -> List[str]:
    """Extrahiert den Text jeder Seite eines PDFs als eigenen String.

    Enthält eine Seite Tabellen, wird deren Inhalt zeilenweise linearisiert;
    andernfalls wird der Fließtext spaltenbewusst gelesen.
    """
    pages_text: List[str] = []
    doc = fitz.open(pdf_path)
    try:
        with pdfplumber.open(pdf_path) as plumber_pdf:
            for page_index, page in enumerate(doc):
                plumber_page = plumber_pdf.pages[page_index]
                tables = plumber_page.extract_tables()
                if tables:
                    pages_text.append(_linearize_tables(tables))
                else:
                    pages_text.append(_extract_page_text_columns(page))
    finally:
        doc.close()
    return pages_text


def extract_pages_for_profile(
    pdf_path: str, profile: Optional[Profile]
) -> Tuple[List[str], bool]:
    """Wie extract_pages(), nutzt aber den OCR-Fallback aus ocr_extractor
    (Tesseract), sobald profile.ocr.enabled=True ist - z.B. für gescannte
    Seiten ohne nativen Textlayer.

    extract_pages() selbst bleibt unverändert (schneller Pfad ohne
    Profilbezug); diese Funktion ist der zusätzliche, profilbewusste
    Einstiegspunkt für Aufrufer (CLI, Batch-Verarbeitung), die wissen
    müssen, ob für den Report tatsächlich OCR verwendet wurde.

    Rückgabe: (Seitentexte, ocr_used).
    """
    if profile is not None and profile.ocr.enabled:
        from engine.ocr_extractor import extract_pages_with_ocr_fallback
        return extract_pages_with_ocr_fallback(pdf_path)
    if profile is not None and profile.text_extraction == "reconstruct":
        return _extract_pages_reconstructed(pdf_path), False
    return extract_pages(pdf_path), False
