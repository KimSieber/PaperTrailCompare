# file:    tools/diag_deltas.py
# purpose: Diagnostic tool for inspecting PDF extraction details: delta
#          analysis, rawdict inspection, font encoding checks, spacewidth
#          calibration reports, and TEXT_INHIBIT_SPACES cross-checks.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Diagnose-Skript für das Fußzeilen-Delta-Ticket (Leerzeichen-Toleranz).

NUR zur Analyse auf einem realen Dateipaar beim Kunden - liest ausschließlich
lokal, schreibt keine Dateien, macht keine Netzwerk-Zugriffe. Nicht Teil der
Core Engine (bewusst außerhalb von engine/), damit es nicht versehentlich in
den Produktivpfad gerät.

Nutzung (Delta-Diagnose, zwei Dokumente):
    python -m tools.diag_deltas <ref.pdf> <cnd.pdf> [--case-insensitive]

Nutzung (Wort-Diagnose, ein Dokument - klärt Sperrsatz/H1 vs. OCR/H2):
    python -m tools.diag_deltas <datei.pdf> --inspect-word "<suchbegriff>" --page N

Nutzung (Sicherheits-Check für TEXT_INHIBIT_SPACES, zwei Dokumente):
    python -m tools.diag_deltas <ref.pdf> <cnd.pdf> --check-inhibit-spaces [--samples N]

Nutzung (Encoding-Diagnose für Umlaut-Defekte, ein Dokument - für Referenz
und Kandidat je einmal separat aufrufen):
    python -m tools.diag_deltas <datei.pdf> --inspect-encoding "<suchbegriff>" --page N

Nutzung (rawdict-Leerzeichen-Diagnose, ein Dokument - für Referenz und
Kandidat je einmal separat aufrufen):
    python -m tools.diag_deltas <datei.pdf> --inspect-rawdict "<suchbegriff>" --page N

Nutzung (Kalibrierungs-Report für die Wortrekonstruktion, ein Dokument):
    python -m tools.diag_deltas <datei.pdf> --calibration-report

Greift auf ein paar private Hilfsfunktionen aus engine.text_comparator zu
(_words_with_pages, _is_whitespace_only_difference), um exakt dieselbe
Opcode-Struktur zu inspizieren, die compare() intern verwendet, dort aber
nicht nach außen gibt.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from typing import List, Optional

import pymupdf
import pdfplumber

from engine.pdf_extractor import calibrate_spacewidths, extract_pages, get_text_blocks, sort_blocks_columns
from engine.text_comparator import _is_whitespace_only_difference, _words_with_pages

# Nicht-ASCII-Whitespace/Format-Zeichen, die von normalize_text()s \s+ NICHT
# zwingend erfasst werden (v.a. Zero-Width-/BOM-Zeichen der Kategorie "Cf")
# oder die zwar erfasst werden, aber als Diagnose-Kandidaten interessant sind.
_SUSPECT_CHARS = {
    "\xa0": "NO-BREAK SPACE (U+00A0)",
    " ": "THIN SPACE (U+2009)",
    " ": "NARROW NO-BREAK SPACE (U+202F)",
    " ": "FIGURE SPACE (U+2007)",
    "​": "ZERO WIDTH SPACE (U+200B)",
    "‌": "ZERO WIDTH NON-JOINER (U+200C)",
    "‍": "ZERO WIDTH JOINER (U+200D)",
    "﻿": "ZERO WIDTH NO-BREAK SPACE / BOM (U+FEFF)",
    "\t": "TAB (U+0009)",
}


def _char_inventory(pages: List[str], label: str) -> None:
    print(f"\n--- Zeichen-Inventur: {label} ---")
    counter: Counter = Counter()
    for page_text in pages:
        for ch in page_text:
            if ch in _SUSPECT_CHARS:
                counter[ch] += 1
    if not counter:
        print("  (keine der gesuchten Zeichen gefunden)")
        return
    for ch, count in sorted(counter.items(), key=lambda kv: -kv[1]):
        print(f"  {_SUSPECT_CHARS[ch]:45} {ch!r:10} x{count}")


def _print_deltas(ref_pages: List[str], cnd_pages: List[str], case_sensitive: bool, limit: int = 10) -> None:
    ref_words, _ = _words_with_pages(ref_pages)
    cnd_words, cnd_word_pages = _words_with_pages(cnd_pages)

    if case_sensitive:
        ref_keys, cnd_keys = ref_words, cnd_words
    else:
        ref_keys = [w.lower() for w in ref_words]
        cnd_keys = [w.lower() for w in cnd_words]

    matcher = SequenceMatcher(a=ref_keys, b=cnd_keys, autojunk=False)
    shown = 0
    total_opcodes = 0
    total_remaining = 0

    print(f"\n--- Deltas (erste {limit}), normalize_whitespace=True ---")
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        total_opcodes += 1
        ref_text = " ".join(ref_words[i1:i2])
        cnd_text = " ".join(cnd_words[j1:j2])
        would_filter = _is_whitespace_only_difference(ref_text, cnd_text, case_sensitive)
        if would_filter:
            continue
        total_remaining += 1
        page = cnd_word_pages[j1] if j1 < len(cnd_word_pages) else (
            cnd_word_pages[-1] if cnd_word_pages else 0
        )
        if shown < limit:
            print(f"\n  Delta #{total_remaining} (Seite {page}, Opcode={tag})")
            print(f"    ref_text = {ref_text!r}")
            print(f"    cnd_text = {cnd_text!r}")
            print(f"    _is_whitespace_only_difference() = {would_filter}")
            shown += 1

    print(f"\n  Gesamt: {total_opcodes} Roh-Opcodes (ohne 'equal'), davon {total_opcodes - total_remaining} "
          f"durch normalize_whitespace gefiltert, {total_remaining} verbleibende Deltas.")


def _print_footer_buckets(pdf_path: str, label: str, num_pages: int = 3, bucket_pt: float = 50.0) -> None:
    print(f"\n--- Fußzeilen-Blöcke (letzte Blöcke je Seite, x0 -> Bucket round(x0/{bucket_pt:.0f})): {label} ---")
    doc = pymupdf.open(pdf_path)
    try:
        for page_index in range(min(num_pages, len(doc))):
            page = doc[page_index]
            blocks = get_text_blocks(page)
            sorted_blocks = sort_blocks_columns(blocks)
            # "unterer Seitenbereich": die Blöcke mit den größten y0-Werten
            # (fitz-Koordinaten: y wächst von oben nach unten).
            footer_blocks = sorted(blocks, key=lambda b: b[1])[-4:]
            print(f"\n  Seite {page_index + 1}:")
            for b in sorted(footer_blocks, key=lambda b: b[0]):
                x0, y0 = b[0], b[1]
                bucket = round(x0 / bucket_pt)
                text_preview = b[4].strip().replace("\n", " \\n ")[:60]
                print(f"    x0={x0:7.1f}  y0={y0:7.1f}  bucket={bucket:3d}  text={text_preview!r}")
    finally:
        doc.close()


def _page_render_summary(page: "pymupdf.Page") -> None:
    """(a) Bildbasiert oder nativ? Bilder, nativer Textumfang, Bildflächenanteil."""
    images = page.get_images(full=True)
    image_infos = page.get_image_info(xrefs=True)
    page_area = page.rect.width * page.rect.height
    image_area = sum(
        max(0.0, info["bbox"][2] - info["bbox"][0]) * max(0.0, info["bbox"][3] - info["bbox"][1])
        for info in image_infos
    )
    native_text_len = len(page.get_text())
    ratio = (image_area / page_area) if page_area else 0.0

    print("\n--- a) Seite bildbasiert oder nativ? ---")
    print(f"  Anzahl Image-XObjects: {len(images)}")
    print(f"  Länge des nativen Textes (page.get_text()): {native_text_len} Zeichen")
    print(f"  Bildfläche / Seitenfläche: {ratio:.1%} ({image_area:.0f} / {page_area:.0f} pt²)")


def _find_char_run(texttrace, search_term: str):
    """Sucht im Zeichenstrom (Lesereihenfolge nach seqno) nach einer
    zusammenhängenden Sequenz, deren Nicht-Whitespace-Zeichen (case-insensitiv)
    dem Suchbegriff entsprechen. Gibt die Liste der (char, unicode, span)-Tupel
    der Fundstelle zurück (inkl. etwaiger Leerzeichen dazwischen) oder None.

    Das ist der entscheidende Kniff: get_texttrace() liefert ausschließlich
    Zeichen, die tatsächlich im Content-Stream stehen - anders als
    page.get_text("text"), das an großen Glyphenlücken zusätzliche
    Leerzeichen einfügt, die im PDF selbst nicht existieren. Ein "echtes"
    Leerzeichen (chr(32) in diesem Zeichenstrom) ist damit ein Beleg für H2;
    eine reine Positionslücke ohne zugehöriges Zeichen spricht für H1.
    """
    spans = sorted(texttrace, key=lambda s: s.get("seqno", 0))
    full_chars = []  # (char, unicode_codepoint, span, char_tuple)
    for span in spans:
        for ch in span["chars"]:
            full_chars.append((chr(ch[0]), ch[0], span, ch))

    target_letters = re.sub(r"\s+", "", search_term).lower()
    if not target_letters:
        return None

    compact_to_full = []  # Index im "nur Nicht-Whitespace"-String -> Index in full_chars
    compact_string = []
    for idx, (char, _, _, _) in enumerate(full_chars):
        if not char.isspace():
            compact_to_full.append(idx)
            compact_string.append(char.lower())
    compact_string = "".join(compact_string)

    match_pos = compact_string.find(target_letters)
    if match_pos == -1:
        return None

    first_full_idx = compact_to_full[match_pos]
    last_full_idx = compact_to_full[match_pos + len(target_letters) - 1]
    return full_chars[first_full_idx : last_full_idx + 1]


_UMLAUT_CHARS = "äöüÄÖÜß"


def _find_char_run_lenient(texttrace, search_term: str):
    """Wie _find_char_run(), aber tolerant gegenüber Umlaut-Defekten: jeder
    Umlaut im Suchbegriff darf im Zeichenstrom fehlen (0 Zeichen) oder durch
    U+FFFD (Replacement Character) ersetzt sein, statt eine exakte
    Übereinstimmung zu verlangen. Nötig, weil ein defekter Encoding/
    ToUnicode-Fall genau das produziert - eine strikte Suche würde die
    Fundstelle dann gar nicht erst finden.

    Gibt (run, target_letter_infos) zurück, wobei target_letter_infos pro
    Position im Suchbegriff vermerkt, ob es sich um einen toleranten
    Umlaut-Slot handelte (für die Ausgabe in (b))."""
    spans = sorted(texttrace, key=lambda s: s.get("seqno", 0))
    full_chars = []
    for span in spans:
        for ch in span["chars"]:
            full_chars.append((chr(ch[0]), ch[0], span, ch))

    target_letters = re.sub(r"\s+", "", search_term)
    if not target_letters:
        return None, None

    compact_to_full = []
    compact_string = []
    for idx, (char, _, _, _) in enumerate(full_chars):
        if not char.isspace():
            compact_to_full.append(idx)
            compact_string.append(char)
    compact_string = "".join(compact_string)

    pattern_parts = []
    is_umlaut_slot = []
    for target_char in target_letters:
        if target_char in _UMLAUT_CHARS:
            pattern_parts.append(f"[{re.escape(target_char)}�]?")
            is_umlaut_slot.append(True)
        else:
            pattern_parts.append(re.escape(target_char))
            is_umlaut_slot.append(False)
    pattern = re.compile("".join(pattern_parts), re.IGNORECASE)

    match = pattern.search(compact_string)
    if match is None or match.start() == match.end():
        return None, None

    first_full_idx = compact_to_full[match.start()]
    last_full_idx = compact_to_full[match.end() - 1]
    run = full_chars[first_full_idx : last_full_idx + 1]
    return run, (target_letters, is_umlaut_slot)


def _inspect_char_run(run) -> pymupdf.Rect:
    """(b) Render-Mode je Span, (c) Zeichenebene inkl. Lücken-Analyse."""
    print("\n--- b) Text-Render-Mode der betroffenen Spans ---")
    seen_spans = []
    for _, _, span, _ in run:
        if span not in seen_spans:
            seen_spans.append(span)
    for span in seen_spans:
        render_mode = span.get("type")
        marker = "  <-- unsichtbar (klassischer OCR-Layer-Marker)" if render_mode == 3 else ""
        print(
            f"  font={span.get('font')!r:25} size={span.get('size'):.1f} "
            f"render_mode(type)={render_mode}{marker}"
        )

    print("\n--- c) Zeichenebene (aus get_texttrace(), nur real vorhandene Zeichen) ---")
    prev_bbox = None
    prev_span = None
    real_space_count = 0
    gap_without_char_count = 0
    run_rect = None
    for char, codepoint, span, ch in run:
        origin = ch[2]
        bbox = pymupdf.Rect(ch[3])
        run_rect = bbox if run_rect is None else run_rect | bbox
        gap = ""
        if prev_bbox is not None and prev_span is span:
            gap_pt = bbox.x0 - prev_bbox.x1
            spacewidth = span.get("spacewidth") or 0.0
            gap = f"  gap_zu_vorherigem={gap_pt:6.2f}pt (spacewidth dieser Schriftart={spacewidth:.2f}pt)"
        is_real_space = codepoint == 32
        if is_real_space:
            real_space_count += 1
        elif prev_bbox is not None and prev_span is span:
            gap_pt = bbox.x0 - prev_bbox.x1
            spacewidth = span.get("spacewidth") or 1.0
            if gap_pt > 0.3 * spacewidth:
                gap_without_char_count += 1
        print(
            f"    char={char!r:6} U+{codepoint:04X}  bbox=({bbox.x0:7.2f},{bbox.y0:7.2f},"
            f"{bbox.x1:7.2f},{bbox.y1:7.2f})  font={span.get('font')!r}"
            f" size={span.get('size'):.1f}{gap}"
        )
        prev_bbox = bbox
        prev_span = span

    print(f"\n  Echte Space-Zeichen (chr(32)) in der Fundstelle: {real_space_count}")
    print(f"  Positionslücken ohne zugehöriges Zeichen (>30% der Space-Breite dieser Schrift): {gap_without_char_count}")
    return run_rect


def _cross_check_extractions(pdf_path: str, page_index: int, run_rect: pymupdf.Rect, search_term: str) -> None:
    """(d) Gegenprobe mit alternativen Extraktionsmethoden derselben Stelle."""
    margin = 3.0
    clip = pymupdf.Rect(
        run_rect.x0 - margin, run_rect.y0 - margin, run_rect.x1 + margin, run_rect.y1 + margin
    )

    print("\n--- d) Gegenprobe mit alternativen Extraktionen derselben Stelle ---")
    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]
        standard = page.get_text("text", clip=clip).strip().replace("\n", " \\n ")
        print(f"  page.get_text('text')                         -> {standard!r}")
        inhibit = page.get_text("text", clip=clip, flags=pymupdf.TEXT_INHIBIT_SPACES).strip().replace("\n", " \\n ")
        print(f"  page.get_text('text', TEXT_INHIBIT_SPACES)    -> {inhibit!r}")
    finally:
        doc.close()

    with pdfplumber.open(pdf_path) as plumber_pdf:
        plumber_page = plumber_pdf.pages[page_index]
        bbox = (clip.x0, clip.y0, clip.x1, clip.y1)
        cropped = plumber_page.crop(bbox)
        for x_tol in (None, 1.0, 2.0, 3.0):
            kwargs = {} if x_tol is None else {"x_tolerance": x_tol}
            extracted = (cropped.extract_text(**kwargs) or "").strip().replace("\n", " \\n ")
            label = "Standard-x_tolerance" if x_tol is None else f"x_tolerance={x_tol}"
            print(f"  pdfplumber ({label:22}) -> {extracted!r}")

    print(f"\n  (Suchbegriff war: {search_term!r})")


def _inspect_word(pdf_path: str, search_term: str, page_number: int) -> int:
    doc = pymupdf.open(pdf_path)
    try:
        if not (1 <= page_number <= len(doc)):
            print(f"Fehler: Seite {page_number} existiert nicht (Dokument hat {len(doc)} Seiten).", file=sys.stderr)
            return 1
        page_index = page_number - 1
        page = doc[page_index]

        print(f"Datei: {pdf_path}  |  Seite {page_number}/{len(doc)}  |  Suchbegriff: {search_term!r}")
        _page_render_summary(page)

        texttrace = page.get_texttrace()
        run = _find_char_run(texttrace, search_term)
        if run is None:
            print(
                f"\nFehler: Suchbegriff {search_term!r} (ohne Whitespace: "
                f"{re.sub(r'\\s+', '', search_term)!r}) wurde im Zeichenstrom von Seite {page_number} "
                "nicht gefunden.",
                file=sys.stderr,
            )
            return 1

        run_rect = _inspect_char_run(run)
    finally:
        doc.close()

    _cross_check_extractions(pdf_path, page_index, run_rect, search_term)

    print("\n--- e) Fazit ---")
    print(
        "  Siehe oben: echte Space-Zeichen (chr(32)) im Zeichenstrom sprechen für H2 (OCR-Layer "
        "enthält Leerzeichen tatsächlich als Zeichen); Positionslücken ohne zugehöriges Zeichen "
        "sprechen für H1 (Sperrsatz/Laufweite, PyMuPDF leitet das Leerzeichen nur aus dem Abstand "
        "ab). Render-Mode 3 auf den betroffenen Spans wäre ein zusätzlicher, unabhängiger Hinweis "
        "auf eine unsichtbare OCR-Textschicht (H2). Falls TEXT_INHIBIT_SPACES oder ein erhöhter "
        "pdfplumber-x_tolerance-Wert das Wort intakt liefert, stützt das zusätzlich H1."
    )
    return 0


def _print_char_run_ab(run, target_info) -> pymupdf.Rect:
    """(a) Codepoint/Zeichen/Glyph/Font/bbox je Zeichen der Fundstelle.
    (b) Ob get_texttrace() an einer Umlaut-Position ein Zeichen liefert,
    keines liefert (Position fehlt) oder U+FFFD liefert."""
    print("\n--- a) get_texttrace() je Zeichen an der Fundstelle ---")
    run_rect = None
    for char, codepoint, span, ch in run:
        bbox = pymupdf.Rect(ch[3])
        run_rect = bbox if run_rect is None else run_rect | bbox
        glyph_id = ch[1]
        print(
            f"    char={char!r:6} U+{codepoint:04X}  glyph_id={glyph_id:4d}  "
            f"font={span.get('font')!r:20} bbox=({bbox.x0:7.2f},{bbox.y0:7.2f},{bbox.x1:7.2f},{bbox.y1:7.2f})"
        )

    print("\n--- b) Fehlt die Position oder ist nur falsch zugeordnet? ---")
    if target_info is not None:
        target_letters, is_umlaut_slot = target_info
        num_umlaut_slots = sum(is_umlaut_slot)
        num_umlaut_matched_chars = sum(
            1 for char, codepoint, _, _ in run if char in _UMLAUT_CHARS or codepoint == 0xFFFD
        )
        print(f"  Suchbegriff (bereinigt): {target_letters!r}, davon {num_umlaut_slots} Umlaut-Position(en)")
        print(f"  In der Fundstelle tatsächlich vorhandene Umlaut/Replacement-Zeichen: {num_umlaut_matched_chars}")
        if num_umlaut_matched_chars < num_umlaut_slots:
            print(
                "  -> Mindestens eine Umlaut-Position hat GAR KEIN Zeichen im Zeichenstrom "
                "(Position fehlt vollständig, nicht nur falsch zugeordnet)."
            )
        elif any(codepoint == 0xFFFD for _, codepoint, _, _ in run):
            print(
                "  -> Es ist ein Zeichen vorhanden, aber es ist U+FFFD (Replacement Character) "
                "- die Position ist also besetzt, aber falsch zugeordnet."
            )
        else:
            print("  -> Alle erwarteten Umlaut-Positionen sind mit dem korrekten Zeichen besetzt.")
    return run_rect


def _cross_check_encoding(pdf_path: str, page_index: int, run_rect: pymupdf.Rect) -> None:
    """(c) Gegenprobe über rawdict, get_text('words') und pdfplumber .chars."""
    margin = 2.0
    clip = pymupdf.Rect(
        run_rect.x0 - margin, run_rect.y0 - margin, run_rect.x1 + margin, run_rect.y1 + margin
    )

    print("\n--- c) Gegenprobe über drei weitere Extraktionswege ---")
    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]

        rawdict = page.get_text("rawdict", clip=clip)
        rawdict_chars = [
            ch["c"]
            for block in rawdict.get("blocks", [])
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            for ch in span.get("chars", [])
        ]
        print(f"  rawdict 'c'-Felder: {rawdict_chars!r}")

        words = page.get_text("words", clip=clip)
        print(f"  get_text('words'):  {[w[4] for w in words]!r}")
    finally:
        doc.close()

    with pdfplumber.open(pdf_path) as plumber_pdf:
        plumber_page = plumber_pdf.pages[page_index]
        chars_in_clip = [
            c["text"]
            for c in plumber_page.chars
            if c["x0"] >= clip.x0 - 1 and c["x1"] <= clip.x1 + 1 and c["top"] >= clip.y0 - 1 and c["bottom"] <= clip.y1 + 1
        ]
        print(f"  pdfplumber .chars 'text'-Felder: {chars_in_clip!r}")


_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")
_TOUNICODE_REF_RE = re.compile(r"/ToUnicode\s+(\d+)\s+\d+\s+R")


def _analyze_fonts(pdf_path: str, page_index: int, run) -> None:
    """(d) Font-Analyse: Subtype, Subset-Präfix, Encoding/Differences,
    ToUnicode-CMap (falls vorhanden, Roh-Dump zur Sichtprüfung - MuPDFs
    'glyph'-Feld aus get_texttrace() ist ein font-interner Glyphenindex,
    nicht notwendigerweise der PDF-Zeichencode, den die ToUnicode-CMap
    referenziert; ein exaktes Glyph->ToUnicode-Mapping ist daher nicht
    zuverlässig herleitbar - dieser Dump ist Beleg, kein Beweis für eine
    einzelne Glyphe)."""
    print("\n--- d) Font-Analyse ---")
    font_names = sorted({span.get("font") for _, _, span, _ in run})

    doc = pymupdf.open(pdf_path)
    try:
        page = doc[page_index]
        fonts = page.get_fonts(full=True)
        for font_name in font_names:
            matches = [f for f in fonts if f[3] == font_name or f[4] == font_name]
            if not matches:
                print(f"  Font {font_name!r}: nicht in page.get_fonts() gefunden (evtl. geerbte Ressource).")
                continue
            for f in matches:
                xref, ext, ftype, basefont, name, encoding = f[0], f[1], f[2], f[3], f[4], f[5]
                is_subset = bool(_SUBSET_PREFIX_RE.match(basefont))
                print(f"\n  Font {name!r}: basefont={basefont!r}  subtype={ftype}  encoding={encoding!r}")
                print(f"    Subset-Präfix (6 Großbuchstaben + '+'): {is_subset}")

                obj_text = doc.xref_object(xref)
                has_differences = "/Differences" in obj_text
                print(f"    /Differences-Array in Encoding vorhanden: {has_differences}")

                tounicode_match = _TOUNICODE_REF_RE.search(obj_text)
                if not tounicode_match:
                    print("    /ToUnicode: NICHT vorhanden")
                    continue
                tounicode_xref = int(tounicode_match.group(1))
                print(f"    /ToUnicode: vorhanden (xref {tounicode_xref})")
                try:
                    cmap_bytes = doc.xref_stream(tounicode_xref)
                    cmap_text = cmap_bytes.decode("latin-1", errors="replace")
                    preview_lines = [
                        line for line in cmap_text.splitlines()
                        if "bfchar" in line or "bfrange" in line or line.strip().startswith(("<", "beginbf"))
                    ][:20]
                    print("    ToUnicode-CMap-Auszug (bfchar/bfrange-Zeilen, max. 20, Beleg zur Sichtprüfung):")
                    for line in preview_lines:
                        print(f"      {line.strip()}")
                except Exception as exc:  # Diagnose-Skript: Rohdaten-Dump darf nie hart abbrechen
                    print(f"    ToUnicode-Stream konnte nicht gelesen werden: {exc}")
    finally:
        doc.close()


def _inspect_encoding(pdf_path: str, search_term: str, page_number: int) -> int:
    doc = pymupdf.open(pdf_path)
    try:
        if not (1 <= page_number <= len(doc)):
            print(f"Fehler: Seite {page_number} existiert nicht (Dokument hat {len(doc)} Seiten).", file=sys.stderr)
            return 1
        page_index = page_number - 1
        page = doc[page_index]

        print(f"Datei: {pdf_path}  |  Seite {page_number}/{len(doc)}  |  Suchbegriff: {search_term!r}")

        texttrace = page.get_texttrace()
        run, target_info = _find_char_run_lenient(texttrace, search_term)
        if run is None:
            print(
                f"\nFehler: Suchbegriff {search_term!r} wurde im Zeichenstrom von Seite {page_number} "
                "auch mit Umlaut-Toleranz nicht gefunden.",
                file=sys.stderr,
            )
            return 1

        run_rect = _print_char_run_ab(run, target_info)
    finally:
        doc.close()

    _cross_check_encoding(pdf_path, page_index, run_rect)
    _analyze_fonts(pdf_path, page_index, run)

    print("\n--- f) Fazit ---")
    has_missing_or_replacement = any(
        codepoint == 0xFFFD for _, codepoint, _, _ in run
    ) or (target_info is not None and sum(target_info[1]) > sum(
        1 for char, codepoint, _, _ in run if char in _UMLAUT_CHARS or codepoint == 0xFFFD
    ))
    if has_missing_or_replacement:
        print(
            "  Der Umlaut ist bereits in get_texttrace() NICHT korrekt vorhanden (siehe (a)/(b) oben - "
            "entweder fehlt die Position vollständig oder enthält U+FFFD). get_texttrace() ist die "
            "unterste von PyMuPDF bereitgestellte Text-Extraktionsebene für Zeichen - der Defekt sitzt "
            "also VOR jeder eigenen Wortrekonstruktion, in PyMuPDFs eigener Encoding-/ToUnicode-Auflösung "
            "beim Laden der Schriftart. Eine eigene Wortrekonstruktion aus get_texttrace()-Koordinaten "
            "würde diesen Fall NICHT automatisch mitlösen, da das fehlerhafte/fehlende Zeichen schon an "
            "der Quelle so vorliegt."
        )
    else:
        print(
            "  Der Umlaut ist in get_texttrace() korrekt vorhanden. Der Defekt entsteht demnach erst in "
            "einer höheren Extraktionsstufe (z.B. TEXT_INHIBIT_SPACES-Pfad) und würde von einer eigenen, "
            "auf get_texttrace() basierenden Wortrekonstruktion vermutlich automatisch mitgelöst."
        )
    return 0


def _flatten_rawdict(rawdict) -> List[tuple]:
    """Rawdict-Zeichen in Lesereihenfolge (Block -> Line -> Span -> Char).
    Gibt (char, bbox_tuple, font, size)-Tupel zurück."""
    flat = []
    for block in rawdict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font = span.get("font")
                size = span.get("size")
                for ch in span.get("chars", []):
                    flat.append((ch["c"], ch["bbox"], font, size))
    return flat


def _find_rawdict_run(flat_chars: List[tuple], search_term: str) -> Optional[List[tuple]]:
    """Wie _find_char_run(), aber auf rawdict-Zeichen statt get_texttrace()-
    Zeichen: sucht die zusammenhängende Sequenz, deren Nicht-Whitespace-
    Zeichen (case-insensitiv) dem Suchbegriff entsprechen, inkl. etwaiger
    dazwischenliegender Zeichen (auch Leerzeichen-Einträge, falls vorhanden -
    genau das ist ja die offene Frage dieses Diagnose-Schritts)."""
    target_letters = re.sub(r"\s+", "", search_term).lower()
    if not target_letters:
        return None

    compact_to_full = []
    compact_string = []
    for idx, (char, _, _, _) in enumerate(flat_chars):
        if char and not char.isspace():
            compact_to_full.append(idx)
            compact_string.append(char.lower())
    compact_string = "".join(compact_string)

    match_pos = compact_string.find(target_letters)
    if match_pos == -1:
        return None

    first_full_idx = compact_to_full[match_pos]
    last_full_idx = compact_to_full[match_pos + len(target_letters) - 1]
    return flat_chars[first_full_idx : last_full_idx + 1]


def _inspect_rawdict(pdf_path: str, search_term: str, page_number: int) -> int:
    doc = pymupdf.open(pdf_path)
    try:
        if not (1 <= page_number <= len(doc)):
            print(f"Fehler: Seite {page_number} existiert nicht (Dokument hat {len(doc)} Seiten).", file=sys.stderr)
            return 1
        page_index = page_number - 1
        page = doc[page_index]

        print(f"Datei: {pdf_path}  |  Seite {page_number}/{len(doc)}  |  Suchbegriff: {search_term!r}")

        rawdict = page.get_text("rawdict")
        flat_chars = _flatten_rawdict(rawdict)
        run = _find_rawdict_run(flat_chars, search_term)
        if run is None:
            print(
                f"\nFehler: Suchbegriff {search_term!r} wurde in den rawdict-Zeichen von Seite "
                f"{page_number} nicht gefunden.",
                file=sys.stderr,
            )
            return 1

        print("\n--- a) rawdict-Zeichen-Einträge der Fundstelle, in Reihenfolge ---")
        run_rect = None
        space_entries = []
        for char, bbox_tuple, font, size in run:
            bbox = pymupdf.Rect(bbox_tuple)
            run_rect = bbox if run_rect is None else run_rect | bbox
            marker = "  <-- LEERZEICHEN-EINTRAG" if char == " " else ""
            print(
                f"    c={char!r:6} bbox=({bbox.x0:7.2f},{bbox.y0:7.2f},{bbox.x1:7.2f},{bbox.y1:7.2f}) "
                f"font={font!r:20} size={size:.1f}{marker}"
            )
            if char == " ":
                space_entries.append(bbox)

        margin = 2.0
        clip = pymupdf.Rect(
            run_rect.x0 - margin, run_rect.y0 - margin, run_rect.x1 + margin, run_rect.y1 + margin
        )
        text_at_clip = page.get_text("text", clip=clip)
        text_at_clip_stripped = text_at_clip.strip()

        print("\n--- b) get_text('text') an derselben Stelle ---")
        print(f"  page.get_text('text', clip=Fundstelle) -> {text_at_clip_stripped!r}")

        total_rawdict_chars = len(run)
        rawdict_space_count = len(space_entries)
        text_space_count = text_at_clip_stripped.count(" ")

        print("\n--- c) Zählung: rawdict-Leerzeichen vs. get_text('text')-Leerzeichen ---")
        print(f"  rawdict-Zeichen insgesamt an der Fundstelle: {total_rawdict_chars}")
        print(f"  davon rawdict-Einträge mit c=' ': {rawdict_space_count}")
        print(f"  Leerzeichen in get_text('text') an derselben Stelle: {text_space_count}")
        if rawdict_space_count != text_space_count:
            print(
                f"  -> Abweichung ({rawdict_space_count} vs. {text_space_count}): get_text('text') fügt "
                "Leerzeichen ein, die in rawdict nicht als eigener Zeichen-Eintrag existieren."
            )
        else:
            print("  -> Keine Abweichung an dieser Stelle.")

        print("\n--- d) bbox-Breite etwaiger rawdict-Leerzeichen-Einträge ---")
        zero_width_count = 0
        real_glyph_width_count = 0
        if space_entries:
            for bbox in space_entries:
                width = bbox.x1 - bbox.x0
                is_zero_width = width < 0.5
                if is_zero_width:
                    zero_width_count += 1
                else:
                    real_glyph_width_count += 1
                kind = "Null-Breite-Platzhalter" if is_zero_width else "Breite Glyphe (siehe d.1 unten - kann auch eine von PyMuPDFs Lücken-Heuristik SYNTHETISIERTE Glyphe sein, nicht zwangsläufig ein echtes PDF-Space-Zeichen)"
                print(f"    bbox=({bbox.x0:7.2f},{bbox.y0:7.2f},{bbox.x1:7.2f},{bbox.y1:7.2f})  breite={width:.2f}pt  -> {kind}")
        else:
            print("  (keine rawdict-Einträge mit c=' ' an dieser Fundstelle)")

        print("\n--- d.1) Gegenprobe: rawdict MIT TEXT_INHIBIT_SPACES an derselben Stelle ---")
        rawdict_inhibited = page.get_text("rawdict", clip=clip, flags=pymupdf.TEXT_INHIBIT_SPACES)
        flat_inhibited = _flatten_rawdict(rawdict_inhibited)
        inhibited_text = "".join(c for c, _, _, _ in flat_inhibited)
        inhibited_space_count = sum(1 for c, _, _, _ in flat_inhibited if c == " ")
        print(f"  rawdict('c'-Felder) MIT TEXT_INHIBIT_SPACES -> {inhibited_text!r}")
        print(f"  davon Einträge mit c=' ': {inhibited_space_count} (ohne Flag waren es {rawdict_space_count})")
        rawdict_flag_sensitive = real_glyph_width_count > 0 and inhibited_space_count < rawdict_space_count

        print("\n--- e) Fazit ---")
        if rawdict_space_count == 0 and text_space_count > 0:
            print(
                "  rawdict (ohne Flags) enthält an dieser Stelle NUR reale Glyphen, keine abgeleiteten "
                "Leerzeichen. get_text('text') fügt die Leerzeichen selbst ein (Lücken-Heuristik). Eine "
                "Wortrekonstruktion auf rawdict-Basis ist hier geradlinig."
            )
        elif rawdict_flag_sensitive:
            print(
                "  WICHTIG - Korrektur der bisherigen Annahme: rawdict ist NICHT grundsätzlich frei von "
                "abgeleiteten Leerzeichen. An dieser Stelle enthält rawdict (ohne Flags) dieselbe Anzahl "
                "Leerzeichen-Einträge wie get_text('text') (siehe (c)), UND diese Einträge verschwinden "
                f"unter TEXT_INHIBIT_SPACES ({rawdict_space_count} -> {inhibited_space_count}, siehe d.1) "
                "- das beweist, dass es sich um dieselbe, von PyMuPDF synthetisierte Lücken-Heuristik "
                "handelt wie bei get_text('text'), nicht um echte PDF-Space-Zeichen mit breiter, aber "
                "realer Glyphe. Eine Wortrekonstruktion auf rawdict-Basis MUSS diese synthetischen "
                "Leerzeichen also selbst erkennen und verwerfen (z.B. durch rawdict mit "
                "TEXT_INHIBIT_SPACES abrufen, oder Einträge mit c=' ' vor der Wortbildung filtern), "
                "sie kann sich NICHT darauf verlassen, dass rawdict automatisch nur reale Glyphen liefert."
            )
        elif rawdict_space_count > 0:
            print(
                "  rawdict enthält an dieser Stelle Leerzeichen-Einträge, die auch unter "
                "TEXT_INHIBIT_SPACES erhalten bleiben (siehe d.1) - das spricht für echte, im "
                "Content-Stream vorhandene Space-Zeichen statt einer reinen Lücken-Heuristik. Eine "
                "Wortrekonstruktion auf rawdict-Basis kann diese Einträge direkt als Wortgrenzen "
                "übernehmen."
            )
        else:
            print(
                "  Uneindeutiger Fall - bitte (a)-(d.1) oben im Detail prüfen."
            )
    finally:
        doc.close()
    return 0


_FOOTER_ZONE_FRACTION = 0.85  # unterste 15% der Seitenhöhe gelten als Fußzeilen-Bereich
_MIN_SAMPLE_TEXT_LEN = 30  # Mindestlänge, damit eine Stichprobe aussagekräftig ist


def _count_real_spaces(pdf_path: str):
    """(a) Gesamtzahl echter chr(32)-Zeichen im Zeichenstrom über alle Seiten,
    plus Anzahl Seiten mit mindestens einem solchen Zeichen."""
    doc = pymupdf.open(pdf_path)
    try:
        total_spaces = 0
        pages_with_space = 0
        for page in doc:
            page_spaces = sum(
                1
                for span in page.get_texttrace()
                for ch in span["chars"]
                if ch[0] == 32
            )
            total_spaces += page_spaces
            if page_spaces > 0:
                pages_with_space += 1
        return total_spaces, pages_with_space, len(doc)
    finally:
        doc.close()


def _flow_text_samples(pdf_path: str, num_samples: int) -> List[tuple]:
    """Sucht Fließtext-Blöcke (nicht die untersten _FOOTER_BLOCK_COUNT Blöcke
    einer Seite, siehe _print_footer_buckets) mit ausreichender Textlänge,
    seitenweise, bis num_samples Stichproben gefunden sind. Gibt
    (page_index, bbox_tuple, text_preview) zurück."""
    samples = []
    doc = pymupdf.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            if len(samples) >= num_samples:
                break
            page = doc[page_index]
            blocks = get_text_blocks(page)
            if not blocks:
                continue
            footer_threshold = page.rect.height * _FOOTER_ZONE_FRACTION
            flow_blocks = [b for b in blocks if b[1] < footer_threshold]
            for b in flow_blocks:
                if len(samples) >= num_samples:
                    break
                if len(b[4].strip()) >= _MIN_SAMPLE_TEXT_LEN:
                    samples.append((page_index, (b[0], b[1], b[2], b[3])))
    finally:
        doc.close()
    return samples


def _print_inhibit_samples(pdf_path: str, label: str, num_samples: int) -> bool:
    """(b) Fließtext-Stichproben normal vs. TEXT_INHIBIT_SPACES nebeneinander.
    Gibt True zurück, wenn mindestens eine Stichprobe unter INHIBIT_SPACES
    weniger durch Leerzeichen getrennte Wörter enthält als normal
    (Heuristik-Warnsignal für Wortverschmelzung)."""
    print(f"\n--- b) Fließtext-Stichproben: {label} ---")
    samples = _flow_text_samples(pdf_path, num_samples)
    if not samples:
        print("  (keine ausreichend langen Fließtext-Blöcke gefunden)")
        return False

    merged_words_detected = False
    doc = pymupdf.open(pdf_path)
    try:
        for sample_no, (page_index, bbox) in enumerate(samples, start=1):
            page = doc[page_index]
            clip = pymupdf.Rect(bbox)
            normal = page.get_text("text", clip=clip).strip().replace("\n", " \\n ")
            inhibited = page.get_text("text", clip=clip, flags=pymupdf.TEXT_INHIBIT_SPACES).strip().replace("\n", " \\n ")
            normal_words = len(normal.split())
            inhibited_words = len(inhibited.split())
            print(f"\n  Stichprobe {sample_no} (Seite {page_index + 1}):")
            print(f"    normal            -> {normal!r}")
            print(f"    TEXT_INHIBIT_SPACES -> {inhibited!r}")
            print(f"    Wortanzahl normal={normal_words}  inhibited={inhibited_words}")
            if inhibited_words < normal_words:
                merged_words_detected = True
                print("    WARNUNG: weniger Wörter unter TEXT_INHIBIT_SPACES -> Wortverschmelzung wahrscheinlich")
    finally:
        doc.close()
    return merged_words_detected


def _check_inhibit_spaces(ref_pdf: str, cnd_pdf: str, num_samples: int) -> int:
    print(f"Referenz: {ref_pdf}")
    print(f"Kandidat: {cnd_pdf}")

    results = {}
    for label, path in (("Referenz", ref_pdf), ("Kandidat", cnd_pdf)):
        total_spaces, pages_with_space, total_pages = _count_real_spaces(path)
        print(f"\n--- a) Echte Space-Zeichen im Zeichenstrom: {label} ---")
        print(f"  Gesamtzahl chr(32) über alle Seiten: {total_spaces}")
        print(f"  Seiten mit mindestens einem chr(32): {pages_with_space} / {total_pages}")
        merged_words_detected = _print_inhibit_samples(path, label, num_samples)
        results[label] = (total_spaces, pages_with_space, total_pages, merged_words_detected)

    print("\n--- d) Fazit ---")
    risky = False
    for label, (total_spaces, pages_with_space, total_pages, merged_words_detected) in results.items():
        if merged_words_detected:
            print(f"  {label}: mindestens eine Fließtext-Stichprobe verschmilzt unter TEXT_INHIBIT_SPACES "
                  f"zu weniger Wörtern -> Flag ist für dieses Dokument NICHT sicher.")
            risky = True
        elif total_spaces == 0:
            print(f"  {label}: 0 echte Space-Zeichen im gesamten Dokument gefunden, aber die Stichproben "
                  f"zeigen keine Wortverschmelzung unter TEXT_INHIBIT_SPACES -> an den Stichproben unauffällig, "
                  f"bitte trotzdem die Ausgabe oben visuell prüfen (Stichproben sind keine Vollabdeckung).")
        else:
            print(f"  {label}: {total_spaces} echte Space-Zeichen auf {pages_with_space}/{total_pages} Seiten "
                  f"gefunden, Stichproben zeigen keine Wortverschmelzung -> Flag wirkt für dieses Dokument sicher.")

    if risky:
        print("\n  GESAMTERGEBNIS: TEXT_INHIBIT_SPACES ist für dieses Dateipaar NICHT ohne weiteres sicher.")
    else:
        print("\n  GESAMTERGEBNIS: An den geprüften Stichproben ist TEXT_INHIBIT_SPACES für dieses Dateipaar "
              "unauffällig - für eine abschließende Aussage bitte die Stichproben oben durchsehen, da sie das "
              "Dokument nicht vollständig abdecken.")
    return 0


def _calibration_report(pdf_path: str) -> int:
    """Nachvollziehbarkeit der Space-Breiten-Kalibrierung für die rawdict-
    Wortrekonstruktion (engine.pdf_extractor.calibrate_spacewidths): pro
    Schrift Quelle, Datenbasis und ob das Klarheits-Kriterium erfüllt war."""
    print(f"Datei: {pdf_path}")
    doc = pymupdf.open(pdf_path)
    try:
        calibration = calibrate_spacewidths(doc)
    finally:
        doc.close()

    if not calibration:
        print("  (keine Schriften mit horizontalem Text gefunden)")
        return 0

    print(f"\n{'Font':<25} {'Größe':>6} {'Spacewidth':>11} {'Quelle':<20} {'Messwerte':>10} {'Kriterium erfüllt':>18}")
    for (font, size), cal in sorted(calibration.items()):
        spacewidth_str = f"{cal.spacewidth:.2f}pt" if cal.spacewidth is not None else "-"
        print(
            f"{font:<25} {size:>6.1f} {spacewidth_str:>11} {cal.source:<20} "
            f"{cal.sample_count:>10} {str(cal.criterion_met):>18}"
        )

    not_reconstructable = [f"{font} {size:.1f}pt" for (font, size), cal in calibration.items() if not cal.criterion_met]
    if not_reconstructable:
        print(
            f"\n  Hinweis: Für {len(not_reconstructable)} Schrift(en) ohne belastbare Kalibrierung "
            f"bleibt die native Extraktion unverändert: {', '.join(not_reconstructable)}"
        )
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref_pdf", help="Pfad zur Referenz-PDF (im --inspect-word-Modus: die zu untersuchende PDF)")
    parser.add_argument("cnd_pdf", nargs="?", default=None, help="Pfad zur Kandidat-PDF (nicht im --inspect-word-Modus)")
    parser.add_argument("--case-insensitive", action="store_true", help="Vergleich case-insensitive (Default: case-sensitive)")
    parser.add_argument("--limit", type=int, default=10, help="Anzahl der anzuzeigenden Deltas (Default 10)")
    parser.add_argument("--footer-pages", type=int, default=3, help="Anzahl Seiten für die Fußzeilen-Bucket-Ausgabe (Default 3)")
    parser.add_argument("--inspect-word", metavar="SUCHBEGRIFF", default=None, help="Wort-Diagnose statt Delta-Vergleich (H1 Sperrsatz vs. H2 OCR)")
    parser.add_argument("--page", type=int, default=None, help="Seitennummer (1-basiert) für --inspect-word")
    parser.add_argument(
        "--check-inhibit-spaces",
        action="store_true",
        help="Prüft, ob TEXT_INHIBIT_SPACES für dieses ref/cnd-Dateipaar gefahrlos ist "
        "(echte Space-Zeichen zählen + Fließtext-Stichproben normal vs. inhibiert)",
    )
    parser.add_argument("--samples", type=int, default=3, help="Anzahl Fließtext-Stichproben für --check-inhibit-spaces (Default 3)")
    parser.add_argument("--inspect-encoding", metavar="SUCHBEGRIFF", default=None, help="Encoding-Diagnose für Umlaut-Defekte (get_texttrace/rawdict/words/pdfplumber + Font/ToUnicode-Analyse)")
    parser.add_argument("--inspect-rawdict", metavar="SUCHBEGRIFF", default=None, help="Prüft, ob rawdict an der Fundstelle abgeleitete Leerzeichen enthält oder nur reale Glyphen")
    parser.add_argument(
        "--calibration-report",
        action="store_true",
        help="Zeigt die Space-Breiten-Kalibrierung je Schrift für die rawdict-Wortrekonstruktion (ref_pdf)",
    )
    args = parser.parse_args(argv)

    if args.calibration_report:
        if args.cnd_pdf is not None:
            parser.error("--calibration-report erwartet nur eine PDF-Datei (ref_pdf), kein cnd_pdf.")
        return _calibration_report(args.ref_pdf)

    if args.inspect_word is not None:
        if args.cnd_pdf is not None:
            parser.error("--inspect-word erwartet nur eine PDF-Datei (ref_pdf), kein cnd_pdf.")
        if args.page is None:
            parser.error("--inspect-word erfordert --page N.")
        return _inspect_word(args.ref_pdf, args.inspect_word, args.page)

    if args.inspect_encoding is not None:
        if args.cnd_pdf is not None:
            parser.error("--inspect-encoding erwartet nur eine PDF-Datei (ref_pdf), kein cnd_pdf.")
        if args.page is None:
            parser.error("--inspect-encoding erfordert --page N.")
        return _inspect_encoding(args.ref_pdf, args.inspect_encoding, args.page)

    if args.inspect_rawdict is not None:
        if args.cnd_pdf is not None:
            parser.error("--inspect-rawdict erwartet nur eine PDF-Datei (ref_pdf), kein cnd_pdf.")
        if args.page is None:
            parser.error("--inspect-rawdict erfordert --page N.")
        return _inspect_rawdict(args.ref_pdf, args.inspect_rawdict, args.page)

    if args.cnd_pdf is None:
        parser.error("cnd_pdf ist erforderlich, außer im --inspect-word-Modus.")

    if args.check_inhibit_spaces:
        return _check_inhibit_spaces(args.ref_pdf, args.cnd_pdf, args.samples)

    case_sensitive = not args.case_insensitive

    print(f"Lese Referenz:  {args.ref_pdf}")
    print(f"Lese Kandidat:  {args.cnd_pdf}")
    ref_pages = extract_pages(args.ref_pdf)
    cnd_pages = extract_pages(args.cnd_pdf)
    print(f"Seiten: Referenz={len(ref_pages)}  Kandidat={len(cnd_pages)}")

    _print_deltas(ref_pages, cnd_pages, case_sensitive=case_sensitive, limit=args.limit)

    _char_inventory(ref_pages, "Referenz")
    _char_inventory(cnd_pages, "Kandidat")

    _print_footer_buckets(args.ref_pdf, "Referenz", num_pages=args.footer_pages)
    _print_footer_buckets(args.cnd_pdf, "Kandidat", num_pages=args.footer_pages)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
