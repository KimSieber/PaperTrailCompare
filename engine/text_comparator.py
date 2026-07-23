"""Vergleichskern: normalisiert und vergleicht extrahierten PDF-Text.

Nimmt pro Dokument eine Liste von Seitentexten entgegen (ein String pro Seite),
damit Deltas mit Seiten- und Positionsangabe gemeldet werden können, auch wenn
sich der Seitenumbruch zwischen Referenz- und Kandidat-Dokument verschiebt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Sequence

_HYPHENATION_RE = re.compile(r"-\s*\n\s*")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class Delta:
    page: int
    position: int
    ref_text: str
    cnd_text: str


@dataclass
class CompareResult:
    has_delta: bool
    deltas: List[Delta] = field(default_factory=list)
    ocr_was_used: bool = False


def normalize_text(text: str) -> str:
    """Führt Silbentrennungen am Zeilenende zusammen und normalisiert Whitespace."""
    text = _HYPHENATION_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _words_with_pages(pages: Sequence[str]):
    words: List[str] = []
    word_pages: List[int] = []
    for page_num, page_text in enumerate(pages, start=1):
        for word in normalize_text(page_text).split(" "):
            if not word:
                continue
            words.append(word)
            word_pages.append(page_num)
    return words, word_pages


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


def compare(
    ref_pages: Sequence[str],
    cnd_pages: Sequence[str],
    case_sensitive: bool = True,
    normalize_whitespace: bool = False,
    ocr_used: bool = False,
) -> CompareResult:
    """Vergleicht Referenz- und Kandidat-Text seitenweise, ignoriert dabei
    Seitenumbrüche und Silbentrennung.

    case_sensitive=False ignoriert Groß-/Kleinschreibung beim Vergleich
    (TC-T-006); ref_text/cnd_text in den Deltas behalten die Originalschreibung.

    normalize_whitespace=True verwirft Delta-Kandidaten, die sich nur durch
    Leerzeichen unterscheiden (z.B. OCR-bedingte Wort-Trennfehler) - ein
    Delta, das auch einen echten Textunterschied enthält, bleibt bestehen.

    ocr_used wird unverändert in CompareResult.ocr_was_used übernommen, damit
    Aufrufer (z.B. der Report) sichtbar machen können, ob die Texte über
    OCR statt nativer PDF-Extraktion gewonnen wurden.
    """
    ref_words, _ = _words_with_pages(ref_pages)
    cnd_words, cnd_word_pages = _words_with_pages(cnd_pages)

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
        deltas.append(
            Delta(
                page=page,
                position=j1,
                ref_text=ref_text,
                cnd_text=cnd_text,
            )
        )

    return CompareResult(has_delta=bool(deltas), deltas=deltas, ocr_was_used=ocr_used)
