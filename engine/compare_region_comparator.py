# file:    engine/compare_region_comparator.py
# purpose: Character-multiset comparison for profile.compare_regions - ignores
#          ALL whitespace AND block/word order, only which characters occur
#          (and how often) matters. Produces Delta objects compatible with
#          engine.text_comparator.Delta.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-16

"""Zeichen-Multiset-Vergleich für compare_regions.

Vergleicht zwei Texte anhand ihres Zeichen-Multisets nach vollständigem
Entfernen jeglichen Whitespace - nicht sequenzieller Diff (wie
engine.text_comparator._compare_words), nicht Wort-für-Wort per Counter
(erste Fassung), nicht mehr Whitespace-freier Stringvergleich (zweite
Fassung, siehe docs/prompt_table_regions_whitespace_free.md). Gedacht für
Seitenbereiche, in denen PyMuPDF für optisch identischen Mehrspalten-Inhalt
je nach Formatierer unterschiedliche Blockgrenzen liefert.

Diagnose an echten Referenz-/Kandidat-Dokumenten (siehe
docs/prompt_table_regions_char_multiset.md) hat gezeigt: die Whitespace-
freie Condition-Prüfung funktioniert auf beiden Seiten korrekt, die Blöcke
werden korrekt abgetrennt - das Problem liegt tiefer, in der
Block-KONKATENATIONSREIHENFOLGE. Die Referenz-Seite liefert einen breiten
Block PRO ZEILE (row-major, über alle Spalten hinweg konkateniert), die
Kandidaten-Seite dagegen einen schmalen Block PRO SPALTE (column-major).
Beide Regionstexte enthalten exakt dieselben Zeichen - nur in komplett
anderer Reihenfolge. Ein Stringvergleich (auch Whitespace-frei) kann bei
divergierender Blockreihenfolge NIE Gleichheit feststellen, obwohl der
Inhalt identisch ist.

Design-Historie: der ursprüngliche Wort-Counter-Vergleich scheiterte an
Type3-Silbenfragmentierung von Großrechner-Drucksystemen (unzuverlässige
Wortgrenzen, siehe unten); der anschließende Whitespace-freie
Stringvergleich scheitert an divergierender Blockreihenfolge. Der
Zeichen-Multiset-Vergleich (Counter(ref_nows) == Counter(cnd_nows)) ist
sowohl reihenfolge- als auch Whitespace-unabhängig - genau die Kombination,
die diese Dokumentklasse braucht.

Bekannte Einschränkung (bewusst in Kauf genommen): zwei Texte, die
zueinander Anagramme sind (exakt dieselben Zeichen in beliebiger
Reihenfolge, aber unterschiedliche Bedeutung), würden als gleich bewertet.
Für den Fußzeilen-Use-Case ist das praktisch irrelevant - jede geänderte
Ziffer, jeder geänderte Betrag oder jedes fehlende Wort ändert das
Zeichen-Multiset -, muss aber dokumentiert sein.

Historischer Kontext Type3-Fragmentierung: echte Type3-Schriften von
Großrechner-Drucksystemen (Size=1.0) liefern über PyMuPDFs
Leerzeichen-Heuristik Silbenfragmente mit falschen Zwischenräumen ("SV Spa
r ka ssen V er si ch eru n g" statt "SV SparkassenVersicherung") - ein
Wortvergleich sähe dort völlig andere "Wörter" ("Spa", "r", "ka", "ssen",
...) als auf der Kandidatenseite ("SparkassenVersicherung") und würde
selbst bei identischem Inhalt massive Deltas erzeugen. Entfernt man
dagegen JEGLICHEN Whitespace vor dem Vergleich, wird
"SVSparkassenVersicherung..." auf beiden Seiten identisch, unabhängig
davon, wo genau PyMuPDF (fälschlich oder korrekt) Leerzeichen eingefügt
hat.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from engine.profile_loader import CompareRegion, Profile
from engine.text_comparator import Delta, compare

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


def compare_region(
    ref_text_nows: str,
    cnd_text_nows: str,
    ref_text_display: str,
    cnd_text_display: str,
    page_num: int,
    region_index: int,
    region_clip: Optional[Tuple[float, float, float, float]] = None,
) -> List[Delta]:
    """Vergleicht zwei Regionstexte über ihr Zeichen-Multiset, nach
    vollständigem Entfernen jeglichen Whitespace - Wortgrenzen (echte wie
    durch Type3-Fragmentierung falsche) UND Blockreihenfolge (row-major vs.
    column-major, siehe Modul-Docstring) spielen dabei keine Rolle mehr.

    ref_text_nows/cnd_text_nows sind bereits whitespace-frei (siehe
    pdf_extractor.separate_compare_region_blocks) und werden hier nur noch in
    ihr Zeichen-Multiset überführt - ".join(text.split())" wird trotzdem
    defensiv erneut angewendet, falls diese Funktion mit nicht
    vorbereinigtem Text aufgerufen wird (z.B. direkt in Tests).

    Sind die Zeichen-Multisets der whitespace-freien Versionen identisch,
    gibt es KEIN Delta - das ist die entscheidende Eigenschaft: weder
    Block-/Wortreihenfolge noch jegliche Leerzeichen-Platzierung spielen
    eine Rolle, nur WELCHE Zeichen (und wie oft) vorkommen. Unterscheiden
    sich die Multisets, wird EIN Delta für die gesamte Region erzeugt
    (nicht mehr pro Wort wie in der ursprünglichen Counter-Fassung) -
    ref_text/cnd_text im Delta sind die lesbaren, Whitespace-normalisierten
    Versionen (ref_text_display/cnd_text_display), damit der Report für
    Tester ohne Kenntnis der Profil-Einstellungen lesbar bleibt (siehe
    docs/prompt_table_regions_whitespace_free.md, Option A).

    Bekannte Einschränkung: zueinander anagrammatische Texte (exakt
    dieselben Zeichen in beliebiger Reihenfolge) werden als gleich bewertet
    - siehe Modul-Docstring, Abschnitt "Bekannte Einschränkung".

    Es gibt bewusst KEIN eigenes "type"-Feld auf dem erzeugten Delta-Objekt
    - Delta (engine.text_comparator) hat kein solches Feld, und der Report-
    Renderer liest ohnehin nur page/ref_text/cnd_text (siehe
    report_generator._render_detail_rows).

    region_index identifiziert die compare_region (siehe profile.compare_regions)
    für Aufrufer/Logging; er fließt NICHT in das Delta-Objekt ein, da dessen
    Schema dafür kein Feld vorsieht.

    region_clip (x0, y0, x1, y1) ist die Bounding-Box der Region in PDF-
    Seitenkoordinaten (siehe docs/prompt_region_clip_highlighting.md) - wird
    unverändert auf das erzeugte Delta durchgereicht, damit der
    report_generator die Fundstellensuche für die Highlight-Markierung auf
    genau diese Region einschränken kann (page.search_for(text, clip=...)),
    statt versehentlich gleichlautenden Text an anderen Stellen der Seite
    (Sender-Block, Fußzeile) mitzumarkieren. None (Default) bedeutet "keine
    Einschränkung" - z.B. bei direkten Testaufrufen ohne Profil-Region.
    """
    ref_nows = "".join(ref_text_nows.split())
    cnd_nows = "".join(cnd_text_nows.split())

    if Counter(ref_nows) == Counter(cnd_nows):
        return []

    return [
        Delta(
            page=page_num,
            position=_NO_POSITION,
            ref_text=ref_text_display,
            cnd_text=cnd_text_display,
            region_clip=region_clip,
        )
    ]


@dataclasses.dataclass(frozen=True)
class RegionCompareSettings:
    """Bündelt die Vergleichsparameter für den sequenziellen
    compare_region-Vergleich (mode="sequential") - siehe
    build_region_compare_settings."""

    case_sensitive: bool = True
    normalize_whitespace: bool = False
    compare_mode: str = "words"
    merge_hyphenation: bool = True
    normalize_orphan_hyphens: bool = True


def build_region_compare_settings(profile: Optional[Profile]) -> RegionCompareSettings:
    """EINE zentrale Stelle, die die Vergleichsparameter für den
    sequenziellen compare_region-Vergleich bündelt (siehe
    docs/prompt_compare_regions_mode.md, Task 2) - dieselben Parameter, mit
    denen auch der normale Seitenvergleich läuft (case_sensitive,
    compare_mode, normalize_whitespace, merge_hyphenation,
    normalize_orphan_hyphens), damit z.B. ein case_sensitive=False- oder
    compare_mode="hybrid"-Profil konsistent auch innerhalb isolierter
    Regionen gilt.

    WICHTIG für spätere Erweiterbarkeit: künftige Region-spezifische
    Overrides (ein Profil, das für EINE Region z.B. einen anderen
    compare_mode erzwingt) docken hier an - an genau dieser einen Stelle,
    ohne dass merge_compare_region_comparison oder deren Aufrufer
    umgebaut werden müssten. Aktuell NICHT implementiert (siehe
    docs/prompt_compare_regions_mode.md, Task 2: "Do NOT implement
    per-region overrides now").

    profile=None (kein Profil übergeben) liefert dieselben Defaults wie
    Profile() selbst - siehe engine.__main__._run_compare/
    engine.batch_processor, die compare() für den Hauptvergleich ebenso
    mit "if profile else <Default>" aufrufen."""
    if profile is None:
        return RegionCompareSettings()
    return RegionCompareSettings(
        case_sensitive=profile.case_sensitive,
        normalize_whitespace=profile.normalize_whitespace,
        compare_mode=profile.compare_mode,
        merge_hyphenation=profile.merge_hyphenation,
        normalize_orphan_hyphens=profile.normalize_orphan_hyphens,
    )


def _compare_region_sequential(
    ref_display: str,
    cnd_display: str,
    page_num: int,
    settings: RegionCompareSettings,
    region_clip: Optional[Tuple[float, float, float, float]] = None,
) -> List[Delta]:
    """mode="sequential" (siehe docs/prompt_compare_regions_mode.md, Task 2):
    vergleicht den Regionstext mit dem NORMALEN sequenziellen Vergleich
    (engine.text_comparator.compare), isoliert vom Rest der Seite - liefert
    also mehrere kleine Deltas statt eines einzigen Deltas für den gesamten
    Blocktext (das bleibt mode="unordered" vorbehalten, siehe
    compare_region oben).

    compare() arbeitet seitenweise und vergibt page=1 an das (einzige)
    Element der übergebenen ref_pages/cnd_pages-Liste - das wird hier auf
    die tatsächliche Seitenzahl der Region zurückgemappt (Anforderung 4 aus
    docs/prompt_compare_regions_mode.md, Task 2).

    region_clip (siehe compare_region oben, docs/prompt_region_clip_highlighting.md)
    wird auf JEDES remappte Delta gesetzt - compare() kennt die Region nicht
    und liefert Deltas ohne region_clip; das muss hier nachgetragen werden."""
    result = compare(
        [ref_display], [cnd_display],
        case_sensitive=settings.case_sensitive,
        normalize_whitespace=settings.normalize_whitespace,
        compare_mode=settings.compare_mode,
        merge_hyphenation=settings.merge_hyphenation,
        normalize_orphan_hyphens=settings.normalize_orphan_hyphens,
    )
    return [
        dataclasses.replace(delta, page=page_num, region_clip=region_clip)
        for delta in result.deltas
    ]


def merge_compare_region_comparison(
    ref_tr_texts: Sequence[Dict[int, Tuple[str, str]]],
    cnd_tr_texts: Sequence[Dict[int, Tuple[str, str]]],
    profile: Optional[Profile] = None,
) -> List[Delta]:
    """Führt den compare_region-Vergleich über alle Seiten/Regionen zusammen
    - gemeinsam genutzt von engine.__main__ (Einzelvergleich) und
    engine.batch_processor (Batch), die beide dieselbe Logik brauchen, um
    die compare_region_texts-Rückgabe von extract_pages_for_profile in
    zusätzliche Deltas zu verwandeln (siehe docs/prompt_table_regions.md,
    Step 4).

    Pro Region wird anhand ihres profile.compare_regions[region_index].mode
    entschieden, WIE verglichen wird (siehe
    docs/prompt_compare_regions_mode.md, Task 2):
    - "sequential" (Default): _compare_region_sequential (mehrere kleine,
      präzise Deltas).
    - "unordered": compare_region (Zeichen-Multiset, EIN Delta für die
      gesamte Region).
    profile=None (kein Profil übergeben, z.B. wenn compare_region_texts aus
    anderen Gründen leer sind) fällt für alle Regionen auf "unordered"
    zurück, ist aber praktisch unerreichbar - ohne Profil gibt es auch keine
    compare_regions und damit keine Einträge in ref_tr_texts/cnd_tr_texts.

    ref_tr_texts/cnd_tr_texts: je ein dict pro Seite (region_index ->
    (whitespace-freier Text, lesbarer Text)), wie von
    extract_pages_for_profile zurückgegeben (siehe
    pdf_extractor.separate_compare_region_blocks). Element [0] geht in den
    Multiset-Vergleich (mode="unordered"), Element [1] sowohl in die
    Delta-Anzeige als auch in den sequenziellen Vergleich (mode="sequential"
    braucht keinen whitespace-freien Text, nur die lesbare Version).

    Nur region_index-Werte, die auf BEIDEN Seiten für dieselbe Seitenzahl
    vorhanden sind, werden verglichen - eine Region, die nur auf einer
    Seite matchte (z.B. weil die condition dort nicht zutraf), wird
    stillschweigend übersprungen und bleibt Teil des normalen sequenziellen
    Vergleichs (siehe pdf_extractor.separate_compare_region_blocks: nur bei
    zutreffender condition werden Blöcke überhaupt abgetrennt - siehe dort
    den TODO-Kommentar zum bekannten Risiko eines einseitigen
    condition-Matches, docs/prompt_compare_regions_mode.md, Task 2).

    Hat ref_tr_texts mehr/weniger Seiten als cnd_tr_texts (unterschiedliche
    Seitenzahl zwischen Referenz und Kandidat), werden nur die gemeinsamen
    Seiten betrachtet (zip stoppt an der kürzeren Liste) - überzählige
    Seiten haben ohnehin schon eigene reguläre Deltas aus dem sequenziellen
    Vergleich (Seitenumbruch-Toleranz ist dessen Aufgabe, nicht diese hier).

    Jedes erzeugte Delta bekommt zusätzlich region_clip = (region.x,
    region.y, region.x + region.width, region.y + region.height) aus der
    zugehörigen profile.compare_regions[region_index] gesetzt (siehe
    docs/prompt_region_clip_highlighting.md) - der report_generator nutzt
    das, um die Fundstellensuche für die Highlight-Markierung auf die
    Region einzuschränken, statt gleichlautenden Text an anderen
    Seitenstellen (z.B. eine zweite Telefonnummer in der Fußzeile)
    fälschlich mitzumarkieren.
    """
    compare_regions: Sequence[CompareRegion] = profile.compare_regions if profile is not None else ()
    settings = build_region_compare_settings(profile)

    deltas: List[Delta] = []
    for page_index, (ref_regions, cnd_regions) in enumerate(zip(ref_tr_texts, cnd_tr_texts)):
        page_num = page_index + 1
        for region_index, (ref_nows, ref_display) in ref_regions.items():
            if region_index not in cnd_regions:
                continue
            cnd_nows, cnd_display = cnd_regions[region_index]
            region = compare_regions[region_index] if region_index < len(compare_regions) else None
            mode = region.mode if region is not None else "unordered"
            region_clip = (
                (region.x, region.y, region.x + region.width, region.y + region.height)
                if region is not None
                else None
            )
            if mode == "sequential":
                deltas.extend(
                    _compare_region_sequential(
                        ref_display, cnd_display, page_num, settings, region_clip=region_clip
                    )
                )
            else:
                deltas.extend(
                    compare_region(
                        ref_nows, cnd_nows, ref_display, cnd_display, page_num, region_index,
                        region_clip=region_clip,
                    )
                )
    return deltas
