# file:    engine/profile_loader.py
# purpose: Loads and validates JSON comparison profiles into type-safe
#          configuration objects (Profile, ExcludeRegion, OcrConfig,
#          PageGroupPattern). Raises ValidationError on invalid input.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09
# 
"""Lädt und validiert JSON-Vergleichsprofile zu typsicheren Konfigurationsobjekten.

Bildet mindestens die laut Projektbeschreibung geforderten Konfigurations-
möglichkeiten ab: Ausschluss-Regionen, Seitengruppen-Patterns,
case_sensitive-Flag und Report-Format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional, Union

_VALID_REPORT_FORMATS = ("pdf", "html")
_VALID_TEXT_EXTRACTION_MODES = ("native", "reconstruct")
_VALID_OCR_MODES = ("off", "fallback", "force")
_VALID_COMPARE_MODES = ("words", "chars", "hybrid")
_VALID_COMPARE_REGION_MODES = ("sequential", "unordered")
_REQUIRED_FIELDS = ("version",)


class ValidationError(Exception):
    """Wird geworfen, wenn ein Profil nicht gelesen oder validiert werden kann."""


@dataclass
class ExcludeRegion:
    """page und page_from sind beide optional; genau eines von beiden muss
    gesetzt sein - das wird in load_profile geprüft, nicht hier, damit
    direkt konstruierte ExcludeRegion(...)-Aufrufe (Tests) ohne zusätzliche
    Validierung bleiben. page=0 bedeutet "alle Seiten", page_from=N bedeutet
    "ab Seite N bis Dokumentende" (siehe pdf_extractor._region_applies_to_page)."""

    x: float
    y: float
    width: float
    height: float
    page: Optional[int] = None
    page_from: Optional[int] = None


@dataclass
class CompareRegion:
    """Wie ExcludeRegion (page/page_from-Semantik identisch, siehe dort),
    aber die Blöcke innerhalb der Region werden nicht ausgeschlossen,
    sondern isoliert vom Rest der Seite verglichen (siehe
    engine.compare_region_comparator) - das eliminiert False-Deltas durch
    Interleaving mit umliegendem Text bzw. durch abweichende
    Block-/Spaltenstrukturen bei sonst identischem Textinhalt (z.B.
    Mehrspalten-Fußzeilen, siehe docs/prompt_table_regions.md). condition
    ist ein case-sensitiver Teilstring-Match auf den (Whitespace-
    normalisierten) Blocktext der Region - nur wenn er zutrifft, werden die
    Blöcke überhaupt abgetrennt; sonst bleiben sie unverändert im normalen
    sequenziellen Vergleich (siehe separate_compare_region_blocks).
    condition muss mindestens 2 Wörter enthalten - ein einzelnes Wort
    matcht zu unspezifisch (praktisch jeder Fußzeilenblock enthielte es).

    mode bestimmt, WIE die abgetrennten Blöcke verglichen werden (siehe
    docs/prompt_compare_regions_mode.md, Task 2):
    - "sequential" (Default): normaler sequenzieller Vergleich
      (engine.text_comparator.compare), isoliert vom Rest der Seite - für
      Regionen, deren Blockreihenfolge auf beiden Seiten konsistent ist und
      die nur wegen Interleaving mit Nachbartext eine eigene Region
      brauchen (z.B. Absenderinfo-Block neben dem Adressfenster). Liefert
      kleine, präzise Deltas statt eines Deltas für den gesamten Block.
    - "unordered": Zeichen-Multiset-Vergleich (Counter), reihenfolge- und
      whitespace-unabhängig - für Regionen, deren Formatierer die Blöcke in
      unterschiedlicher Reihenfolge liefern (row-major vs. column-major,
      siehe docs/prompt_table_regions_char_multiset.md). Liefert EIN Delta
      für die gesamte Region bei Abweichung."""

    x: float
    y: float
    width: float
    height: float
    condition: str
    page: Optional[int] = None
    page_from: Optional[int] = None
    mode: str = "sequential"


@dataclass
class PageGroupPattern:
    pattern: str
    name: str


@dataclass
class OcrConfig:
    """mode_reference/mode_candidate erlauben getrennte Einstellungen für
    Referenz- und Kandidat-Datei (z.B. Referenz per OCR erzwingen, weil ihre
    Type3-Schrift kaputte Wortgrenzen liefert, während der Kandidat sauberen
    nativen Text hat und nicht durch OCR verschlechtert werden soll).

    None bedeutet "im Profil nicht explizit gesetzt" – dann gilt zur
    Laufzeit (siehe pdf_extractor._effective_ocr_mode) das alte Verhalten
    über 'enabled': True -> "fallback", False -> "off". Das hält bestehende
    Profile und direkt konstruierte OcrConfig(enabled=...)-Aufrufe (Tests)
    unverändert kompatibel; wer die neuen Felder setzt, überschreibt gezielt
    eine Seite."""

    enabled: bool = False
    confidence_threshold: float = 0.85
    mode_reference: Optional[str] = None
    mode_candidate: Optional[str] = None
    dpi: int = 200


@dataclass
class Profile:
    """compare_mode ist eine kundenseitige Einstellung, kein internes Flag:
    "words" (Default) vergleicht auf Wort-Tokens - das passt für Dokumente
    mit intakten Wortgrenzen. "chars" ignoriert beim Vergleich jeglichen
    Whitespace vollständig und vergleicht zeichenweise; das lohnt sich nur
    für Dokumente, deren Wortgrenzen bei der Extraktion unzuverlässig sind
    (z.B. Type3-Schriften alter Großrechner-Drucksysteme ohne ToUnicode-
    Tabelle, siehe Diagnose-Session zu PDF EBR.PY.*) - kann aber auf
    Dokumenten mit vielen bereits strukturell abweichenden Textstellen zu
    einer Explosion kleiner, verstreuter Deltas führen (gemessen: 388 im
    Wortmodus -> 1024 im Zeichenmodus auf denselben Dateien). "hybrid"
    behebt das: Wort-Matcher zur groben Ausrichtung, Zeichenvergleich nur
    innerhalb der so gefundenen Bereiche (siehe
    text_comparator._compare_hybrid) - für dieselbe Dokumentklasse i.d.R.
    die bessere Wahl als "chars". Andere Kunden mit anderen Dokumenttypen
    haben in aller Regel intakte Wortgrenzen - dort würden "chars"/"hybrid"
    nur unnötig Rechenzeit kosten und Änderungen feiner aufsplitten als
    nötig. Deshalb bewusst kein globaler Default, sondern ein expliziter
    Opt-in pro Vergleichsprofil."""

    version: str
    case_sensitive: bool = True
    normalize_whitespace: bool = False
    exclude_regions: List[ExcludeRegion] = field(default_factory=list)
    compare_regions: List[CompareRegion] = field(default_factory=list)
    page_groups: List[PageGroupPattern] = field(default_factory=list)
    report_format: str = "pdf"
    ocr: OcrConfig = field(default_factory=OcrConfig)
    text_extraction: str = "native"
    compare_mode: str = "words"
    merge_hyphenation: bool = True
    normalize_orphan_hyphens: bool = True


def load_profile(path: Union[str, Path]) -> Profile:
    """Lädt ein JSON-Vergleichsprofil und liefert ein validiertes Profile-Objekt.

    Wirft ValidationError mit sprechendem Fehlertext bei Syntaxfehlern oder
    fehlenden/ungültigen Pflichtfeldern (TC-P-002).
    """
    path = Path(path)

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"Profil konnte nicht gelesen werden: {path}: {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Ungültiges JSON in Profil '{path}': {exc.msg} "
            f"(Zeile {exc.lineno}, Spalte {exc.colno})"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError(
            f"Profil '{path}' muss ein JSON-Objekt sein, ist aber {type(data).__name__}"
        )

    for required_field in _REQUIRED_FIELDS:
        if required_field not in data:
            raise ValidationError(f"Profil '{path}': Pflichtfeld '{required_field}' fehlt")

    if "table_regions" in data:
        # Kein Alt-Schlüssel-Support (siehe docs/prompt_compare_regions_mode.md,
        # Task 1): "table_regions" wurde in "compare_regions" umbenannt, weil es
        # nicht mehr nur um Tabellen geht, sondern allgemein um isoliert zu
        # vergleichende Seitenbereiche. Ein stillschweigendes Ignorieren des
        # alten Schlüssels würde die Region unbemerkt verschwinden lassen
        # (leere compare_regions-Liste) - deshalb hier ein expliziter,
        # sprechender Fehler statt Rückwärtskompatibilität.
        raise ValidationError(
            f"Profil '{path}': Schlüssel 'table_regions' ist veraltet und wird "
            f"nicht mehr unterstützt - bitte 'compare_regions' verwenden"
        )

    report_format = data.get("report_format", "pdf")
    if report_format not in _VALID_REPORT_FORMATS:
        raise ValidationError(
            f"Profil '{path}': report_format muss einer von {_VALID_REPORT_FORMATS} "
            f"sein, ist '{report_format}'"
        )

    try:
        exclude_regions = []
        for region in data.get("exclude_regions", []):
            page = region.get("page")
            page_from = region.get("page_from")
            if page is not None and page_from is not None:
                raise ValidationError(
                    f"Profil '{path}': exclude_regions-Eintrag darf nicht gleichzeitig "
                    f"'page' und 'page_from' setzen"
                )
            if page is None and page_from is None:
                raise ValidationError(
                    f"Profil '{path}': exclude_regions-Eintrag benötigt entweder "
                    f"'page' (0 = alle Seiten) oder 'page_from'"
                )
            if page is not None and page < 0:
                raise ValidationError(
                    f"Profil '{path}': exclude_regions.page darf nicht negativ sein, "
                    f"ist {page}"
                )
            if page_from is not None and page_from < 1:
                raise ValidationError(
                    f"Profil '{path}': exclude_regions.page_from muss >= 1 sein, "
                    f"ist {page_from}"
                )
            exclude_regions.append(
                ExcludeRegion(
                    page=page,
                    page_from=page_from,
                    x=region["x"],
                    y=region["y"],
                    width=region["width"],
                    height=region["height"],
                )
            )
        compare_regions = []
        for region in data.get("compare_regions", []):
            page = region.get("page")
            page_from = region.get("page_from")
            if page is not None and page_from is not None:
                raise ValidationError(
                    f"Profil '{path}': compare_regions-Eintrag darf nicht gleichzeitig "
                    f"'page' und 'page_from' setzen"
                )
            if page is None and page_from is None:
                raise ValidationError(
                    f"Profil '{path}': compare_regions-Eintrag benötigt entweder "
                    f"'page' (0 = alle Seiten) oder 'page_from'"
                )
            if page is not None and page < 0:
                raise ValidationError(
                    f"Profil '{path}': compare_regions.page darf nicht negativ sein, "
                    f"ist {page}"
                )
            if page_from is not None and page_from < 1:
                raise ValidationError(
                    f"Profil '{path}': compare_regions.page_from muss >= 1 sein, "
                    f"ist {page_from}"
                )
            width = region["width"]
            height = region["height"]
            if region["x"] < 0 or region["y"] < 0:
                raise ValidationError(
                    f"Profil '{path}': compare_regions.x/y dürfen nicht negativ sein"
                )
            if width <= 0 or height <= 0:
                raise ValidationError(
                    f"Profil '{path}': compare_regions.width/height müssen positiv sein"
                )
            condition = region["condition"]
            if not isinstance(condition, str) or not condition.strip():
                raise ValidationError(
                    f"Profil '{path}': compare_regions.condition darf nicht leer sein"
                )
            if len(condition.split()) < 2:
                raise ValidationError(
                    f"Profil '{path}': compare_regions.condition muss mindestens 2 "
                    f"Wörter enthalten (zu unspezifisch sonst), ist '{condition}'"
                )
            region_mode = region.get("mode", "sequential")
            if region_mode not in _VALID_COMPARE_REGION_MODES:
                raise ValidationError(
                    f"Profil '{path}': compare_regions.mode muss einer von "
                    f"{_VALID_COMPARE_REGION_MODES} sein, ist '{region_mode}'"
                )
            compare_regions.append(
                CompareRegion(
                    page=page,
                    page_from=page_from,
                    x=region["x"],
                    y=region["y"],
                    width=width,
                    height=height,
                    condition=condition,
                    mode=region_mode,
                )
            )
        page_groups = [
            PageGroupPattern(pattern=group["pattern"], name=group["name"])
            for group in data.get("page_groups", [])
        ]
    except KeyError as exc:
        raise ValidationError(
            f"Profil '{path}': fehlendes Feld {exc} in exclude_regions/compare_regions/page_groups"
        ) from exc

    ocr_data = data.get("ocr", {})
    mode_reference = ocr_data.get("mode_reference")
    mode_candidate = ocr_data.get("mode_candidate")
    for field_name, mode_value in (("mode_reference", mode_reference), ("mode_candidate", mode_candidate)):
        if mode_value is not None and mode_value not in _VALID_OCR_MODES:
            raise ValidationError(
                f"Profil '{path}': ocr.{field_name} muss einer von {_VALID_OCR_MODES} "
                f"sein, ist '{mode_value}'"
            )

    dpi = int(ocr_data.get("dpi", 200))
    if dpi <= 0:
        raise ValidationError(f"Profil '{path}': ocr.dpi muss positiv sein, ist {dpi}")

    ocr = OcrConfig(
        enabled=bool(ocr_data.get("enabled", False)),
        confidence_threshold=float(ocr_data.get("confidence_threshold", 0.85)),
        mode_reference=mode_reference,
        mode_candidate=mode_candidate,
        dpi=dpi,
    )

    text_extraction = data.get("text_extraction", "native")
    if text_extraction not in _VALID_TEXT_EXTRACTION_MODES:
        raise ValidationError(
            f"Profil '{path}': text_extraction muss einer von {_VALID_TEXT_EXTRACTION_MODES} "
            f"sein, ist '{text_extraction}'"
        )

    compare_mode = data.get("compare_mode", "words")
    if compare_mode not in _VALID_COMPARE_MODES:
        raise ValidationError(
            f"Profil '{path}': compare_mode muss einer von {_VALID_COMPARE_MODES} "
            f"sein, ist '{compare_mode}'"
        )

    merge_hyphenation = bool(data.get("merge_hyphenation", True))
    normalize_orphan_hyphens = bool(data.get("normalize_orphan_hyphens", True))

    return Profile(
        version=str(data["version"]),
        case_sensitive=bool(data.get("case_sensitive", True)),
        normalize_whitespace=bool(data.get("normalize_whitespace", False)),
        exclude_regions=exclude_regions,
        compare_regions=compare_regions,
        page_groups=page_groups,
        report_format=report_format,
        ocr=ocr,
        text_extraction=text_extraction,
        compare_mode=compare_mode,
        merge_hyphenation=merge_hyphenation,
        normalize_orphan_hyphens=normalize_orphan_hyphens,
    )


def apply_overrides(profile: Profile, **overrides) -> Profile:
    """Überschreibt einzelne Profilwerte, z.B. durch CLI-Parameter (TC-P-003).

    Nur explizit übergebene, nicht-None Werte überschreiben das Profil;
    das übergebene Profile-Objekt selbst bleibt unverändert (dataclasses
    sind hier nicht frozen, aber apply_overrides gibt bewusst eine neue
    Instanz zurück statt in-place zu mutieren).
    """
    active_overrides = {k: v for k, v in overrides.items() if v is not None}
    return replace(profile, **active_overrides)
