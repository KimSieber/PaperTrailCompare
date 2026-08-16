# file:    tests/test_compare_region_comparator.py
# purpose: Tests for engine.compare_region_comparator (Sprint PTC-S3 Task C,
#          siehe docs/prompt_table_regions.md, Step 3,
#          docs/prompt_table_regions_whitespace_free.md für den Wechsel von
#          Counter-Wortvergleich auf Whitespace-freien Stringvergleich, und
#          docs/prompt_table_regions_char_multiset.md für den Wechsel von
#          Whitespace-freiem Stringvergleich auf Zeichen-Multiset-Vergleich).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-16

"""Testfälle für engine.compare_region_comparator.compare_region().

Kein Testfall aus der Testspezifikation - compare_regions ist eine neue
Erweiterung (Sprint PTC-S3 Task C), noch nicht Teil der ursprünglichen
Testfall-Matrix.

compare_region vergleicht die Zeichen-Multisets der whitespace-freien
Texte (Counter(ref_text_nows) == Counter(cnd_text_nows)) - sind sie
identisch, gibt es kein Delta, unabhängig von Zeichen-/Block-/
Wortreihenfolge UND Leerzeichen-Platzierung (siehe
docs/prompt_table_regions_char_multiset.md: reale Referenz-/Kandidat-
Dokumente liefern denselben Fußzeilentext in row-major- bzw. column-major-
Blockreihenfolge). Unterscheiden sich die Multisets, entsteht GENAU EIN
Delta für die gesamte Region, dessen ref_text/cnd_text die lesbaren
*_display-Versionen sind (nicht die whitespace-freien) - für die
Report-Lesbarkeit.
"""
from engine.compare_region_comparator import compare_region, merge_compare_region_comparison
from engine.profile_loader import CompareRegion, Profile


def test_identische_texte_liefern_keine_deltas():
    deltas = compare_region(
        "SVSparkassenVersicherungKundenservice", "SVSparkassenVersicherungKundenservice",
        "SV SparkassenVersicherung Kundenservice", "SV SparkassenVersicherung Kundenservice",
        page_num=1, region_index=0,
    )
    assert deltas == []


def test_unterschiedlicher_inhalt_liefert_genau_ein_delta_fuer_die_region():
    deltas = compare_region(
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
    deltas = compare_region(
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
    deltas = compare_region(
        "SVSparkassenVersicherung", "SVSparkassenVersicherung",
        "SV Spa r ka ssen V er si ch eru n g", "SV SparkassenVersicherung",
        page_num=1, region_index=0,
    )
    assert deltas == []


def test_beide_texte_leer_liefert_keine_deltas():
    deltas = compare_region("", "", "", "", page_num=1, region_index=0)
    assert deltas == []


def test_leere_referenz_liefert_ein_delta():
    deltas = compare_region(
        "", "AlphaBeta", "", "Alpha Beta", page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == ""
    assert deltas[0].cnd_text == "Alpha Beta"


def test_leerer_kandidat_liefert_ein_delta():
    deltas = compare_region(
        "AlphaBeta", "", "Alpha Beta", "", page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == "Alpha Beta"
    assert deltas[0].cnd_text == ""


def test_andere_blockreihenfolge_gleiche_zeichen_liefert_keine_deltas():
    """Kernverhalten seit dem Wechsel auf Zeichen-Multiset-Vergleich (siehe
    docs/prompt_table_regions_char_multiset.md): auf echten Kundendokumenten
    liefert die Referenz-Seite EINEN breiten Block pro ZEILE (row-major,
    über alle Spalten hinweg konkateniert), die Kandidaten-Seite dagegen
    EINEN schmalen Block pro SPALTE (column-major) - derselbe Fußzeilentext,
    aber komplett andere Zeichenreihenfolge, weil die Formatierer
    unterschiedlich segmentieren. Ein sequenzieller/String-Vergleich sähe
    hier hunderte False-Deltas, obwohl der Inhalt identisch ist.

    Der frühere Whitespace-freie Stringvergleich (siehe
    docs/prompt_table_regions_whitespace_free.md) hat Wortumstellungen noch
    bewusst als Delta gewertet - das war zum damaligen Zeitpunkt eine
    sinnvolle Annahme, wurde aber durch die Diagnose an den echten
    Referenz-/Kandidat-Dokumenten widerlegt: Block-Reihenfolge ist kein
    inhaltlicher Unterschied, sondern nur eine andere Extraktionsreihenfolge
    desselben Textes. Der Zeichen-Multiset-Vergleich ignoriert daher auch
    die Block-/Wortreihenfolge, nicht nur die Whitespace-Platzierung."""
    deltas = compare_region(
        "SVSparkassenVersicherungKundenservice",
        "KundenserviceSVSparkassenVersicherung",
        "SV SparkassenVersicherung Kundenservice",
        "Kundenservice SV SparkassenVersicherung",
        page_num=1, region_index=0,
    )
    assert deltas == []


def test_zeilenweise_vs_spaltenweise_blockreihenfolge_liefert_keine_deltas():
    """Reales Szenario aus docs/prompt_table_regions_char_multiset.md: ein
    2x2-Fußzeilenraster ("Tel"/"0521" in Zeile 1, "Fax"/"0621" in Zeile 2).
    Referenz konkateniert row-major (ein breiter Block pro Zeile), Kandidat
    column-major (ein schmaler Block pro Spalte) - exakt dieselben 14
    Zeichen, komplett andere Reihenfolge. Da der Inhalt identisch ist, darf
    kein Delta entstehen."""
    ref_nows = "Tel0521Fax0621"  # Zeile 1 + Zeile 2 (row-major)
    cnd_nows = "TelFax05210621"  # Spalte 1 + Spalte 2 (column-major)
    deltas = compare_region(
        ref_nows, cnd_nows,
        "Tel: 0521  Fax: 0621", "Tel: Fax:  0521 0621",
        page_num=1, region_index=0,
    )
    assert deltas == []


def test_zeilenweise_vs_spaltenweise_mit_geaenderter_ziffer_liefert_ein_delta():
    """Gleiches 2x2-Raster wie oben, aber im Kandidaten wurde eine Ziffer der
    zweiten Rufnummer geändert (0621 -> 0622) - eine echte inhaltliche
    Änderung, die trotz unterschiedlicher Blockreihenfolge als GENAU EIN
    Delta erkannt werden muss (Zeichen-Multisets unterscheiden sich)."""
    ref_nows = "Tel0521Fax0621"  # Zeile 1 + Zeile 2 (row-major)
    cnd_nows = "TelFax05210622"  # Spalte 1 + Spalte 2 (column-major), Ziffer geändert
    ref_display = "Tel: 0521  Fax: 0621"
    cnd_display = "Tel: Fax:  0521 0622"
    deltas = compare_region(
        ref_nows, cnd_nows, ref_display, cnd_display,
        page_num=1, region_index=0,
    )
    assert len(deltas) == 1
    assert deltas[0].ref_text == ref_display
    assert deltas[0].cnd_text == cnd_display


def test_deltas_haben_korrektes_page_attribut():
    deltas = compare_region(
        "Alpha", "Beta", "Alpha", "Beta", page_num=7, region_index=2,
    )
    assert len(deltas) == 1
    assert deltas[0].page == 7


# --- merge_compare_region_comparison: mode-Dispatch (docs/prompt_compare_regions_mode.md, Task 2) ---


def _region(mode: str, condition: str = "irrelevant condition"):
    return CompareRegion(x=0, y=0, width=1, height=1, condition=condition, page=1, mode=mode)


def test_merge_sequential_mode_liefert_mehrere_kleine_deltas_statt_einem_grossen():
    """Kerntest aus docs/prompt_compare_regions_mode.md, Task 2: das reale
    Absenderinfo-Feld liefert 'Tel.:' -> 'Tel.' UND ein geändertes Datum -
    im mode='sequential' müssen das MEHRERE kleine Deltas werden (wie beim
    normalen Seitenvergleich), NICHT ein einziges Delta für den gesamten
    Blocktext (das wäre das alte 'unordered'-Verhalten)."""
    ref_display = "Tel.: 0611 178-49830 Wiesbaden, 15.06.2026"
    cnd_display = "Tel. 0611 178-49830 Wiesbaden, 03.07.2026"
    ref_tr_texts = [{0: (ref_display, ref_display)}]
    cnd_tr_texts = [{0: (cnd_display, cnd_display)}]
    profile = Profile(version="1.0", compare_regions=[_region("sequential")])

    deltas = merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)

    assert len(deltas) > 1
    for delta in deltas:
        assert delta.page == 1
        assert delta.ref_text != ref_display
        assert delta.cnd_text != cnd_display


def test_merge_sequential_ist_default_wenn_mode_nicht_gesetzt():
    """CompareRegion.mode hat bereits per Dataclass-Default 'sequential' -
    dieser Test dokumentiert, dass merge_compare_region_comparison sich
    genauso verhält, wenn eine Region ohne explizites mode-Argument
    konstruiert wird (z.B. direkt in Tests, ohne load_profile). Braucht
    genügend unveränderte Wort-Anker zwischen den geänderten Stellen, sonst
    fasst difflib die komplett unterschiedlichen Resttokens zu einem
    einzigen replace-Opcode zusammen (siehe die ausführlichere Variante in
    test_merge_sequential_mode_liefert_mehrere_kleine_deltas_statt_einem_grossen)."""
    ref_display = "Tel.: 0611 178-49830 Wiesbaden, 15.06.2026"
    cnd_display = "Tel. 0611 178-49830 Wiesbaden, 03.07.2026"
    ref_tr_texts = [{0: (ref_display, ref_display)}]
    cnd_tr_texts = [{0: (cnd_display, cnd_display)}]
    region = CompareRegion(x=0, y=0, width=1, height=1, condition="irrelevant condition", page=1)
    assert region.mode == "sequential"
    profile = Profile(version="1.0", compare_regions=[region])

    deltas = merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)

    assert len(deltas) > 1


def test_merge_unordered_mode_ignoriert_weiterhin_blockreihenfolge():
    """mode='unordered' muss über merge_compare_region_comparison exakt das
    bisherige Verhalten liefern (siehe test_compare_region_comparator.py
    oben, compare_region() direkt): row-major vs. column-major Blöcke mit
    identischem Zeichen-Multiset -> kein Delta."""
    ref_nows = "Tel0521Fax0621"
    cnd_nows = "TelFax05210621"
    ref_tr_texts = [{0: (ref_nows, "Tel: 0521  Fax: 0621")}]
    cnd_tr_texts = [{0: (cnd_nows, "Tel: Fax:  0521 0621")}]
    profile = Profile(version="1.0", compare_regions=[_region("unordered")])

    deltas = merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)

    assert deltas == []


def test_merge_unordered_mode_liefert_weiterhin_genau_ein_delta_bei_aenderung():
    ref_nows = "Tel0521Fax0621"
    cnd_nows = "TelFax05210622"
    ref_display = "Tel: 0521  Fax: 0621"
    cnd_display = "Tel: Fax:  0521 0622"
    ref_tr_texts = [{0: (ref_nows, ref_display)}]
    cnd_tr_texts = [{0: (cnd_nows, cnd_display)}]
    profile = Profile(version="1.0", compare_regions=[_region("unordered")])

    deltas = merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)

    assert len(deltas) == 1
    assert deltas[0].ref_text == ref_display
    assert deltas[0].cnd_text == cnd_display


def test_merge_isoliert_zwei_regionen_auf_derselben_seite_voneinander():
    """Zwei compare_regions auf derselben Seite - eine geänderte
    ('sequential'), eine unveränderte ('unordered') - dürfen sich nicht
    gegenseitig beeinflussen: nur die geänderte Region erzeugt Deltas."""
    profile = Profile(
        version="1.0",
        compare_regions=[
            _region("sequential", condition="Region A Bedingung"),
            _region("unordered", condition="Region B Bedingung"),
        ],
    )
    ref_tr_texts = [{
        0: ("Alpha Beta Gamma", "Alpha Beta Gamma"),
        1: ("XY", "XY"),
    }]
    cnd_tr_texts = [{
        0: ("Alpha GEAENDERT Gamma", "Alpha GEAENDERT Gamma"),
        1: ("XY", "XY"),
    }]

    deltas = merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)

    assert len(deltas) >= 1
    assert all(d.page == 1 for d in deltas)
    assert not any("XY" in d.ref_text or "XY" in d.cnd_text for d in deltas)
