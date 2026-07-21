"""P1-Testfälle TC-B-001 bis TC-B-003 für engine.batch_processor.

Integrationstests (Schicht 3, siehe CLAUDE.md) – laufen bewusst über
mehrere Module (pdf_extractor, text_comparator, profile_loader) hinweg.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 7.
Fixtures: tests/fixtures/TC-B-001/, TC-B-002/, TC-B-003/
(tests/generate_fixtures.py::generate_tc_b_001_003).
"""
from pathlib import Path

from engine.batch_processor import batch_compare, batch_compare_by_xmp

FIXTURES = Path(__file__).parent / "fixtures"


def test_tc_b_001_batch_per_dateiliste_alle_paare_verarbeitet():
    result = batch_compare(FIXTURES / "TC-B-001" / "filelist.csv")

    assert len(result.pairs) == 10
    assert result.ok_count == 10
    assert result.error_count == 0
    for pair in result.pairs:
        assert pair.status == "ok"
        assert pair.compare_result.has_delta is False


def test_tc_b_002_fehlende_datei_wird_protokolliert_rest_verarbeitet():
    result = batch_compare(FIXTURES / "TC-B-002" / "filelist.csv")

    assert len(result.pairs) == 5
    assert result.ok_count == 4
    assert result.error_count == 1

    error_pairs = [p for p in result.pairs if p.status == "error"]
    assert len(error_pairs) == 1
    assert "doc_03_cnd.pdf" in error_pairs[0].error

    ok_pairs = [p for p in result.pairs if p.status == "ok"]
    assert len(ok_pairs) == 4
    for pair in ok_pairs:
        assert pair.compare_result.has_delta is False


def test_tc_b_003_batch_per_xmp_metadaten_document_id():
    # ref_*.pdf und cnd_*.pdf liegen in einem gemeinsamen Verzeichnis (siehe
    # Fixture-Vorbedingung: "Verzeichnis mit 20 PDFs"); ref_glob/cnd_glob
    # trennen sie anhand des Dateinamens.
    result = batch_compare_by_xmp(
        FIXTURES / "TC-B-003", FIXTURES / "TC-B-003",
        ref_glob="ref_*.pdf", cnd_glob="cnd_*.pdf",
    )

    # 10 ref_*.pdf + 10 cnd_*.pdf, je Paar dieselbe Document-ID -> 10 Paare.
    assert len(result.pairs) == 10
    assert result.ok_count == 10
    assert result.error_count == 0

    matched_refs = {Path(p.ref_path).name for p in result.pairs}
    matched_cnds = {Path(p.cnd_path).name for p in result.pairs}
    assert matched_refs == {f"ref_{i:02d}.pdf" for i in range(1, 11)}
    assert matched_cnds == {f"cnd_{i:02d}.pdf" for i in range(1, 11)}

    # ref/cnd unterscheiden sich inhaltlich ("Variante: ref" vs. "Variante: cnd") -
    # die Zuordnung ist korrekt, wenn jedes Paar (erwartungsgemäß) ein Delta liefert.
    for pair in result.pairs:
        assert pair.compare_result.has_delta is True
