# file:    tests/test_profile_loader.py
# purpose: Tests TC-P-001 to TC-P-003 for engine.profile_loader. Covers
#          valid profile loading, validation error paths, CLI overrides,
#          OCR mode settings, and compare_mode handling.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

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

from engine.profile_loader import ValidationError, apply_overrides, load_profile

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


def test_tc_p_003_cli_parameter_ueberschreibt_profilwert(tmp_path):
    """TC-P-003: Profil mit case_sensitive=True; CLI übergibt
    case_sensitive=False -> der CLI-Wert gewinnt, das Profil bleibt unverändert."""
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "case_sensitive": True}), encoding="utf-8"
    )
    profile = load_profile(profile_path)
    assert profile.case_sensitive is True

    overridden = apply_overrides(profile, case_sensitive=False)

    assert overridden.case_sensitive is False
    assert profile.case_sensitive is True  # Original bleibt unangetastet


def test_apply_overrides_none_werte_lassen_profil_unveraendert(tmp_path):
    """Nicht übergebene (None) CLI-Parameter dürfen das Profil nicht überschreiben."""
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "case_sensitive": True, "report_format": "pdf"}),
        encoding="utf-8",
    )
    profile = load_profile(profile_path)

    overridden = apply_overrides(profile, case_sensitive=None, report_format=None)

    assert overridden.case_sensitive is True
    assert overridden.report_format == "pdf"


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


def test_load_profile_text_extraction_default_ist_native(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")

    profile = load_profile(profile_path)

    assert profile.text_extraction == "native"


def test_load_profile_ungueltiger_text_extraction_wert_wirft_validation_error(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "text_extraction": "auto"}), encoding="utf-8"
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


def test_load_profile_ocr_defaults_ohne_ocr_feld(tmp_path):
    """Ohne ocr-Feld im Profil bleiben mode_reference/mode_candidate None
    (nicht explizit gesetzt) und dpi hat den per Messung ermittelten
    Default 200."""
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")

    profile = load_profile(profile_path)

    assert profile.ocr.mode_reference is None
    assert profile.ocr.mode_candidate is None
    assert profile.ocr.dpi == 200


def test_load_profile_ocr_mode_reference_und_candidate_getrennt_einstellbar(tmp_path):
    """Kernanforderung: Referenz per OCR erzwingen, Kandidat nativ lassen."""
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "ocr": {"mode_reference": "force", "mode_candidate": "off", "dpi": 250},
            }
        ),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert profile.ocr.mode_reference == "force"
    assert profile.ocr.mode_candidate == "off"
    assert profile.ocr.dpi == 250


@pytest.mark.parametrize(
    "ocr_data",
    [
        {"mode_reference": "auto"},
        {"mode_candidate": "always"},
    ],
    ids=["ungueltiger_mode_reference", "ungueltiger_mode_candidate"],
)
def test_load_profile_ungueltiger_ocr_modus_wirft_validation_error(tmp_path, ocr_data):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "ocr": ocr_data}), encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_ocr_dpi_nicht_positiv_wirft_validation_error(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "ocr": {"dpi": 0}}), encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_compare_mode_default_ist_words(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")

    profile = load_profile(profile_path)

    assert profile.compare_mode == "words"


def test_load_profile_compare_mode_chars_wird_uebernommen(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "compare_mode": "chars"}), encoding="utf-8"
    )

    profile = load_profile(profile_path)

    assert profile.compare_mode == "chars"


def test_load_profile_ungueltiger_compare_mode_wirft_validation_error(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "compare_mode": "sentences"}), encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_compare_mode_hybrid_wird_uebernommen(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "compare_mode": "hybrid"}), encoding="utf-8"
    )

    profile = load_profile(profile_path)

    assert profile.compare_mode == "hybrid"


def test_load_profile_exclude_region_page_zero_all_pages(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"page": 0, "x": 0, "y": 0, "width": 100, "height": 50}],
        }),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert len(profile.exclude_regions) == 1
    region = profile.exclude_regions[0]
    assert region.page == 0
    assert region.page_from is None


def test_load_profile_exclude_region_page_from(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"page_from": 2, "x": 0, "y": 0, "width": 100, "height": 50}],
        }),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert len(profile.exclude_regions) == 1
    region = profile.exclude_regions[0]
    assert region.page is None
    assert region.page_from == 2


def test_load_profile_exclude_region_page_and_page_from_both_set_raises(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [
                {"page": 1, "page_from": 2, "x": 0, "y": 0, "width": 100, "height": 50}
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_exclude_region_neither_page_nor_page_from_raises(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"x": 0, "y": 0, "width": 100, "height": 50}],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_exclude_region_page_negative_raises(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"page": -1, "x": 0, "y": 0, "width": 100, "height": 50}],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_exclude_region_page_from_zero_raises(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"page_from": 0, "x": 0, "y": 0, "width": 100, "height": 50}],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_exclude_region_page_from_negative_raises(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"page_from": -1, "x": 0, "y": 0, "width": 100, "height": 50}],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_profile(profile_path)


def test_load_profile_combined_regions_mixed_page_types(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [
                {"page": 1, "x": 0, "y": 0, "width": 100, "height": 50},
                {"page": 0, "x": 10, "y": 10, "width": 20, "height": 20},
                {"page_from": 3, "x": 5, "y": 5, "width": 30, "height": 30},
            ],
        }),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert len(profile.exclude_regions) == 3
    region_1, region_all, region_from = profile.exclude_regions
    assert region_1.page == 1 and region_1.page_from is None
    assert region_all.page == 0 and region_all.page_from is None
    assert region_from.page is None and region_from.page_from == 3


def test_merge_hyphenation_default_true(tmp_path):
    """merge_hyphenation defaults to True when not in JSON."""
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0"}')
    profile = load_profile(path)
    assert profile.merge_hyphenation is True


def test_merge_hyphenation_false_from_json(tmp_path):
    """merge_hyphenation=false is loaded correctly."""
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0", "merge_hyphenation": false}')
    profile = load_profile(path)
    assert profile.merge_hyphenation is False


def test_normalize_orphan_hyphens_default_true(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0"}')
    profile = load_profile(path)
    assert profile.normalize_orphan_hyphens is True


def test_normalize_orphan_hyphens_false_from_json(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"version": "1.0", "normalize_orphan_hyphens": false}')
    profile = load_profile(path)
    assert profile.normalize_orphan_hyphens is False
