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


def compare(ref_pages: Sequence[str], cnd_pages: Sequence[str]) -> CompareResult:
    """Vergleicht Referenz- und Kandidat-Text seitenweise, ignoriert dabei
    Seitenumbrüche und Silbentrennung."""
    ref_words, _ = _words_with_pages(ref_pages)
    cnd_words, cnd_word_pages = _words_with_pages(cnd_pages)

    matcher = SequenceMatcher(a=ref_words, b=cnd_words, autojunk=False)
    deltas: List[Delta] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        page = cnd_word_pages[j1] if j1 < len(cnd_word_pages) else (
            cnd_word_pages[-1] if cnd_word_pages else 0
        )
        deltas.append(
            Delta(
                page=page,
                position=j1,
                ref_text=" ".join(ref_words[i1:i2]),
                cnd_text=" ".join(cnd_words[j1:j2]),
            )
        )

    return CompareResult(has_delta=bool(deltas), deltas=deltas)
