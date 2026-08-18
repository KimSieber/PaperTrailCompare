# file:    engine/text_comparator.py
# purpose: Core comparison logic: normalizes extracted PDF text (hyphenation,
#          whitespace) and compares via difflib in three modes (words, chars,
#          hybrid). Returns CompareResult with page-level Delta positions.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Vergleichskern: normalisiert und vergleicht extrahierten PDF-Text.

Nimmt pro Dokument eine Liste von Seitentexten entgegen (ein String pro Seite),
damit Deltas mit Seiten- und Positionsangabe gemeldet werden können, auch wenn
sich der Seitenumbruch zwischen Referenz- und Kandidat-Dokument verschiebt.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Tuple

_HYPHENATION_RE = re.compile(r"(?<=\w)-\s*\n\s*(?=\w)")
_WHITESPACE_RE = re.compile(r"\s+")
_ORPHAN_HYPHEN_RE = re.compile(r"(\w) - ")

_VALID_COMPARE_MODES = ("words", "chars", "hybrid")

# Länge (in Wort-Tokens) eines equal-Laufs, unterhalb derer er beim
# hybriden Vergleich als zufällige Übereinstimmung statt als echter
# Synchronisationspunkt gilt (siehe _merge_fragmented_opcodes). Empirisch
# auf den TC_REAL-Dateien belegt: alle so gefundenen nützlichen Merges
# betrafen genau einen einzelnen übereinstimmenden Wort-Token - ab zwei
# aufeinanderfolgenden Wörtern ist eine zufällige Übereinstimmung in
# natürlicher Sprache unwahrscheinlich genug, um als echte Synchronisation
# zu gelten.
_HYBRID_MAX_ACCIDENTAL_EQUAL_RUN = 1


@dataclass
class Delta:
    page: int
    position: int
    ref_text: str
    cnd_text: str
    # (x0, y0, x1, y1) in PDF-Seitenkoordinaten der compare_region, aus der
    # dieses Delta stammt (siehe engine.compare_region_comparator) - None
    # für alle "normalen" (nicht regionsbasierten) Deltas, bedeutet "keine
    # Einschränkung, ganze Seite durchsuchen". Wird ausschließlich vom
    # report_generator konsumiert (page.search_for(text, clip=...), siehe
    # docs/prompt_region_clip_highlighting.md) - rein Python-intern, MUSS
    # aus der JSON-Ausgabe ausgeschlossen bleiben (siehe engine.__main__).
    region_clip: Optional[Tuple[float, float, float, float]] = None


@dataclass
class CompareResult:
    has_delta: bool
    deltas: List[Delta] = field(default_factory=list)
    ocr_was_used: bool = False


def normalize_text(
    text: str,
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
) -> str:
    """Führt Silbentrennungen am Zeilenende zusammen und normalisiert Whitespace.

    _HYPHENATION_RE verlangt ein Wortzeichen unmittelbar VOR dem Bindestrich
    und eines unmittelbar NACH dem Umbruch (Lookbehind/Lookahead) - nur dann
    handelt es sich um echte Silbentrennung ('Silben-\\ntrennung'). Ein
    isolierter Gedankenstrich (Whitespace/Zeilenumbruch davor, z.B. weil er
    in einem Ein-Wort-pro-Zeile-Layout zufällig allein auf einer Zeile
    steht) wird nicht entfernt - siehe Diagnose-Session: in einem echten
    Dokument stand '...Verlässlichkeit\\n-\\nvielen Dank...', wobei der
    Strich Satzzeichen war, aber wie Silbentrennung behandelt wurde und
    verschwand ('' vs. '-' als falsches Delta, 8 von 220 betroffen).

    merge_hyphenation=False deaktiviert _HYPHENATION_RE vollständig - für
    Dokumenttypen, bei denen zusammengesetzte Bindestriche (z.B. 'Stück-
    und') von der Extraktion mit einem Zeilenumbruch statt einem Leerzeichen
    getrennt werden (Papyrus-Formatierer, der einen visuellen Zeilenumbruch
    in mehrere Content-Stream-Operationen aufteilt) und _HYPHENATION_RE das
    fälschlich als Silbentrennung erkennt und den Bindestrich entfernt
    ('Stück- und' -> 'Stückund', falsches Delta). Extraktion selbst kann
    hierfür nicht sicher angepasst werden (siehe Sprint PTC-S3 Task A);
    stattdessen wird das per Profil abschaltbar gemacht.

    normalize_orphan_hyphens=True (Default) hängt danach einen Bindestrich,
    der isoliert zwischen Leerzeichen steht ('Stück - und'), wieder an das
    vorangehende Wort an ('Stück- und') - Folgezustand desselben Papyrus-
    Musters wie oben, wenn der Bindestrich in eine eigene rawdict-Zeile
    fällt und PyMuPDF ihn dadurch beidseitig mit Leerzeichen umgibt statt
    ihn direkt ans Wort zu hängen (siehe Sprint PTC-S3 Task A2). Läuft
    unabhängig von merge_hyphenation und NACH der Whitespace-Kollabierung,
    da _ORPHAN_HYPHEN_RE auf genau einem Leerzeichen vor/nach dem
    Bindestrich beruht."""
    if merge_hyphenation:
        text = _HYPHENATION_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if normalize_orphan_hyphens:
        text = _ORPHAN_HYPHEN_RE.sub(r"\1- ", text)
    return text


def _words_with_pages(
    pages: Sequence[str],
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
):
    """Normalisiert jede Seite (normalize_text) und zerlegt sie in Wörter,
    gibt dabei zu jedem Wort die 1-basierte Seitenzahl mit zurück - Grundlage
    für _compare_words(), das darüber Deltas ihrer Ursprungsseite zuordnet."""
    words: List[str] = []
    word_pages: List[int] = []
    for page_num, page_text in enumerate(pages, start=1):
        normalized = normalize_text(
            page_text,
            merge_hyphenation=merge_hyphenation,
            normalize_orphan_hyphens=normalize_orphan_hyphens,
        )
        for word in normalized.split(" "):
            if not word:
                continue
            words.append(word)
            word_pages.append(page_num)
    return words, word_pages


def _chars_with_pages(
    pages: Sequence[str],
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
) -> Tuple[str, List[int], str, List[Tuple[int, int]]]:
    """Baut aus pages eine kompakte, whitespace-freie Zeichenkette für den
    zeichenbasierten Vergleich (compare_mode="chars") - für Dokumente, deren
    Wortgrenzen unzuverlässig sind (z.B. Type3-Schriften ohne ToUnicode-
    Tabelle, siehe Diagnose-Session), sodass wortbasierter Vergleich
    Rauschen als Delta meldet.

    Jede Seite wird zunächst wie im Wortmodus normalisiert (Silbentrennung
    zusammenführen, Whitespace kollabieren), damit Delta-Texte in beiden
    Modi gleich aussehen; die Seiten werden dann mit "\\n" zu original_text
    verbunden.

    Rückgabe: (compact, compact_to_original, original_text, page_boundaries)
    - compact: original_text ohne jegliches Whitespace-Zeichen.
    - compact_to_original[i]: Position des i-ten kompakten Zeichens in
      original_text - Index-Tabelle, um Delta-Bereiche aus dem Matcher
      (der auf compact läuft) auf lesbaren Text mit Leerzeichen
      zurückzurechnen (siehe _char_range_to_text).
    - page_boundaries: sortierte (offset, page_num)-Paare, ein Eintrag pro
      Seitenanfang in original_text - Pendant zu word_pages im Wortmodus,
      aber offset- statt indexbasiert (siehe _page_for_offset).
    """
    original_parts: List[str] = []
    page_boundaries: List[Tuple[int, int]] = []
    compact_chars: List[str] = []
    compact_to_original: List[int] = []
    offset = 0

    for page_num, page_text in enumerate(pages, start=1):
        if original_parts:
            original_parts.append("\n")
            offset += 1
        page_boundaries.append((offset, page_num))
        normalized = normalize_text(
            page_text,
            merge_hyphenation=merge_hyphenation,
            normalize_orphan_hyphens=normalize_orphan_hyphens,
        )
        for ch in normalized:
            if not ch.isspace():
                compact_chars.append(ch)
                compact_to_original.append(offset)
            offset += 1
        original_parts.append(normalized)

    return "".join(compact_chars), compact_to_original, "".join(original_parts), page_boundaries


def _page_for_offset(page_boundaries: Sequence[Tuple[int, int]], offset: int) -> int:
    """Liefert die Seitenzahl, auf der offset in original_text liegt -
    letzter Seitenanfang mit start_offset <= offset (page_boundaries ist
    nach start_offset aufsteigend sortiert, siehe _chars_with_pages)."""
    if not page_boundaries:
        return 0
    starts = [b[0] for b in page_boundaries]
    idx = bisect_right(starts, offset) - 1
    idx = max(0, min(idx, len(page_boundaries) - 1))
    return page_boundaries[idx][1]


def _char_range_to_text(
    compact_to_original: Sequence[int], original_text: str, start: int, end: int
) -> Tuple[str, int]:
    """Übersetzt einen Bereich [start:end) aus Indizes in der kompakten
    Zeichenkette zurück in (lesbarer Text mit Leerzeichen, Original-Offset
    des Bereichsanfangs) - der Offset wird für _page_for_offset benötigt.

    Bei leerem Bereich (reine Einfügung/Löschung, start==end) gibt es kein
    eigenes kompaktes Zeichen als Anker; genau wie im Wortmodus
    (cnd_word_pages[j1] mit Fallback) wird dann die Position des nächsten
    (oder, falls am Ende, letzten) kompakten Zeichens verwendet."""
    if start < end:
        orig_start = compact_to_original[start]
        orig_end = compact_to_original[end - 1] + 1
        return original_text[orig_start:orig_end], orig_start
    if start < len(compact_to_original):
        orig_start = compact_to_original[start]
    elif compact_to_original:
        orig_start = compact_to_original[-1] + 1
    else:
        orig_start = 0
    return "", orig_start


def _is_whitespace_only_difference(ref_text: str, cnd_text: str, case_sensitive: bool) -> bool:
    """Prüft, ob sich ref_text/cnd_text nur durch (fälschlich eingefügte
    oder fehlende) Leerzeichen unterscheiden, z.B. OCR-Wort-Trennfehler
    wie 'Vertragsbedingungen' -> 'Vertrags bedingungen'. Wird pro
    Delta-Kandidat geprüft (nicht global), damit ein echter Unterschied an
    anderer Stelle im Dokument diese Erkennung nicht verdeckt."""
    compact_ref = ref_text.replace(" ", "")
    compact_cnd = cnd_text.replace(" ", "")
    if not case_sensitive:
        compact_ref = compact_ref.lower()
        compact_cnd = compact_cnd.lower()
    return compact_ref == compact_cnd


def _compare_words(
    ref_pages: Sequence[str],
    cnd_pages: Sequence[str],
    case_sensitive: bool,
    normalize_whitespace: bool,
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
) -> List[Delta]:
    """Vergleicht Referenz- und Kandidat-Seiten wortweise (nach Normalisierung
    via _words_with_pages) und liefert die Liste der gefundenen Deltas
    inklusive Seiten- und Positionsangabe. case_sensitive/normalize_whitespace
    steuern die Toleranz beim Wortvergleich (siehe CompareResult/Delta)."""
    ref_words, _ = _words_with_pages(
        ref_pages, merge_hyphenation=merge_hyphenation, normalize_orphan_hyphens=normalize_orphan_hyphens
    )
    cnd_words, cnd_word_pages = _words_with_pages(
        cnd_pages, merge_hyphenation=merge_hyphenation, normalize_orphan_hyphens=normalize_orphan_hyphens
    )

    if case_sensitive:
        ref_keys, cnd_keys = ref_words, cnd_words
    else:
        ref_keys = [w.lower() for w in ref_words]
        cnd_keys = [w.lower() for w in cnd_words]

    matcher = SequenceMatcher(a=ref_keys, b=cnd_keys, autojunk=False)
    deltas: List[Delta] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref_text = " ".join(ref_words[i1:i2])
        cnd_text = " ".join(cnd_words[j1:j2])
        if normalize_whitespace and _is_whitespace_only_difference(ref_text, cnd_text, case_sensitive):
            continue
        page = cnd_word_pages[j1] if j1 < len(cnd_word_pages) else (
            cnd_word_pages[-1] if cnd_word_pages else 0
        )
        deltas.append(Delta(page=page, position=j1, ref_text=ref_text, cnd_text=cnd_text))
    return deltas


def _merge_fragmented_opcodes(
    opcodes: Sequence[Tuple[str, int, int, int, int]]
) -> List[Tuple[str, int, int, int, int]]:
    """Fasst benachbarte nicht-gleiche Opcodes zusammen, die durch einen
    einzelnen (siehe _HYBRID_MAX_ACCIDENTAL_EQUAL_RUN) zufällig
    übereinstimmenden Wort-Token getrennt sind.

    Grund: bei fragmentierten Wortgrenzen (Type3-Defekt) matcht ein
    kurzes, häufiges Wort (z.B. 'der', 'in', 'die') mitten im Fragmen-
    tierungsrauschen manchmal zufällig auf beiden Seiten - SequenceMatcher
    wertet das als Synchronisationspunkt und zerlegt eine an sich
    zusammenhängende Fragmentierung in zwei separate Opcodes, die EINZELN
    nicht whitespace-identisch sind (siehe _is_whitespace_only_difference),
    zusammen aber schon. Ohne diese Zusammenfassung bleiben solche Stellen
    fälschlich Deltas.

    Ab zwei aufeinanderfolgenden übereinstimmenden Wörtern gilt der Treffer
    als echte Synchronisation und bleibt eine Grenze zwischen zwei
    Bereichen - eine zufällige Übereinstimmung von zwei Wörtern in Folge
    ist in natürlicher Sprache unwahrscheinlich genug, um verlässlich zu sein.
    """
    merged: List[Tuple[str, int, int, int, int]] = []
    i = 0
    n = len(opcodes)
    while i < n:
        tag, i1, i2, j1, j2 = opcodes[i]
        if tag == "equal":
            merged.append(opcodes[i])
            i += 1
            continue

        region_i1, region_i2, region_j1, region_j2 = i1, i2, j1, j2
        merged_any = False
        i += 1
        while (
            i + 1 < n
            and opcodes[i][0] == "equal"
            and (opcodes[i][2] - opcodes[i][1]) <= _HYBRID_MAX_ACCIDENTAL_EQUAL_RUN
            and opcodes[i + 1][0] != "equal"
        ):
            _, _, n_i2, _, n_j2 = opcodes[i + 1]
            region_i2, region_j2 = n_i2, n_j2
            merged_any = True
            i += 2

        merged.append(
            ("replace" if merged_any else tag, region_i1, region_i2, region_j1, region_j2)
        )
    return merged


def _compare_hybrid(
    ref_pages: Sequence[str],
    cnd_pages: Sequence[str],
    case_sensitive: bool,
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
) -> List[Delta]:
    """Zweistufiger Vergleich (compare_mode="hybrid"): löst die Explosion
    kleiner, über weite Bereiche verstreuter Deltas, die reiner
    Zeichenvergleich auf strukturell bereits abweichenden Textstellen
    erzeugt (siehe Messung: 388 im Wortmodus -> 1024 im Zeichenmodus auf
    denselben Dateien).

    Stufe 1: Wort-Matcher wie im Wortmodus (autojunk=False) - liefert die
    grobe Ausrichtung, die im reinen Zeichenmodus fehlt und dort zu
    zufälligen Kurz-Teilstring-Treffern über den gesamten Bereich führt.

    Stufe 2: benachbarte nicht-gleiche Opcodes werden zusammengefasst
    (siehe _merge_fragmented_opcodes), dann wird je zusammengefasstem
    Bereich die kompakte (whitespace-freie) Form verglichen - identisch:
    kein Delta; unterschiedlich: EIN Delta über den gesamten Bereich, Text
    aus dem Original (mit Leerzeichen), wie im Wortmodus. Das ist derselbe
    Vergleich wie _is_whitespace_only_difference, nur auf den zusammen-
    gefassten Bereich statt auf einen einzelnen Opcode angewendet - deshalb
    hier unconditional (nicht hinter normalize_whitespace), das Zusammen-
    fassen ist der eigentliche Kern dieses Modus, nicht ein optionales
    Zusatzverhalten."""
    ref_words, _ = _words_with_pages(
        ref_pages, merge_hyphenation=merge_hyphenation, normalize_orphan_hyphens=normalize_orphan_hyphens
    )
    cnd_words, cnd_word_pages = _words_with_pages(
        cnd_pages, merge_hyphenation=merge_hyphenation, normalize_orphan_hyphens=normalize_orphan_hyphens
    )

    if case_sensitive:
        ref_keys, cnd_keys = ref_words, cnd_words
    else:
        ref_keys = [w.lower() for w in ref_words]
        cnd_keys = [w.lower() for w in cnd_words]

    matcher = SequenceMatcher(a=ref_keys, b=cnd_keys, autojunk=False)
    regions = _merge_fragmented_opcodes(matcher.get_opcodes())

    deltas: List[Delta] = []
    for tag, i1, i2, j1, j2 in regions:
        if tag == "equal":
            continue
        ref_text = " ".join(ref_words[i1:i2])
        cnd_text = " ".join(cnd_words[j1:j2])
        if _is_whitespace_only_difference(ref_text, cnd_text, case_sensitive):
            continue
        page = cnd_word_pages[j1] if j1 < len(cnd_word_pages) else (
            cnd_word_pages[-1] if cnd_word_pages else 0
        )
        deltas.append(Delta(page=page, position=j1, ref_text=ref_text, cnd_text=cnd_text))
    return deltas


def _compare_chars(
    ref_pages: Sequence[str],
    cnd_pages: Sequence[str],
    case_sensitive: bool,
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
) -> List[Delta]:
    """Zeichenbasierter Vergleich (compare_mode="chars"): ignoriert
    jeglichen Whitespace vollständig, statt auf Wortgrenzen zu vertrauen -
    für Dokumente wie Type3-Schriften ohne ToUnicode-Tabelle, bei denen
    PyMuPDFs Leerzeichen-Heuristik Wortgrenzen wortselektiv falsch setzt
    (siehe Diagnose-Session: 'Versicherung' vs. 'Versi ch e ru n g').

    autojunk=True (Default von SequenceMatcher) ist hier absichtlich anders
    als im Wortmodus (dort autojunk=False): auf ~150.000 Einzelzeichen
    macht autojunk=False den Matcher wegen extrem häufiger Buchstaben
    (e, n, r, s, t, a, i) praktisch unbenutzbar (gemessen: ~600s statt
    ~10s auf den TC_REAL-Dateien). Ein Qualitätstest mit einem großen
    synthetischen Dokumentpaar und gezielt eingebauten Änderungen
    (test_text_comparator.py) belegt, dass autojunk=True dabei keine
    Unterschiede verschluckt oder erfindet - Änderungen werden ggf. in
    mehrere kleinere Deltas aufgesplittet (z.B. ein Datum mit zufällig
    übereinstimmenden Ziffern), aber nicht verloren."""
    ref_compact, ref_map, ref_original, ref_boundaries = _chars_with_pages(
        ref_pages, merge_hyphenation=merge_hyphenation, normalize_orphan_hyphens=normalize_orphan_hyphens
    )
    cnd_compact, cnd_map, cnd_original, cnd_boundaries = _chars_with_pages(
        cnd_pages, merge_hyphenation=merge_hyphenation, normalize_orphan_hyphens=normalize_orphan_hyphens
    )

    if case_sensitive:
        ref_keys, cnd_keys = ref_compact, cnd_compact
    else:
        ref_keys, cnd_keys = ref_compact.lower(), cnd_compact.lower()

    matcher = SequenceMatcher(a=ref_keys, b=cnd_keys, autojunk=True)
    deltas: List[Delta] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref_text, _ = _char_range_to_text(ref_map, ref_original, i1, i2)
        cnd_text, cnd_offset = _char_range_to_text(cnd_map, cnd_original, j1, j2)
        page = _page_for_offset(cnd_boundaries, cnd_offset)
        deltas.append(Delta(page=page, position=j1, ref_text=ref_text, cnd_text=cnd_text))
    return deltas


def compare(
    ref_pages: Sequence[str],
    cnd_pages: Sequence[str],
    case_sensitive: bool = True,
    normalize_whitespace: bool = False,
    ocr_used: bool = False,
    compare_mode: str = "words",
    merge_hyphenation: bool = True,
    normalize_orphan_hyphens: bool = True,
) -> CompareResult:
    """Vergleicht Referenz- und Kandidat-Text seitenweise, ignoriert dabei
    Seitenumbrüche und Silbentrennung.

    case_sensitive=False ignoriert Groß-/Kleinschreibung beim Vergleich
    (TC-T-006); ref_text/cnd_text in den Deltas behalten die Originalschreibung.

    normalize_whitespace=True verwirft Delta-Kandidaten, die sich nur durch
    Leerzeichen unterscheiden (z.B. OCR-bedingte Wort-Trennfehler) - ein
    Delta, das auch einen echten Textunterschied enthält, bleibt bestehen.
    Gilt nur für compare_mode="words" - in "chars"/"hybrid" ist Whitespace
    ohnehin vollständig aus dem Vergleich entfernt bzw. wird bereichsweise
    ignoriert, das Flag wird dort einfach ignoriert (kein Fehler, keine
    Sonderbehandlung nötig).

    compare_mode="chars" vergleicht auf Zeichenebene statt auf Wort-Tokens
    (siehe _compare_chars) - für Dokumente, deren Wortgrenzen bei der
    Extraktion unzuverlässig sind. Auf Dokumenten mit vielen bereits
    strukturell abweichenden Textstellen kann das zu einer Explosion
    kleiner, verstreuter Deltas führen (siehe Messung: 388 im Wortmodus ->
    1024 im Zeichenmodus auf denselben Dateien) - dafür gibt es
    compare_mode="hybrid" (siehe _compare_hybrid): Wort-Matcher zur groben
    Ausrichtung, Zeichenvergleich (kompakte Form) nur innerhalb der so
    gefundenen, zusammengefassten Bereiche. Kein Default für "chars" oder
    "hybrid", weil andere Dokumenttypen intakte Wortgrenzen haben, bei
    denen beide unnötig Rechenzeit kosten.

    ocr_used wird unverändert in CompareResult.ocr_was_used übernommen, damit
    Aufrufer (z.B. der Report) sichtbar machen können, ob die Texte über
    OCR statt nativer PDF-Extraktion gewonnen wurden.
    """
    if compare_mode not in _VALID_COMPARE_MODES:
        raise ValueError(f"compare_mode muss einer von {_VALID_COMPARE_MODES} sein, ist {compare_mode!r}")

    if compare_mode == "chars":
        deltas = _compare_chars(
            ref_pages, cnd_pages, case_sensitive,
            merge_hyphenation=merge_hyphenation,
            normalize_orphan_hyphens=normalize_orphan_hyphens,
        )
    elif compare_mode == "hybrid":
        deltas = _compare_hybrid(
            ref_pages, cnd_pages, case_sensitive,
            merge_hyphenation=merge_hyphenation,
            normalize_orphan_hyphens=normalize_orphan_hyphens,
        )
    else:
        deltas = _compare_words(
            ref_pages, cnd_pages, case_sensitive, normalize_whitespace,
            merge_hyphenation=merge_hyphenation,
            normalize_orphan_hyphens=normalize_orphan_hyphens,
        )

    return CompareResult(has_delta=bool(deltas), deltas=deltas, ocr_was_used=ocr_used)
