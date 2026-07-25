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
_REQUIRED_FIELDS = ("version",)


class ValidationError(Exception):
    """Wird geworfen, wenn ein Profil nicht gelesen oder validiert werden kann."""


@dataclass
class ExcludeRegion:
    page: int
    x: float
    y: float
    width: float
    height: float


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
    page_groups: List[PageGroupPattern] = field(default_factory=list)
    report_format: str = "pdf"
    ocr: OcrConfig = field(default_factory=OcrConfig)
    text_extraction: str = "native"
    compare_mode: str = "words"


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

    report_format = data.get("report_format", "pdf")
    if report_format not in _VALID_REPORT_FORMATS:
        raise ValidationError(
            f"Profil '{path}': report_format muss einer von {_VALID_REPORT_FORMATS} "
            f"sein, ist '{report_format}'"
        )

    try:
        exclude_regions = [
            ExcludeRegion(
                page=region["page"],
                x=region["x"],
                y=region["y"],
                width=region["width"],
                height=region["height"],
            )
            for region in data.get("exclude_regions", [])
        ]
        page_groups = [
            PageGroupPattern(pattern=group["pattern"], name=group["name"])
            for group in data.get("page_groups", [])
        ]
    except KeyError as exc:
        raise ValidationError(
            f"Profil '{path}': fehlendes Feld {exc} in exclude_regions/page_groups"
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

    return Profile(
        version=str(data["version"]),
        case_sensitive=bool(data.get("case_sensitive", True)),
        normalize_whitespace=bool(data.get("normalize_whitespace", False)),
        exclude_regions=exclude_regions,
        page_groups=page_groups,
        report_format=report_format,
        ocr=ocr,
        text_extraction=text_extraction,
        compare_mode=compare_mode,
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
