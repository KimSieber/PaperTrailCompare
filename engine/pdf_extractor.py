# file:    engine/pdf_extractor.py
# purpose: PDF text extraction with column-aware sorting, table linearization
#          (pdfplumber), spacewidth calibration for Type3 fonts, and exclude-
#          region filtering. Central extraction entry point for all compare paths.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""PDF-Textextraktion: liefert pro Seite einen normalisierten Text-String,
passend als Eingabe für engine.text_comparator.compare().

Nutzt PyMuPDF (pymupdf) als primäre Extraktions-Engine (Koordinaten, Spalten)
und pdfplumber ergänzend für Tabellenerkennung, siehe
doc/PaperTrailCompare_Architekturspezifikation.docx Abschnitt 4/6.2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf
import pdfplumber

from engine.profile_loader import Profile, CompareRegion

_TEXT_BLOCK_TYPE = 0
_COLUMN_BUCKET_PT = 50  # Blockbreite-Toleranz zur Spaltenerkennung

_SPLIT_THRESHOLD_PT = 300  # Blöcke breiter als das sind Kandidaten für split_wide_blocks()
_SPLIT_GAP_THRESHOLD_PT = 30  # Lücke zwischen zwei nach x0 sortierten Zeilen, ab der eine neue Spalte beginnt

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


@dataclass
class Region:
    """Koordinatenbasierte Ausschluss-Region (PyMuPDF-Koordinaten, Ursprung
    oben links, y wächst nach unten). Lebt hier statt in engine.region_filter,
    weil pdf_extractors eigene block-basierte Extraktionspfade (native,
    reconstruct) sie direkt anwenden müssen, um profile.exclude_regions
    tatsächlich wirken zu lassen (siehe extract_pages_for_profile);
    engine.region_filter importiert diese Klasse von hier und exportiert
    sie unter ihrem angestammten Namen weiter (TC-E-001 ff.)."""

    page: int  # 1-basiert
    x: float
    y: float
    w: float
    h: float
    page_from: Optional[int] = None  # ab Seite N bis Dokumentende (siehe Block 2 Matching)

    def overlaps(self, bbox: Sequence[float]) -> bool:
        x0, y0, x1, y1 = bbox
        return not (
            x1 <= self.x
            or x0 >= self.x + self.w
            or y1 <= self.y
            or y0 >= self.y + self.h
        )


def _region_applies_to_page(region: Region, page_num: int) -> bool:
    """Wildcard-Matching für Ausschluss-Regionen: page=0 wirkt auf jeder
    Seite, page=N nur auf Seite N, page_from=N auf Seite N bis
    Dokumentende. Zentrale Stelle für dieses Matching - wird von jedem Ort
    genutzt, der Regionen einer Seite zuordnet (filter_blocks_by_regions,
    _warn_if_table_page_has_regions, ocr_extractor._mask_regions_on_image
    und der Fallback-Gate in extract_pages_with_ocr_fallback)."""
    if region.page is not None:
        return region.page == 0 or region.page == page_num
    if region.page_from is not None:
        return page_num >= region.page_from
    return False  # sollte nach load_profile-Validierung nicht vorkommen


def filter_blocks_by_regions(
    blocks: Sequence[TextBlock], page_num: int, regions: Sequence[Region]
) -> List[TextBlock]:
    """Entfernt Textblöcke, die eine für page_num definierte Region
    überlappen (TC-E-001: Ausschluss, TC-E-002: nur für die definierte
    Seite). Regionen für andere Seiten bleiben wirkungslos."""
    page_regions = [r for r in regions if _region_applies_to_page(r, page_num)]
    if not page_regions:
        return list(blocks)
    return [b for b in blocks if not any(r.overlaps(b[:4]) for r in page_regions)]


def _compare_region_overlaps(region: CompareRegion, bbox: Sequence[float]) -> bool:
    """Wie Region.overlaps, aber für CompareRegion (x/y/width/height statt
    x/y/w/h) - eigene Methode statt Wiederverwendung, weil CompareRegion in
    profile_loader lebt und keine overlaps()-Methode besitzt (keine
    Modulabhängigkeit von profile_loader auf pdf_extractor)."""
    x0, y0, x1, y1 = bbox
    return not (
        x1 <= region.x
        or x0 >= region.x + region.width
        or y1 <= region.y
        or y0 >= region.y + region.height
    )


def check_compare_region_condition(text: str, condition: str) -> Optional[Tuple[str, str]]:
    """Whitespace-freier condition-Abgleich für compare_regions - gemeinsame
    Stelle für BEIDE Extraktionspfade (nativer Text: separate_compare_region_blocks
    hier; OCR-Zweig: ocr_extractor.extract_pages_with_ocr_fallback), damit
    beide exakt dieselbe Semantik verwenden (siehe
    docs/prompt_table_regions_ocr_branch.md - vorher lag dieser Abgleich nur
    inline in separate_compare_region_blocks, der OCR-Zweig hatte gar keinen).

    Case-sensitiver Teilstring-Vergleich, aber JEGLICHER Whitespace wird vor
    dem Vergleich entfernt (nicht nur auf ein Leerzeichen kollabiert) -
    Type3-Schriften von Großrechner-Drucksystemen (Size=1.0) liefern über
    PyMuPDFs Leerzeichen-Heuristik Silbenfragmente mit falschen
    Zwischenräumen ("SV Spa r ka ssen V er si ch eru n g" statt "SV
    SparkassenVersicherung", siehe docs/prompt_table_regions_whitespace_free.md).

    Rückgabe: None, wenn condition nicht zutrifft. Sonst ein Tupel
    (text_nows, text_display):
    - text_nows: text komplett ohne Whitespace - für den späteren
      Whitespace-freien Vergleich (siehe engine.compare_region_comparator).
    - text_display: text mit auf je ein Leerzeichen kollabiertem Whitespace
      - lesbare Version für die Delta-Anzeige im Report."""
    text_display = " ".join(text.split())
    text_nows = "".join(text_display.split())
    condition_nows = "".join(condition.split())
    if condition_nows not in text_nows:
        return None
    return text_nows, text_display


def separate_compare_region_blocks(
    blocks: List[TextBlock],
    page_num: int,
    compare_regions: Sequence[CompareRegion],
) -> Tuple[List[TextBlock], Dict[int, Tuple[str, str]]]:
    """Trennt Blöcke ab, die innerhalb einer zutreffenden compare_region
    liegen UND deren condition matcht - für diese Blöcke greift statt des
    normalen sequenziellen Vergleichs der Whitespace-freie Vergleich (siehe
    engine.compare_region_comparator), weil PyMuPDF für optisch identischen
    Mehrspalten-Inhalt je nach Formatierer unterschiedliche Blockgrenzen
    liefert (siehe docs/prompt_table_regions.md).

    _region_applies_to_page erwartet Region, akzeptiert CompareRegion aber
    per Duck-Typing (gleiche .page/.page_from-Attribute) - siehe
    ocr_extractor._mask_regions_on_image für dasselbe Muster.

    Der condition-Abgleich entfernt JEGLICHEN Whitespace (nicht nur
    Kollabieren auf ein Leerzeichen) - Type3-Schriften von Großrechner-
    Drucksystemen (Size=1.0) liefern über PyMuPDFs Leerzeichen-Heuristik
    Silbenfragmente mit falschen Zwischenräumen ("SV Spa r ka ssen V er si
    ch eru n g" statt "SV SparkassenVersicherung", siehe
    docs/prompt_table_regions_whitespace_free.md); die Kalibrierung
    (calibrate_spacewidths) kann das nicht immer heilen, weil die
    Zeichenlücken bei diesen Schriften gleichmäßig verteilt sind (kein
    erkennbarer Sprung zwischen Intra-Wort- und Wortgrenzen-Abstand,
    criterion_met=False). Ein reiner "auf ein Leerzeichen kollabieren"-
    Abgleich (die vorherige Fassung) findet die condition dort nicht, weil
    die Referenzseite viele echte Leerzeichen mitten in Wörtern hat, die
    die Kandidatenseite nicht hat.

    Rückgabe: (remaining_blocks, compare_region_texts)
    - remaining_blocks: Blöcke, die in KEINER zutreffenden, matchenden
      compare_region liegen (unverändert für split_wide_blocks/sort/join).
    - compare_region_texts: dict region_index -> (whitespace-freier Text für
      den Vergleich, Whitespace-normalisierter Text mit einfachen
      Leerzeichen für die lesbare Delta-Anzeige im Report) - NUR für
      Regionen, deren condition tatsächlich zutraf. Nicht zutreffende
      Regionen (falsche Seite, keine überlappenden Blöcke, condition
      trifft nicht zu) bleiben unerwähnt - ihre Blöcke bleiben unverändert
      im normalen Vergleich.
    """
    remaining = list(blocks)
    compare_region_texts: Dict[int, Tuple[str, str]] = {}

    for index, region in enumerate(compare_regions):
        if not _region_applies_to_page(region, page_num):
            continue
        region_blocks = [b for b in remaining if _compare_region_overlaps(region, b[:4])]
        if not region_blocks:
            continue

        matched = check_compare_region_condition(join_block_text(region_blocks), region.condition)
        if matched is None:
            # TODO: separate_compare_region_blocks wird für Referenz- und
            # Kandidat-Seite UNABHÄNGIG voneinander aufgerufen (siehe
            # extract_pages_for_profile). Matcht die condition nur auf EINER
            # Seite (z.B. weil dort ein Wort fehlt/anders geschrieben ist),
            # werden die Blöcke auch nur dort abgetrennt - die andere Seite
            # behält sie im normalen Seitentext. merge_compare_region_comparison
            # (engine.compare_region_comparator) überspringt so einen
            # region_index dann still (kein Eintrag auf beiden Seiten), und
            # die betroffenen Blöcke laufen stattdessen unkontrolliert durch
            # den normalen sequenziellen Vergleich - das kann zu großen,
            # schwer nachvollziehbaren Deltas führen, statt zu einem klaren
            # Hinweis "condition hat nur auf einer Seite gematcht". Bewusst
            # nicht in docs/prompt_compare_regions_mode.md behoben - siehe
            # dort, Abschnitt "One-sided condition match", für den
            # geplanten Follow-up.
            continue  # condition trifft nicht zu - Blöcke bleiben im normalen Vergleich

        compare_region_texts[index] = matched
        region_block_ids = {id(b) for b in region_blocks}
        remaining = [b for b in remaining if id(b) not in region_block_ids]

    return remaining, compare_region_texts


def get_text_blocks(page: "pymupdf.Page") -> List[TextBlock]:
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


def split_wide_blocks(blocks: List[TextBlock], page: "pymupdf.Page") -> List[TextBlock]:
    """Zerlegt breite Blöcke, die mehrere visuelle Spalten überdecken, wieder
    in schmale Teilblöcke - eine je Spalte (siehe CLAUDE-Diagnose-Session:
    schreibt der Formatierer zeilenweise über alle Spalten hinweg, verschmilzt
    PyMuPDF sie zu einem einzigen breiten Block, dessen "Zeilen" eigentlich
    einzelne Spalten-Zellen sind).

    Reine Funktion, verändert blocks/page nicht. Gehört zwischen
    filter_blocks_by_regions() und sort_blocks_columns() in die
    Extraktions-Pipeline (native wie rekonstruiert, siehe
    _extract_page_text_columns[_reconstructed] und
    region_filter.extract_pages_excluding_regions).

    Blöcke <= _SPLIT_THRESHOLD_PT bleiben unverändert (kein Splitkandidat).
    Für breitere Blöcke werden die rawdict-Zeilen über block_no (Index 5 des
    TextBlock-Tupels) nachgeschlagen und per Lücken-Clustering zu
    Spalten-Gruppen zusammengefasst: Zeilen nach x0 sortiert, eine neue Spalte
    beginnt, sobald die Lücke zum nächsten x0 _SPLIT_GAP_THRESHOLD_PT
    überschreitet. Das vermeidet das Bucket-Grenzproblem einer reinen
    Rundung, bei dem zwei nah beieinanderliegende x0-Werte (z.B. 70 und 80)
    je nach Lage der Rundungsgrenze in unterschiedliche Gruppen fallen
    könnten. Ergibt das nur eine Gruppe (z.B. eine breite, linksbündige
    Überschrift über mehrere Zeilen), gibt es keine Mehrspalten-Struktur
    aufzulösen - der Block bleibt unverändert. Bei jeder Unstimmigkeit
    zwischen TextBlock-Text und rawdict (fehlender/abweichender Block,
    Zeilen-Anzahl passt nicht) wird der Block unverändert durchgereicht
    statt zu raten - siehe Modul-Docstring zu _reconstruct_line_text für
    dieselbe Grundhaltung."""
    result: List[TextBlock] = []
    rawdict_blocks: Optional[List[dict]] = None

    for block in blocks:
        x0, y0, x1, y1, text, block_no, block_type = block
        if x1 - x0 <= _SPLIT_THRESHOLD_PT:
            result.append(block)
            continue

        if rawdict_blocks is None:
            rawdict_blocks = page.get_text("rawdict").get("blocks", [])

        if block_no < 0 or block_no >= len(rawdict_blocks):
            result.append(block)
            continue
        rawdict_block = rawdict_blocks[block_no]
        if rawdict_block.get("type") != _TEXT_BLOCK_TYPE:
            result.append(block)
            continue

        lines = rawdict_block.get("lines", [])
        text_lines = text.split("\n")
        while text_lines and text_lines[-1] == "":
            text_lines.pop()
        if not lines or len(text_lines) != len(lines):
            result.append(block)
            continue

        by_x0 = sorted(range(len(lines)), key=lambda i: lines[i]["bbox"][0])
        groups: List[List[int]] = []
        current_group: List[int] = []
        prev_x0: Optional[float] = None
        for i in by_x0:
            x0_line = lines[i]["bbox"][0]
            if prev_x0 is not None and x0_line - prev_x0 > _SPLIT_GAP_THRESHOLD_PT:
                groups.append(current_group)
                current_group = []
            current_group.append(i)
            prev_x0 = x0_line
        if current_group:
            groups.append(current_group)

        if len(groups) <= 1:
            result.append(block)
            continue

        for group in groups:
            indices = sorted(group)  # ursprüngliche Zeilenreihenfolge für Text/Bbox
            line_bboxes = [lines[i]["bbox"] for i in indices]
            sub_x0 = min(b[0] for b in line_bboxes)
            sub_y0 = min(b[1] for b in line_bboxes)
            sub_x1 = max(b[2] for b in line_bboxes)
            sub_y1 = max(b[3] for b in line_bboxes)
            sub_text = "\n".join(text_lines[i] for i in indices) + "\n"
            result.append((sub_x0, sub_y0, sub_x1, sub_y1, sub_text, block_no, _TEXT_BLOCK_TYPE))

    return result


def _extract_page_text_columns(
    page: "pymupdf.Page",
    page_num: int = 1,
    regions: Sequence[Region] = (),
    compare_regions: Sequence[CompareRegion] = (),
) -> Tuple[str, Dict[int, Tuple[str, str]]]:
    """Liest den Text einer Seite spaltenweise (links vor rechts), statt
    strikt zeilenweise. regions wird vor der Sortierung angewendet
    (Ausschluss-Regionen, siehe filter_blocks_by_regions); compare_regions
    danach, aber vor split_wide_blocks (siehe separate_compare_region_blocks -
    deren Blöcke sollen NICHT mehr am Spalten-Splitting/-Sortieren
    teilnehmen, sie fließen stattdessen separat in den Whitespace-freien
    Vergleich).

    Rückgabe: (Seitentext ohne compare_region-Blöcke, compare_region_texts für
    diese Seite - leeres dict, wenn compare_regions leer ist oder keine
    Region zutraf). Werte sind (whitespace-freier Text, lesbarer Text) -
    siehe separate_compare_region_blocks."""
    blocks = filter_blocks_by_regions(get_text_blocks(page), page_num, regions)
    compare_region_texts: Dict[int, Tuple[str, str]] = {}
    if compare_regions:
        blocks, compare_region_texts = separate_compare_region_blocks(blocks, page_num, compare_regions)
    blocks = split_wide_blocks(blocks, page)
    text = join_block_text(sort_blocks_columns(blocks))
    return text, compare_region_texts


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


def _iter_rawdict_lines(doc: "pymupdf.Document"):
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


def _collect_font_measurements(doc: "pymupdf.Document") -> Dict[Tuple[str, float], dict]:
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


def calibrate_spacewidths(doc: "pymupdf.Document") -> Dict[Tuple[str, float], SpacewidthCalibration]:
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
    page: "pymupdf.Page", calibration: Dict[Tuple[str, float], SpacewidthCalibration]
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
    page: "pymupdf.Page",
    calibration: Dict[Tuple[str, float], SpacewidthCalibration],
    page_num: int = 1,
    regions: Sequence[Region] = (),
) -> str:
    blocks = filter_blocks_by_regions(
        get_text_blocks_reconstructed(page, calibration), page_num, regions
    )
    blocks = split_wide_blocks(blocks, page)
    return join_block_text(sort_blocks_columns(blocks))


def _warn_if_table_page_has_regions(
    page_num: int, regions: Sequence[Region], warnings: Optional[List[str]]
) -> None:
    """Tabellenlinearisierung (_linearize_tables) ist nicht block-basiert und
    kann Ausschluss-Regionen daher nicht anwenden. Statt das Ausschluss-
    Fehlen dort still zu übergehen, wird es hier vermerkt - Aufrufer (CLI,
    Batch) geben das an Log/Report weiter."""
    if warnings is None:
        return
    if any(_region_applies_to_page(r, page_num) for r in regions):
        warnings.append(
            f"Seite {page_num}: Ausschluss-Region(en) konnten wegen Tabellenerkennung "
            "nicht angewendet werden."
        )


def _extract_pages_reconstructed(
    pdf_path: str,
    regions: Sequence[Region] = (),
    warnings: Optional[List[str]] = None,
) -> List[str]:
    """Wie extract_pages(), nutzt für Nicht-Tabellenseiten aber die eigene
    Wortrekonstruktion statt PyMuPDFs Leerzeichen-Heuristik. Tabellenerkennung
    (pdfplumber) bleibt unverändert und hat weiterhin Vorrang, wie in
    extract_pages() - siehe Plan Punkt (e)."""
    pages_text: List[str] = []
    doc = pymupdf.open(pdf_path)
    try:
        calibration = calibrate_spacewidths(doc)
        with pdfplumber.open(pdf_path) as plumber_pdf:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                plumber_page = plumber_pdf.pages[page_index]
                tables = plumber_page.extract_tables()
                if tables:
                    _warn_if_table_page_has_regions(page_num, regions, warnings)
                    pages_text.append(_linearize_tables(tables))
                else:
                    pages_text.append(
                        _extract_page_text_columns_reconstructed(page, calibration, page_num, regions)
                    )
    finally:
        doc.close()
    return pages_text


def extract_pages(
    pdf_path: str,
    regions: Sequence[Region] = (),
    warnings: Optional[List[str]] = None,
    compare_regions: Sequence[CompareRegion] = (),
    compare_region_texts: Optional[List[Dict[int, Tuple[str, str]]]] = None,
) -> List[str]:
    """Extrahiert den Text jeder Seite eines PDFs als eigenen String.

    Enthält eine Seite Tabellen, wird deren Inhalt zeilenweise linearisiert;
    andernfalls wird der Fließtext spaltenbewusst gelesen. regions schließt
    Textblöcke aus, die eine für ihre Seite definierte Region überlappen
    (TC-E-001 ff.) - auf Tabellenseiten kann das nicht angewendet werden,
    siehe _warn_if_table_page_has_regions.

    compare_region_texts ist ein Ausgabe-Parameter (wie warnings) statt eines
    Teils des Rückgabewerts - das hält die Signatur für die vielen
    bestehenden direkten extract_pages()-Aufrufer (Tests, page_group_detector)
    unverändert kompatibel: List[str] bleibt List[str]. Wird eine Liste
    übergeben, hängt jede Seite dort ihr compare_region_texts-dict an (leeres
    dict für Tabellenseiten - Tabellenerkennung ist nicht block-basiert,
    siehe _warn_if_table_page_has_regions für dasselbe Problem bei
    exclude_regions)."""
    pages_text: List[str] = []
    doc = pymupdf.open(pdf_path)
    try:
        with pdfplumber.open(pdf_path) as plumber_pdf:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                plumber_page = plumber_pdf.pages[page_index]
                tables = plumber_page.extract_tables()
                if tables:
                    _warn_if_table_page_has_regions(page_num, regions, warnings)
                    pages_text.append(_linearize_tables(tables))
                    if compare_region_texts is not None:
                        compare_region_texts.append({})
                else:
                    page_text, page_compare_region_texts = _extract_page_text_columns(
                        page, page_num, regions, compare_regions
                    )
                    pages_text.append(page_text)
                    if compare_region_texts is not None:
                        compare_region_texts.append(page_compare_region_texts)
    finally:
        doc.close()
    return pages_text


def _effective_ocr_mode(ocr: "OcrConfig", role: str) -> str:
    """Löst den tatsächlich anzuwendenden OCR-Modus für eine Seite
    (Referenz oder Kandidat) auf.

    mode_reference/mode_candidate gewinnen, wenn im Profil explizit gesetzt
    (nicht None). Andernfalls gilt das alte 'enabled'-Flag für beide Seiten
    gleich (True -> "fallback", False -> "off") - so bleiben Altprofile und
    direkt konstruierte OcrConfig(enabled=...)-Aufrufe unverändert gültig."""
    mode = ocr.mode_reference if role == "reference" else ocr.mode_candidate
    if mode is not None:
        return mode
    return "fallback" if ocr.enabled else "off"


def extract_pages_for_profile(
    pdf_path: str,
    profile: Optional[Profile],
    role: str = "reference",
    warnings: Optional[List[str]] = None,
) -> Tuple[List[str], bool, List[Dict[int, Tuple[str, str]]]]:
    """Wie extract_pages(), wendet aber je nach role ("reference" oder
    "candidate") und profile.ocr.mode_reference/mode_candidate einen der
    drei OCR-Modi an, UND wendet profile.exclude_regions tatsächlich auf
    die Extraktion an (TC-E-001 ff.) - das ist der Produktivpfad, den
    engine.__main__ und engine.batch_processor nutzen, anders als der
    direkte Aufruf von engine.region_filter.extract_pages_excluding_regions
    in den ursprünglichen TC-E-Tests, der nicht in dieser Funktion mündete.

    OCR-Modi:
    - "off": kein OCR, heutiger Pfad (native/reconstruct je text_extraction).
      exclude_regions wird block-basiert angewendet (filter_blocks_by_regions);
      auf Tabellenseiten (pdfplumber) ist das nicht möglich, siehe
      _warn_if_table_page_has_regions.
    - "fallback": OCR nur für Seiten ohne nativen Text (ocr_extractor.
      extract_pages_with_ocr_fallback) - z.B. gescannte Seiten. Regionen
      werden für native Seiten block-basiert gefiltert, für tatsächlich
      per OCR gelesene Seiten vor dem Rastern maskiert (siehe "force").
    - "force": OCR für JEDE Seite, auch wenn nativer Text vorhanden ist
      (ocr_extractor.extract_text_via_ocr) - für Fälle wie Type3-Schriften
      ohne ToUnicode-Tabelle, bei denen nativer Text zwar existiert, aber
      wortselektiv kaputte Wortgrenzen liefert. Es gibt hier keine Block-
      struktur mehr, auf die filter_blocks_by_regions aufbauen könnte;
      exclude_regions wird deshalb VOR dem OCR-Lauf als weiße Fläche auf
      das gerasterte Seitenbild gemalt (ocr_extractor._mask_regions_on_image)
      - das wirkt unabhängig von Layout/Blockstruktur zuverlässig, anders
      als ein nachträglicher Textabgleich. "force" überspringt dabei
      zwangsläufig die pdfplumber-Tabellenerkennung und die eigene
      Wortrekonstruktion (text_extraction="reconstruct") - Tesseract liest
      die gerasterte Seite als Ganzes.

    role bestimmt, welche der beiden Profil-Einstellungen greift; es gibt
    bewusst keinen Default, der aus dem Aufruf-Kontext erschlossen wird -
    Aufrufer (CLI, Batch) müssen role explizit übergeben, siehe
    engine.__main__ und engine.batch_processor.

    warnings sammelt (falls übergeben) Hinweise auf Konstellationen, in
    denen exclude_regions NICHT angewendet werden konnte (aktuell nur
    Tabellenseiten unter "off"/"fallback") - Aufrufer geben das an Log und
    Report weiter, statt den Ausschluss dort still wirkungslos zu lassen.

    compare_regions (siehe profile.compare_regions, separate_compare_region_blocks)
    werden aktuell nur unter "off" (native Extraktion, extract_pages) und
    "fallback" (ocr_extractor.extract_pages_with_ocr_fallback, der
    tatsächliche Ausführungspfad für ocr.mode="fallback"-Profile) block-
    basiert ausgewertet - unter "force" (reines OCR, keine Blockstruktur)
    und text_extraction="reconstruct" (noch nicht integriert, siehe
    docs/prompt_table_regions.md) liefern diese Pfade je ein leeres dict
    pro Seite.

    Rückgabe: (Seitentexte, ocr_used, compare_region_texte_pro_seite) - der
    dritte Wert ist eine Liste (ein Eintrag pro Seite) von dicts
    region_index -> (whitespace-freier Text, lesbarer Text); Seiten ohne
    zutreffende compare_region haben ein leeres dict (siehe
    separate_compare_region_blocks).
    """
    regions: List[Region] = []
    compare_regions: List[CompareRegion] = []
    if profile is not None:
        regions = [
            Region(page=r.page, x=r.x, y=r.y, w=r.width, h=r.height, page_from=r.page_from)
            for r in profile.exclude_regions
        ]
        compare_regions = list(profile.compare_regions)
        mode = _effective_ocr_mode(profile.ocr, role)
        if mode == "force":
            from engine.ocr_extractor import extract_text_via_ocr
            pages = extract_text_via_ocr(pdf_path, dpi=profile.ocr.dpi, regions=regions)
            return pages, True, [{} for _ in pages]
        if mode == "fallback":
            from engine.ocr_extractor import extract_pages_with_ocr_fallback
            return extract_pages_with_ocr_fallback(
                pdf_path, dpi=profile.ocr.dpi, regions=regions, warnings=warnings,
                compare_regions=compare_regions,
            )
        if profile.text_extraction == "reconstruct":
            pages = _extract_pages_reconstructed(pdf_path, regions=regions, warnings=warnings)
            return pages, False, [{} for _ in pages]
    per_page_compare_region_texts: List[Dict[int, Tuple[str, str]]] = []
    pages = extract_pages(
        pdf_path, regions=regions, warnings=warnings,
        compare_regions=compare_regions, compare_region_texts=per_page_compare_region_texts,
    )
    return pages, False, per_page_compare_region_texts
