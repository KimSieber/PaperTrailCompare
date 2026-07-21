"""P1-Testfälle TC-P-001 und TC-P-002 für engine.profile_loader.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 6.
Fixtures: tests/fixtures/TC-P-001/profile.json (valide),
          tests/fixtures/TC-P-002/profile_invalid.json (Syntaxfehler).

Zusätzlich (nicht in der Testspezifikation, ergänzt für Coverage-Ziel
≥90 % laut CLAUDE.md): weitere Validierungsfehlerpfade von load_profile(),
die über den reinen JSON-Syntaxfehler aus TC-P-002 hinausgehen.
"""
import json

import pytest

from engine.profile_loader import ValidationError, load_profile

FIXTURES_DIR = __import__("pathlib").Path(__file__).parent / "fixtures"


def test_tc_p_001_valides_json_profil_laden():
    profile = load_profile(FIXTURES_DIR / "TC-P-001" / "profile.json")

    assert profile.version == "1.0"
    assert profile.case_sensitive is False
    assert profile.normalize_whitespace is True
    assert profile.report_format == "pdf"

    assert len(profile.exclude_regions) == 1
    region = profile.exclude_regions[0]
    assert region.page == 1
    assert region.x == 0
    assert region.y == 770
    assert region.width == 200
    assert region.height == 55

    assert len(profile.page_groups) == 1
    group = profile.page_groups[0]
    assert group.pattern == "Rechnung Nr\\..*"
    assert group.name == "Rechnung"

    assert profile.ocr.enabled is False
    assert profile.ocr.confidence_threshold == 0.85


def test_tc_p_002_invalides_json_profil_wirft_validation_error():
    with pytest.raises(ValidationError) as excinfo:
        load_profile(FIXTURES_DIR / "TC-P-002" / "profile_invalid.json")

    assert str(excinfo.value)


def test_load_profile_datei_nicht_gefunden_wirft_validation_error(tmp_path):
    with pytest.raises(ValidationError):
        load_profile(tmp_path / "does_not_exist.json")


def test_load_profile_json_kein_objekt_wirft_validation_error(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_fehlendes_pflichtfeld_version_wirft_validation_error(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"case_sensitive": True}), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_ungueltiges_report_format_wirft_validation_error(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "report_format": "xml"}), encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


@pytest.mark.parametrize(
    "profile_data",
    [
        {"version": "1.0", "exclude_regions": [{"page": 1, "x": 0, "y": 0, "width": 10}]},
        {"version": "1.0", "page_groups": [{"pattern": "Rechnung.*"}]},
    ],
    ids=["exclude_region_ohne_height", "page_group_ohne_name"],
)
def test_load_profile_fehlendes_feld_in_region_oder_gruppe_wirft_validation_error(
    tmp_path, profile_data
):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile_data), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_profile(profile_path)
