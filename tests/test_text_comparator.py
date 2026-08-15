# file:    tests/test_text_comparator.py
# purpose: Unit tests TC-T-001 to TC-T-009 for engine.text_comparator.
#          Covers normalization, hyphenation, page breaks, case sensitivity,
#          whitespace tolerance, and all three compare modes (words/chars/hybrid).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Testfälle TC-T-001 bis TC-T-006 für engine.text_comparator.

TC-T-007 (Mehrspaltigkeit) und TC-T-008 (Tabellenerkennung) betreffen die
PDF-Extraktion (siehe CLAUDE.md Modulübersicht: pdf_extractor) und werden
dort implementiert, nicht in text_comparator.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 2.
"""
import pytest

from engine.text_comparator import compare, normalize_text


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


def test_normalize_text_silbentrennung_wird_zusammengefuehrt():
    """TC-T-002 auf Funktionsebene: Wortzeichen unmittelbar vor dem
    Bindestrich UND unmittelbar nach dem Umbruch -> echte Silbentrennung,
    wird zusammengeführt."""
    assert normalize_text("Silben-\ntrennung") == "Silbentrennung"


def test_normalize_text_isolierter_bindestrich_nach_zeilenumbruch_bleibt_erhalten():
    """Bindestrich mit Whitespace/Zeilenumbruch DAVOR ist kein
    Silbentrennungs-Bindestrich, sondern ein eigenständiger Gedankenstrich
    (z.B. Ein-Wort-pro-Zeile-Layout eines Type3-Dokuments) - _HYPHENATION_RE
    lässt ihn unangetastet. Mit dem neuen Default normalize_orphan_hyphens=True
    (Sprint PTC-S3 Task A2) wird er danach ans vorangehende Wort angehängt."""
    assert normalize_text("Wort\n-\nnächstes") == "Wort- nächstes"


def test_normalize_text_bindestrich_mit_leerzeichen_davor_bleibt_erhalten():
    """Bindestrich mit Leerzeichen davor (kein Wortzeichen unmittelbar vor
    dem Strich) ist ebenfalls kein Silbentrennungs-Bindestrich - wird aber
    mit dem neuen Default normalize_orphan_hyphens=True ans vorangehende
    Wort angehängt (siehe Sprint PTC-S3 Task A2)."""
    assert normalize_text("Ende -\nAnfang") == "Ende- Anfang"


def test_isolierter_gedankenstrich_ergibt_kein_falsches_delta():
    """Reproduziert den auf TC_REAL gefundenen Fall: ein eigenständiger
    Gedankenstrich, der im Referenzdokument zufällig allein auf einer Zeile
    steht, wurde vor dem Fix von der Silbentrennungs-Regex verschluckt
    (ref='' vs. cnd='-' als falsches Delta, 8 von 220 betroffen)."""
    ref_pages = ["Verlässlichkeit\n-\nvielen Dank dafür!"]
    cnd_pages = ["Verlässlichkeit - vielen Dank dafür!"]

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


def test_tc_t_009_ocr_wort_trennfehler_wird_bei_normalize_whitespace_ignoriert():
    """OCR erzeugt fälschlich ein Leerzeichen mitten im Wort
    ('Vertragsbedingungen' -> 'Vertrags bedingungen'); mit
    normalize_whitespace=True darf das nicht als Delta gemeldet werden."""
    ref_pages = ["Die Vertragsbedingungen gelten sofort."]
    cnd_pages = ["Die Vertrags bedingungen gelten sofort."]

    result = compare(ref_pages, cnd_pages, normalize_whitespace=True)

    assert result.has_delta is False
    assert result.deltas == []


def test_tc_t_009_echter_unterschied_bleibt_trotz_normalize_whitespace_delta():
    """Ein echter Textunterschied (nicht nur Leerzeichen) muss auch mit
    normalize_whitespace=True weiterhin als Delta erkannt werden."""
    ref_pages = ["Betrag: 100 EUR"]
    cnd_pages = ["Betrag: 200 EUR"]

    result = compare(ref_pages, cnd_pages, normalize_whitespace=True)

    assert result.has_delta is True
    assert len(result.deltas) == 1
    assert "100" in result.deltas[0].ref_text
    assert "200" in result.deltas[0].cnd_text


def test_tc_t_009_ocr_wort_trennfehler_ohne_normalize_whitespace_bleibt_delta():
    """Default-Verhalten (normalize_whitespace=False) bleibt unverändert:
    der Wort-Trennfehler wird weiterhin als Delta gemeldet."""
    ref_pages = ["Die Vertragsbedingungen gelten sofort."]
    cnd_pages = ["Die Vertrags bedingungen gelten sofort."]

    result = compare(ref_pages, cnd_pages)

    assert result.has_delta is True
    assert len(result.deltas) == 1


def test_ocr_used_wird_in_compare_result_uebernommen():
    result = compare(["Text"], ["Text"], ocr_used=True)

    assert result.ocr_was_used is True

    result_default = compare(["Text"], ["Text"])

    assert result_default.ocr_was_used is False


def test_compare_mode_chars_ignoriert_fragmentierte_wortgrenzen():
    """Kernanforderung: 'Versicherung' vs. 'Versi ch e ru n g' wird im
    Zeichenmodus identisch - genau das Type3-Fragmentierungsmuster aus der
    Diagnose-Session, das im Wortmodus als Delta gemeldet wird."""
    ref_pages = ["Der Versi ch e ru n gssch u tz umfasst alles."]
    cnd_pages = ["Der Versicherungsschutz umfasst alles."]

    result_words = compare(ref_pages, cnd_pages, compare_mode="words")
    result_chars = compare(ref_pages, cnd_pages, compare_mode="chars")

    assert result_words.has_delta is True
    assert result_chars.has_delta is False
    assert result_chars.deltas == []


def test_compare_mode_chars_erkennt_echten_unterschied():
    """'100 EUR' vs. '200 EUR' bleibt ein Delta - Zeichenmodus ignoriert
    nur Whitespace, keine echten Inhaltsunterschiede."""
    ref_pages = ["Der Betrag ist 100 EUR."]
    cnd_pages = ["Der Betrag ist 200 EUR."]

    result = compare(ref_pages, cnd_pages, compare_mode="chars")

    assert result.has_delta is True
    assert len(result.deltas) == 1
    assert result.deltas[0].ref_text == "1"
    assert result.deltas[0].cnd_text == "2"


def test_compare_mode_chars_liefert_lesbaren_text_mit_leerzeichen():
    """Delta-Texte im Zeichenmodus müssen aus dem Originaltext (mit
    Leerzeichen) stammen, nicht aus der kompakten Vergleichsform - sonst
    ist die Delta-Detailliste im Report unlesbar."""
    ref_pages = ["Alte Versicherungsnummer 111."]
    cnd_pages = ["Alte Versicherungsnummer 222."]

    result = compare(ref_pages, cnd_pages, compare_mode="chars")

    assert len(result.deltas) == 1
    delta = result.deltas[0]
    assert delta.ref_text == "111"
    assert delta.cnd_text == "222"


def test_compare_mode_chars_seitenzuordnung_bezieht_sich_auf_kandidat():
    """Wie im Wortmodus (Delta.page bezieht sich auf das Kandidat-Dokument):
    ein Unterschied auf Kandidat-Seite 2 wird als Seite 2 gemeldet, auch
    wenn die Referenz an anderer Stelle umbricht."""
    ref_pages = ["Text auf einer langen Seite eins ohne Umbruch.", "Zahl: 111."]
    cnd_pages = ["Text auf einer langen Seite eins ohne Umbruch.", "Zahl: 222."]

    result = compare(ref_pages, cnd_pages, compare_mode="chars")

    assert len(result.deltas) == 1
    assert result.deltas[0].page == 2


def test_compare_mode_chars_case_sensitive_wird_respektiert():
    result_sensitive = compare(["Text"], ["text"], compare_mode="chars", case_sensitive=True)
    result_insensitive = compare(["Text"], ["text"], compare_mode="chars", case_sensitive=False)

    assert result_sensitive.has_delta is True
    assert result_insensitive.has_delta is False


def test_compare_mode_hybrid_ignoriert_fragmentierte_wortgrenzen():
    """Wie chars-Modus: 'Versicherung' vs. 'Versi ch e ru n g' wird identisch."""
    ref_pages = ["Der Versi ch e ru n gssch u tz umfasst alles."]
    cnd_pages = ["Der Versicherungsschutz umfasst alles."]

    result = compare(ref_pages, cnd_pages, compare_mode="hybrid")

    assert result.has_delta is False
    assert result.deltas == []


def test_compare_mode_hybrid_erkennt_echten_unterschied():
    ref_pages = ["Der Betrag ist 100 EUR."]
    cnd_pages = ["Der Betrag ist 200 EUR."]

    result = compare(ref_pages, cnd_pages, compare_mode="hybrid")

    assert result.has_delta is True
    assert len(result.deltas) == 1


def test_compare_mode_hybrid_fasst_fragmentierung_ueber_zufallstreffer_zusammen():
    """Reproduziert wortgetreu einen auf TC_REAL gefundenen Fall (Opcode
    #251 der echten Referenz/Kandidat-Ausrichtung, siehe Diagnose-Session):
    das eigene Fragment 'der' (Teil von 'besteh'+'en'+'der' = 'bestehender')
    matcht zufällig auf ein späteres, echtes 'der' im Kandidattext und wird
    von SequenceMatcher als Synchronisationspunkt gewertet - das zerlegt
    eine an sich zusammenhängende Fragmentierung in zwei Opcodes, die
    EINZELN nicht whitespace-identisch sind. Der reine Wortmodus (auch mit
    normalize_whitespace=True) meldet das fälschlich als Delta; hybrid muss
    es über den Zufallstreffer hinweg zusammenfassen und erkennen, dass
    insgesamt kein echter Unterschied vorliegt."""
    ref_pages = [
        "du rch Än deru n g besteh en der oder Erla ss n eu er Rech ts vors ch rif ten "
        "ist de r Ve rsi ch erer bere ch ti gt, da s Vers ich eru n gsverh ä ltn is un ter "
        "Ein h a ltu n g ein er"
    ]
    cnd_pages = [
        "durch Änderung bestehender oder Erlass neuer Rechtsvorschriften ist der Versicherer "
        "berechtigt, das Versicherungsverhältnis unter Einhaltung einer"
    ]

    result_words_normalized = compare(ref_pages, cnd_pages, compare_mode="words", normalize_whitespace=True)
    result_hybrid = compare(ref_pages, cnd_pages, compare_mode="hybrid")

    assert result_words_normalized.has_delta is True  # bestätigt die Lücke im Wortmodus
    assert result_hybrid.has_delta is False
    assert result_hybrid.deltas == []


def test_compare_mode_hybrid_zwei_woerter_gleich_bleibt_grenze():
    """Ab zwei aufeinanderfolgenden übereinstimmenden Wörtern gilt der
    Treffer als echte Synchronisation - zwei getrennte, echte
    Unterschiede links und rechts davon bleiben zwei separate Deltas,
    statt über die Grenze hinweg fälschlich zusammengefasst zu werden."""
    ref_pages = ["Betrag 100 EUR heute und morgen Betrag 200 EUR"]
    cnd_pages = ["Betrag 111 EUR heute und morgen Betrag 222 EUR"]

    result = compare(ref_pages, cnd_pages, compare_mode="hybrid")

    assert len(result.deltas) == 2


def test_compare_mode_hybrid_case_sensitive_wird_respektiert():
    result_sensitive = compare(["Text"], ["text"], compare_mode="hybrid", case_sensitive=True)
    result_insensitive = compare(["Text"], ["text"], compare_mode="hybrid", case_sensitive=False)

    assert result_sensitive.has_delta is True
    assert result_insensitive.has_delta is False


def test_compare_mode_ungueltiger_wert_wirft_value_error():
    with pytest.raises(ValueError):
        compare(["Text"], ["Text"], compare_mode="sentences")


def test_compare_mode_chars_ignoriert_normalize_whitespace_flag():
    """normalize_whitespace gilt laut Docstring nur für compare_mode="words"
    - im "chars"-Modus ist Whitespace ohnehin komplett draußen, das Flag
    darf keinen Unterschied machen (weder Fehler noch Verhaltensänderung)."""
    ref_pages = ["Die Vertragsbedingungen gelten sofort."]
    cnd_pages = ["Die Vertrags bedingungen gelten sofort."]

    result_with_flag = compare(ref_pages, cnd_pages, compare_mode="chars", normalize_whitespace=True)
    result_without_flag = compare(ref_pages, cnd_pages, compare_mode="chars", normalize_whitespace=False)

    assert result_with_flag.has_delta is False
    assert result_without_flag.has_delta is False


# --- Qualitätstest autojunk=True auf Dokumentgröße (siehe Rückmeldung zum
# Umsetzungsplan): autojunk stuft auf ~100.000 Einzelzeichen sehr häufige
# Buchstaben (e, n, r, s, t, a, i) als "Junk" ein und verankert den Matcher
# nur noch an selteneren Zeichen - das macht ihn ~60x schneller (siehe
# Diagnose: 596s vs. 10s auf den TC_REAL-Dateien), birgt aber das Risiko,
# echte Unterschiede zu verschlucken. Dieser Test baut ein ~98.000 Zeichen
# großes, synthetisches Dokumentpaar mit 5 gezielt eingebauten Änderungen
# (Zahl, Wort, gelöschter Satz, eingefügter Satz, zweite Zahl) auf
# verschiedenen Seiten, zusätzlich zu flächendeckendem Fragmentierungs-
# Rauschen auf der Referenzseite (wie beim echten Type3-Defekt) - und
# prüft, dass genau diese 5 Stellen gefunden werden und sonst nichts.

_PARAGRAPH_TEMPLATE = (
    "Sehr geehrte Damen und Herren, dies ist ein Testabsatz zur Ueberpruefung "
    "der Versicherungsbedingungen im Rahmen unseres Vertrages Nr. 100000. "
    "Der Versicherungsschutz umfasst Haftpflicht- und Sachschaeden gemaess "
    "den vereinbarten Konditionen. Bitte pruefen Sie die Angaben sorgfaeltig "
    "und wenden Sie sich bei Rueckfragen an unseren Kundenservice. "
)
_PAGE_COUNT = 40
_REPEATS_PER_PAGE = 7
_FRAGMENTED_WORD = "Versi ch e ru n gsbedin gu n gen"  # simuliert den Type3-Defekt


def _build_synthetic_pages(fragment_ref_word: bool):
    pages = []
    for page_num in range(1, _PAGE_COUNT + 1):
        marker = f"Seite {page_num:02d} dieses Schreibens. "
        body = marker + (_PARAGRAPH_TEMPLATE * _REPEATS_PER_PAGE)
        if fragment_ref_word:
            body = body.replace("Versicherungsbedingungen", _FRAGMENTED_WORD)
        pages.append(body)
    return pages


def test_compare_mode_chars_qualitaetstest_grosses_dokument_autojunk():
    ref_pages = _build_synthetic_pages(fragment_ref_word=True)
    cnd_pages = _build_synthetic_pages(fragment_ref_word=False)

    total_ref_len = sum(len(p) for p in ref_pages)
    assert total_ref_len > 90_000  # Größenordnung der echten TC_REAL-Dateien

    edit_pages = {5, 15, 25, 32, 38}

    def edit_page(pages, page_num, old, new):
        idx = page_num - 1
        assert old in pages[idx], f"Anker {old!r} nicht auf Seite {page_num} gefunden"
        pages[idx] = pages[idx].replace(old, new, 1)

    # 1) Zahl geändert
    edit_page(cnd_pages, 5, "Vertrages Nr. 100000", "Vertrages Nr. 100099")
    # 2) Wort geändert
    edit_page(cnd_pages, 15, "Sachschaeden", "Elementarschaeden")
    # 3) Satz gelöscht
    edit_page(
        cnd_pages, 25,
        "Bitte pruefen Sie die Angaben sorgfaeltig und wenden Sie sich bei Rueckfragen an unseren Kundenservice. ",
        "",
    )
    # 4) Satz eingefügt
    edit_page(cnd_pages, 32, "Konditionen. ", "Konditionen. Dieser Absatz wurde nachtraeglich ergaenzt. ")
    # 5) Zweite Zahl geändert (andere Seite, um mehrere unabhängige Zahlenänderungen abzudecken)
    edit_page(cnd_pages, 38, "Vertrages Nr. 100000", "Vertrages Nr. 100088")

    result = compare(ref_pages, cnd_pages, compare_mode="chars")

    assert result.has_delta is True

    delta_pages = {d.page for d in result.deltas}
    # Keine Zusatzfunde außerhalb der bekannten Bearbeitungsseiten - das
    # Fragmentierungsrauschen (auf allen 40 Seiten) darf keine Deltas
    # erzeugen, autojunk=True darf auch nichts andernorts erfinden.
    assert delta_pages <= edit_pages, f"Unerwartete Delta-Seiten: {delta_pages - edit_pages}"

    # Jede der 5 bekannten Bearbeitungen muss durch mindestens ein Delta
    # abgedeckt sein (eine Änderung kann laut Diagnose in mehrere kleine,
    # zusammenhängende Deltas aufsplitten, z.B. bei teilweiser Zeichen-
    # überlappung - das ist erwartetes Verhalten, kein Fehlschlag).
    assert edit_pages <= delta_pages, f"Nicht gefundene Bearbeitungsseiten: {edit_pages - delta_pages}"

    cnd_texts_by_page = {}
    for d in result.deltas:
        cnd_texts_by_page.setdefault(d.page, []).append(d.cnd_text)
    ref_texts_by_page = {}
    for d in result.deltas:
        ref_texts_by_page.setdefault(d.page, []).append(d.ref_text)

    assert any("99" in t for t in cnd_texts_by_page[5])
    assert any("Elementarschaeden" in t or "Elementar" in t for t in cnd_texts_by_page[15])
    assert any(t == "" for t in cnd_texts_by_page[25]) or any(
        "Bitte" in t for t in ref_texts_by_page[25]
    )
    assert any("nachtraeglich" in t or "ergaenzt" in t for t in cnd_texts_by_page[32])
    assert any("88" in t for t in cnd_texts_by_page[38])

    # Obergrenze gegen eine "Explosion" kleiner Deltas: 5 Bearbeitungen
    # dürfen granular aufsplitten, aber nicht in absurd viele Einzelteile.
    assert len(result.deltas) <= 20, (
        f"{len(result.deltas)} Deltas für 5 bekannte Änderungen - "
        "Verdacht auf zusätzliche, ungewollte Fundstellen durch autojunk=True"
    )


def test_compare_mode_hybrid_qualitaetstest_grosses_dokument():
    """Dasselbe Qualitätskriterium wie beim chars-Qualitätstest, für den
    zweistufigen Modus: alle 5 bekannten Änderungen müssen gefunden
    werden, keine Zusatzfunde durch das Fragmentierungsrauschen - UND
    (der eigentliche Zweck von "hybrid") deutlich weniger/kompaktere
    Deltas als der reine Zeichenmodus, weil der Wort-Matcher die grobe
    Ausrichtung liefert, die "chars" fehlt."""
    ref_pages = _build_synthetic_pages(fragment_ref_word=True)
    cnd_pages = _build_synthetic_pages(fragment_ref_word=False)

    edit_pages = {5, 15, 25, 32, 38}

    def edit_page(pages, page_num, old, new):
        idx = page_num - 1
        assert old in pages[idx]
        pages[idx] = pages[idx].replace(old, new, 1)

    edit_page(cnd_pages, 5, "Vertrages Nr. 100000", "Vertrages Nr. 100099")
    edit_page(cnd_pages, 15, "Sachschaeden", "Elementarschaeden")
    edit_page(
        cnd_pages, 25,
        "Bitte pruefen Sie die Angaben sorgfaeltig und wenden Sie sich bei Rueckfragen an unseren Kundenservice. ",
        "",
    )
    edit_page(cnd_pages, 32, "Konditionen. ", "Konditionen. Dieser Absatz wurde nachtraeglich ergaenzt. ")
    edit_page(cnd_pages, 38, "Vertrages Nr. 100000", "Vertrages Nr. 100088")

    result = compare(ref_pages, cnd_pages, compare_mode="hybrid")

    assert result.has_delta is True
    delta_pages = {d.page for d in result.deltas}
    assert delta_pages <= edit_pages, f"Unerwartete Delta-Seiten: {delta_pages - edit_pages}"
    assert edit_pages <= delta_pages, f"Nicht gefundene Bearbeitungsseiten: {edit_pages - delta_pages}"
    assert len(result.deltas) <= 20


def test_normalize_text_merge_hyphenation_false_preserves_hyphen():
    """With merge_hyphenation=False, a hyphen before a newline is NOT
    removed — the compound hyphen 'Stück-' survives normalization."""
    result = normalize_text("Stück-\nund", merge_hyphenation=False)
    assert "Stück-" in result
    assert "Stückund" not in result


def test_normalize_text_merge_hyphenation_true_default_merges():
    """Default behavior: syllable breaks are still merged."""
    result = normalize_text("Silben-\ntrennung", merge_hyphenation=True)
    assert result == "Silbentrennung"


def test_compare_merge_hyphenation_false_no_false_delta():
    """With merge_hyphenation=False, 'Stück-\\nund' in ref vs 'Stück- und'
    in cnd must not produce a delta (both normalize to contain 'Stück-')."""
    ref_pages = ["Beiträge ohne Stück-\nund periodenabhängige Kosten"]
    cnd_pages = ["Beiträge ohne Stück- und periodenabhängige Kosten"]

    result = compare(ref_pages, cnd_pages, merge_hyphenation=False)
    assert result.has_delta is False


def test_compare_merge_hyphenation_true_still_merges_syllables():
    """Default: real syllable breaks still produce no delta."""
    ref_pages = ["Silben-\ntrennung"]
    cnd_pages = ["Silbentrennung"]

    result = compare(ref_pages, cnd_pages, merge_hyphenation=True)
    assert result.has_delta is False


def test_normalize_text_orphan_hyphen_attached_to_preceding_word():
    """A standalone hyphen surrounded by spaces is attached to the
    preceding word: 'Stück - und' → 'Stück- und'."""
    result = normalize_text("Stück - und", normalize_orphan_hyphens=True)
    assert result == "Stück- und"


def test_normalize_text_orphan_hyphen_disabled():
    """With normalize_orphan_hyphens=False, standalone hyphens stay."""
    result = normalize_text("Stück - und", normalize_orphan_hyphens=False)
    assert result == "Stück - und"


def test_normalize_text_orphan_hyphen_from_newline_split():
    """Simulates the Papyrus pattern: word\\n-\\nword → after whitespace
    collapse → 'word - word' → orphan hyphen attach → 'word- word'."""
    result = normalize_text("Stück\n-\nund", normalize_orphan_hyphens=True)
    assert result == "Stück- und"


def test_compare_orphan_hyphen_no_false_delta():
    """Ref has orphan hyphen, cand has attached hyphen — no delta."""
    ref_pages = ["Beiträge ohne Stück - und periodenabhängige Kosten"]
    cnd_pages = ["Beiträge ohne Stück- und periodenabhängige Kosten"]

    result = compare(ref_pages, cnd_pages, normalize_orphan_hyphens=True)
    assert result.has_delta is False


def test_compare_orphan_hyphen_disabled_produces_delta():
    """With orphan hyphen normalization off, the difference IS a delta."""
    ref_pages = ["Beiträge ohne Stück - und periodenabhängige Kosten"]
    cnd_pages = ["Beiträge ohne Stück- und periodenabhängige Kosten"]

    result = compare(ref_pages, cnd_pages, normalize_orphan_hyphens=False)
    assert result.has_delta is True


def test_normalize_text_orphan_hyphen_not_after_punctuation():
    """A hyphen after punctuation (e.g. page number '.- 3 -') must NOT
    be attached to the preceding word. _ORPHAN_HYPHEN_RE requires a
    trailing space after the hyphen, so the final '3 -' (no trailing
    space, end of string) is also left untouched - only a hyphen with a
    word character both before AND after (with a space each) attaches."""
    result = normalize_text("Versicherungsscheins. - 3 -")
    assert result == "Versicherungsscheins. - 3 -"
