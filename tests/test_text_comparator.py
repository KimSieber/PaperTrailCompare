"""Testfälle TC-T-001 bis TC-T-006 für engine.text_comparator.

TC-T-007 (Mehrspaltigkeit) und TC-T-008 (Tabellenerkennung) betreffen die
PDF-Extraktion (siehe CLAUDE.md Modulübersicht: pdf_extractor) und werden
dort implementiert, nicht in text_comparator.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 2.
"""
from engine.text_comparator import compare


def test_tc_t_001_identische_texte_kein_delta():
    ref_pages = ["Dies ist ein identischer Text."]
    cnd_pages = ["Dies ist ein identischer Text."]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_t_002_silbentrennung_am_zeilenende_normalisieren():
    ref_pages = ["Das ist eine Silben-\ntrennung im Text."]
    cnd_pages = ["Das ist eine Silbentrennung im Text."]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_t_003_unterschiedlicher_seitenumbruch_gleicher_text():
    ref_pages = ["Gleicher Absatz auf Seite eins."]
    cnd_pages = ["", "Gleicher Absatz auf Seite eins."]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_t_004_echter_textunterschied_ergibt_delta():
    ref_pages = ["Betrag: 100 EUR"]
    cnd_pages = ["Betrag: 200 EUR"]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert len(result.deltas) == 1
    delta = result.deltas[0]
    assert delta.page == 1
    assert delta.position is not None
    assert "100" in delta.ref_text
    assert "200" in delta.cnd_text


def test_tc_t_005_leerzeichennormalisierung():
    ref_pages = ["Dies  ist   ein Text  mit doppelten Leerzeichen."]
    cnd_pages = ["Dies ist ein Text mit doppelten Leerzeichen."]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_t_006_case_sensitivity_ignoriert_bei_case_insensitive():
    ref_pages = ["MUSTER"]
    cnd_pages = ["muster"]

    result = compare(ref_pages, cnd_pages, case_sensitive=False)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_t_006_case_sensitivity_delta_bei_case_sensitive():
    ref_pages = ["MUSTER"]
    cnd_pages = ["muster"]

    result = compare(ref_pages, cnd_pages, case_sensitive=True)

    assert result.has_delta is True
    assert len(result.deltas) == 1
