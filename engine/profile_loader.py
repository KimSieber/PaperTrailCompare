"""Lädt und validiert JSON-Vergleichsprofile zu typsicheren Konfigurationsobjekten.

Bildet mindestens die laut Projektbeschreibung geforderten Konfigurations-
möglichkeiten ab: Ausschluss-Regionen, Seitengruppen-Patterns,
case_sensitive-Flag und Report-Format.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union

_VALID_REPORT_FORMATS = ("pdf", "html")
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
    enabled: bool = False
    confidence_threshold: float = 0.85


@dataclass
class Profile:
    version: str
    case_sensitive: bool = True
    normalize_whitespace: bool = True
    exclude_regions: List[ExcludeRegion] = field(default_factory=list)
    page_groups: List[PageGroupPattern] = field(default_factory=list)
    report_format: str = "pdf"
    ocr: OcrConfig = field(default_factory=OcrConfig)


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
    ocr = OcrConfig(
        enabled=bool(ocr_data.get("enabled", False)),
        confidence_threshold=float(ocr_data.get("confidence_threshold", 0.85)),
    )

    return Profile(
        version=str(data["version"]),
        case_sensitive=bool(data.get("case_sensitive", True)),
        normalize_whitespace=bool(data.get("normalize_whitespace", True)),
        exclude_regions=exclude_regions,
        page_groups=page_groups,
        report_format=report_format,
        ocr=ocr,
    )
