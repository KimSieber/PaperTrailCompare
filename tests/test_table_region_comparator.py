# file:    tests/test_table_region_comparator.py
# purpose: Tests for engine.table_region_comparator (Sprint PTC-S3 Task C,
#          siehe docs/prompt_table_regions.md, Step 3, und
#          docs/prompt_table_regions_whitespace_free.md für den Wechsel von
#          Counter-Wortvergleich auf Whitespace-freien Stringvergleich).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Testfälle für engine.table_region_comparator.compare_table_region().

Kein Testfall aus der Testspezifikation - table_regions ist eine neue
Erweiterung (Sprint PTC-S3 Task C), noch nicht Teil der ursprünglichen
Testfall-Matrix.

compare_table_region vergleicht die whitespace-freien Versionen der Texte
(ref_text_nows/cnd_text_nows) - sind sie identisch, gibt es kein Delta,
unabhängig von Wortreihenfolge UND Leerzeichen-Platzierung. Unterscheiden
sie sich, entsteht GENAU EIN Delta für die gesamte Region, dessen
ref_text/cnd_text die lesbaren *_display-Versionen sind (nicht die
whitespace-freien) - für die Report-Lesbarkeit.
"""
from engine.table_region_comparator import compare_table_region


def test_identische_texte_liefern_keine_deltas():
    deltas = compare_table_region(
        "SVSparkassenVersicherungKundenservice", "SVSparkassenVersicherungKundenservice",
        "SV SparkassenVersicherung Kundenservice", "SV SparkassenVersicherung Kundenservice",
        page_num=1, region_index=0,
    )
    assert deltas == []


def test_unterschiedlicher_inhalt_liefert_genau_ein_delta_fuer_die_region():
    deltas = compare_table_region(
        "AlphaBetaGamma", "AlphaGamma",
        "Alpha Beta Gamma", "Alpha Gamma",
        page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == "Alpha Beta Gamma"
    assert deltas[0].cnd_text == "Alpha Gamma"


def test_delta_enthaelt_die_lesbare_anzeige_version_nicht_die_whitespace_freie():
    """Kernanforderung aus docs/prompt_table_regions_whitespace_free.md,
    Option A: der Report muss lesbaren Text zeigen, nicht die whitespace-
    freie Vergleichsversion."""
    deltas = compare_table_region(
        "AlphaBeta", "AlphaGamma",
        "Alpha Beta", "Alpha Gamma",
        page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == "Alpha Beta"  # lesbar, nicht "AlphaBeta"
    assert deltas[0].cnd_text == "Alpha Gamma"


def test_whitespace_platzierung_allein_liefert_keine_deltas():
    """Kernverhalten des Wechsels auf Whitespace-freien Vergleich: zwei
    Texte mit identischer Zeichenkette, aber unterschiedlicher Leerzeichen-
    Platzierung (z.B. Type3-Silbenfragmentierung), sind identisch."""
    deltas = compare_table_region(
        "SVSparkassenVersicherung", "SVSparkassenVersicherung",
        "SV Spa r ka ssen V er si ch eru n g", "SV SparkassenVersicherung",
        page_num=1, region_index=0,
    )
    assert deltas == []


def test_beide_texte_leer_liefert_keine_deltas():
    deltas = compare_table_region("", "", "", "", page_num=1, region_index=0)
    assert deltas == []


def test_leere_referenz_liefert_ein_delta():
    deltas = compare_table_region(
        "", "AlphaBeta", "", "Alpha Beta", page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == ""
    assert deltas[0].cnd_text == "Alpha Beta"


def test_leerer_kandidat_liefert_ein_delta():
    deltas = compare_table_region(
        "AlphaBeta", "", "Alpha Beta", "", page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == "Alpha Beta"
    assert deltas[0].cnd_text == ""


def test_andere_wortreihenfolge_gleiche_woerter_liefert_deltas():
    """Anders als der frühere Counter-basierte Vergleich ignoriert der
    Whitespace-freie Stringvergleich NICHT die Zeichenreihenfolge - eine
    reine Wortumstellung ändert die Zeichenkette und liefert daher ein
    Delta. Das ist beabsichtigt (siehe docs/prompt_table_regions_whitespace_free.md):
    für den eigentlichen Use-Case (identischer Blocktext, nur andere
    Blockgrenzen/Leerzeichen-Platzierung durch denselben Formatierer)
    bleibt die Zeichenreihenfolge gleich - eine echte Wortumstellung wäre
    ein Formatierer-Unterschied, den table_regions nicht verschlucken soll."""
    deltas = compare_table_region(
        "SVSparkassenVersicherungKundenservice",
        "KundenserviceSVSparkassenVersicherung",
        "SV SparkassenVersicherung Kundenservice",
        "Kundenservice SV SparkassenVersicherung",
        page_num=1, region_index=0,
    )
    assert len(deltas) == 1


def test_deltas_haben_korrektes_page_attribut():
    deltas = compare_table_region(
        "Alpha", "Beta", "Alpha", "Beta", page_num=7, region_index=2,
    )
    assert len(deltas) == 1
    assert deltas[0].page == 7
