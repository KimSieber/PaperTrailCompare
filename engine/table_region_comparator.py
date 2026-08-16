# file:    engine/table_region_comparator.py
# purpose: Whitespace-free string comparison for profile.table_regions -
#          ignores ALL whitespace (not just word order), only the character
#          sequence matters. Produces Delta objects compatible with
#          engine.text_comparator.Delta.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Whitespace-freier Vergleich für table_regions.

Vergleicht zwei Texte nach vollständigem Entfernen jeglichen Whitespace -
nicht nur sequenziellen Diff (wie engine.text_comparator._compare_words),
auch nicht mehr Wort-für-Wort per Counter (frühere Fassung). Gedacht für
Seitenbereiche, in denen PyMuPDF für optisch identischen Mehrspalten-Inhalt
je nach Formatierer unterschiedliche Blockgrenzen liefert (Referenz: ein
breiter Block pro Zeile über alle Spalten; Kandidat: ein schmaler Block pro
Spalte) - ein sequenzieller Vergleich sähe dort nur Wortumstellungen und
würde hunderte False-Deltas erzeugen, obwohl der Textinhalt identisch ist
(siehe docs/prompt_table_regions.md, Motivation).

Der Wechsel von Counter-basiertem Wortvergleich auf reinen Whitespace-freien
Stringvergleich (siehe docs/prompt_table_regions_whitespace_free.md) war
nötig, weil echte Type3-Schriften von Großrechner-Drucksystemen (Size=1.0)
über PyMuPDFs Leerzeichen-Heuristik Silbenfragmente mit falschen
Zwischenräumen liefern ("SV Spa r ka ssen V er si ch eru n g" statt "SV
SparkassenVersicherung") - ein Wortvergleich sähe dort völlig andere
"Wörter" ("Spa", "r", "ka", "ssen", ...) als auf der Kandidatenseite
("SparkassenVersicherung") und würde selbst bei identischem Inhalt massive
Deltas erzeugen. Entfernt man dagegen JEGLICHEN Whitespace vor dem
Vergleich, wird "SVSparkassenVersicherung..." auf beiden Seiten identisch,
unabhängig davon, wo genau PyMuPDF (fälschlich oder korrekt) Leerzeichen
eingefügt hat.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from engine.text_comparator import Delta

# Der Vergleich hat keinen sinnvollen Positionsbegriff (anders als der
# sequenzielle Vergleich, wo position der Wort-Index im Kandidatentext ist)
# - Delta.position ist als int typisiert (kein Optional), deshalb hier ein
# fester Sentinel-Wert statt None. Report/Batch lesen position aktuell
# nirgends aus (siehe engine.report_generator - nur page/ref_text/cnd_text
# werden verwendet), ein Sentinel ist also inhaltlich unschädlich - ABER:
# muss ein gültiger, NICHT-NEGATIVER int sein. src-tauri/src/lib.rs bildet
# Delta.position auf ein Rust `u32` ab (serde); ein negativer Sentinel wie
# -1 lässt serde_json::from_value::<BatchProgressEvent> fehlschlagen, was in
# start_batch_compare per `if let Ok(...)` OHNE Fehlermeldung verschluckt
# wird - kein Progress-Event, keine Ergebnisliste in der GUI, obwohl der
# Python-Batch selbst fehlerfrei durchläuft (siehe
# docs/prompt_bugfix_batch_progress.md, Root Cause). 0 ist der einzige
# Sentinel-Wert, der zugleich "kein sinnvoller Wort-Index" ausdrückt UND für
# jede Zahlendarstellung (Python int, Rust u32, JS number) gültig bleibt.
_NO_POSITION = 0


def compare_table_region(
    ref_text_nows: str,
    cnd_text_nows: str,
    ref_text_display: str,
    cnd_text_display: str,
    page_num: int,
    region_index: int,
) -> List[Delta]:
    """Vergleicht zwei Regionstexte nach vollständigem Entfernen jeglichen
    Whitespace - Wortgrenzen (echte wie durch Type3-Fragmentierung
    falsche) spielen dabei keine Rolle mehr.

    ref_text_nows/cnd_text_nows sind bereits whitespace-frei (siehe
    pdf_extractor.separate_table_region_blocks) und werden hier nur noch
    direkt verglichen - ".join(text.split())" wird trotzdem defensiv erneut
    angewendet, falls diese Funktion mit nicht vorbereinigtem Text
    aufgerufen wird (z.B. direkt in Tests).

    Sind die whitespace-freien Versionen identisch, gibt es KEIN Delta -
    das ist die entscheidende Eigenschaft: Wortreihenfolge UND jegliche
    Leerzeichen-Platzierung werden ignoriert, nur die reine Zeichenkette
    zählt. Unterscheiden sie sich, wird EIN Delta für die gesamte Region
    erzeugt (nicht mehr pro Wort wie in der Counter-Fassung) - ref_text/
    cnd_text im Delta sind die lesbaren, Whitespace-normalisierten Versionen
    (ref_text_display/cnd_text_display), damit der Report für Tester ohne
    Kenntnis der Profil-Einstellungen lesbar bleibt (siehe
    docs/prompt_table_regions_whitespace_free.md, Option A).

    Es gibt bewusst KEIN eigenes "type"-Feld auf dem erzeugten Delta-Objekt
    - Delta (engine.text_comparator) hat kein solches Feld, und der Report-
    Renderer liest ohnehin nur page/ref_text/cnd_text (siehe
    report_generator._render_detail_rows).

    region_index identifiziert die table_region (siehe profile.table_regions)
    für Aufrufer/Logging; er fließt NICHT in das Delta-Objekt ein, da dessen
    Schema dafür kein Feld vorsieht.
    """
    ref_nows = "".join(ref_text_nows.split())
    cnd_nows = "".join(cnd_text_nows.split())

    if ref_nows == cnd_nows:
        return []

    return [
        Delta(
            page=page_num,
            position=_NO_POSITION,
            ref_text=ref_text_display,
            cnd_text=cnd_text_display,
        )
    ]


def merge_table_region_comparison(
    ref_tr_texts: Sequence[Dict[int, Tuple[str, str]]],
    cnd_tr_texts: Sequence[Dict[int, Tuple[str, str]]],
) -> List[Delta]:
    """Führt den Whitespace-freien Vergleich über alle Seiten/Regionen
    zusammen - gemeinsam genutzt von engine.__main__ (Einzelvergleich) und
    engine.batch_processor (Batch), die beide dieselbe Logik brauchen, um
    die table_region_texts-Rückgabe von extract_pages_for_profile in
    zusätzliche Deltas zu verwandeln (siehe docs/prompt_table_regions.md,
    Step 4).

    ref_tr_texts/cnd_tr_texts: je ein dict pro Seite (region_index ->
    (whitespace-freier Text, lesbarer Text)), wie von
    extract_pages_for_profile zurückgegeben (siehe
    pdf_extractor.separate_table_region_blocks). Element [0] geht in den
    Vergleich, Element [1] in die Delta-Anzeige.

    Nur region_index-Werte, die auf BEIDEN Seiten für dieselbe Seitenzahl
    vorhanden sind, werden verglichen - eine Region, die nur auf einer
    Seite matchte (z.B. weil die condition dort nicht zutraf), wird
    stillschweigend übersprungen und bleibt Teil des normalen sequenziellen
    Vergleichs (siehe pdf_extractor.separate_table_region_blocks: nur bei
    zutreffender condition werden Blöcke überhaupt abgetrennt).

    Hat ref_tr_texts mehr/weniger Seiten als cnd_tr_texts (unterschiedliche
    Seitenzahl zwischen Referenz und Kandidat), werden nur die gemeinsamen
    Seiten betrachtet (zip stoppt an der kürzeren Liste) - überzählige
    Seiten haben ohnehin schon eigene reguläre Deltas aus dem sequenziellen
    Vergleich (Seitenumbruch-Toleranz ist dessen Aufgabe, nicht diese hier).
    """
    deltas: List[Delta] = []
    for page_index, (ref_regions, cnd_regions) in enumerate(zip(ref_tr_texts, cnd_tr_texts)):
        page_num = page_index + 1
        for region_index, (ref_nows, ref_display) in ref_regions.items():
            if region_index not in cnd_regions:
                continue
            cnd_nows, cnd_display = cnd_regions[region_index]
            deltas.extend(
                compare_table_region(
                    ref_nows, cnd_nows, ref_display, cnd_display, page_num, region_index
                )
            )
    return deltas
