"""Testfälle TC-B-001 bis TC-B-003 (P1) und TC-B-004, TC-B-005 (P2) für
engine.batch_processor.

Integrationstests (Schicht 3, siehe CLAUDE.md) – laufen bewusst über
mehrere Module (pdf_extractor, text_comparator, profile_loader,
page_group_detector) hinweg.

Quelle: doc/PaperTrailCompare_Testspezifikation.docx, Abschnitt 7.
Fixtures: tests/fixtures/TC-B-001/ … TC-B-005/
(tests/generate_fixtures.py::generate_tc_b_001_003/generate_tc_b_004/
generate_tc_b_005).
"""
from pathlib import Path

from reportlab.pdfgen import canvas

from engine.batch_processor import batch_compare, batch_compare_by_xmp, read_filelist, split_batch_pdf
from engine.pdf_extractor import extract_pages
from engine.profile_loader import ExcludeRegion, PageGroupPattern, Profile

FIXTURES = Path(__file__).parent / "fixtures"


def _write_single_page_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.save()


def test_batch_compare_erzeugt_einzel_report_pro_ok_paar_im_report_dir(tmp_path, local_filelist):
    """report_dir sorgt dafür, dass batch_compare pro erfolgreich verglichenem
    Paar einen Einzel-Report (analog zum Einzelvergleich) flach im gewählten
    Ausgabeverzeichnis ablegt - auch bei 0 Deltas (siehe prompt_batch_fixes.md,
    Punkt 1)."""
    filelist_path = local_filelist("TC-B-001", 10)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    result = batch_compare(filelist_path, report_dir=report_dir)

    assert result.ok_count == 10
    report_files = sorted(report_dir.glob("*.pdf"))
    assert len(report_files) == 10
    names = {p.name for p in report_files}
    assert "doc_01_ref_doc_01_cnd.pdf" in names
    assert "doc_10_ref_doc_10_cnd.pdf" in names


def test_batch_compare_erzeugt_keinen_einzel_report_fuer_fehlerpaare(tmp_path, local_filelist):
    filelist_path = local_filelist("TC-B-002", 5)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    result = batch_compare(filelist_path, report_dir=report_dir)

    assert result.ok_count == 4
    assert result.error_count == 1
    report_files = sorted(report_dir.glob("*.pdf"))
    assert len(report_files) == 4
    assert not any("doc_03" in p.name for p in report_files)


def test_batch_compare_haengt_zaehler_an_bei_namenskollision(tmp_path):
    """Zwei CSV-Zeilen mit identischem Referenz-/Kandidat-Dateinamen (aber
    unterschiedlichem Verzeichnis) dürfen sich beim Einzel-Report nicht
    gegenseitig überschreiben (siehe prompt_batch_fixes.md, Punkt 1)."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    for d in (dir_a, dir_b):
        _write_single_page_pdf(d / "ref.pdf", "Text A")
        _write_single_page_pdf(d / "cnd.pdf", "Text A")

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(
        f"{dir_a / 'ref.pdf'},{dir_a / 'cnd.pdf'}\n{dir_b / 'ref.pdf'},{dir_b / 'cnd.pdf'}\n",
        encoding="utf-8",
    )
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    result = batch_compare(filelist_path, report_dir=report_dir)

    assert result.ok_count == 2
    report_files = sorted(p.name for p in report_dir.glob("*.pdf"))
    assert report_files == ["ref_cnd.pdf", "ref_cnd_2.pdf"]


def test_read_filelist_ohne_kopfzeile(tmp_path):
    """CSV-Dateiliste hat keine Kopfzeile (Architekturentscheidung Batch-GUI-
    Prompt): jede Zeile ist direkt 'Referenzdatei,Kandidatendatei'."""
    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(
        "/pfad/ref1.pdf,/pfad/cnd1.pdf\n/pfad/ref2.pdf,/pfad/cnd2.pdf\n",
        encoding="utf-8",
    )

    pairs = read_filelist(filelist_path)

    assert pairs == [
        ("/pfad/ref1.pdf", "/pfad/cnd1.pdf"),
        ("/pfad/ref2.pdf", "/pfad/cnd2.pdf"),
    ]


def test_batch_compare_ruft_on_progress_nach_jedem_paar_auf(local_filelist):
    """on_progress(index, total, pair_result) wird nach jedem verarbeiteten
    Paar aufgerufen - Grundlage für Live-Progress-Events Richtung GUI
    (siehe prompt_batch_verarbeitung.md)."""
    calls = []

    def on_progress(index, total, pair_result):
        calls.append((index, total, pair_result))

    result = batch_compare(local_filelist("TC-B-001", 10), on_progress=on_progress)

    assert len(calls) == 10
    assert [c[0] for c in calls] == list(range(1, 11))
    assert all(c[1] == 10 for c in calls)
    assert [c[2] for c in calls] == result.pairs


def test_batch_compare_liefert_total_pages_pro_paar_fuer_uebereinstimmungs_prozent(local_filelist):
    """total_pages (max. Seitenzahl von Referenz/Kandidat) ist Grundlage für
    die Übereinstimmungs-Prozentanzeige je Zeile in der Batch-GUI (siehe
    prompt_batch_verarbeitung.md)."""
    result = batch_compare(local_filelist("TC-B-001", 10))

    for pair in result.pairs:
        assert pair.total_pages == 1


def test_tc_b_001_batch_per_dateiliste_alle_paare_verarbeitet(local_filelist):
    result = batch_compare(local_filelist("TC-B-001", 10))

    assert len(result.pairs) == 10
    assert result.ok_count == 10
    assert result.error_count == 0
    for pair in result.pairs:
        assert pair.status == "ok"
        assert pair.compare_result.has_delta is False


def test_tc_b_002_fehlende_datei_wird_protokolliert_rest_verarbeitet(local_filelist):
    result = batch_compare(local_filelist("TC-B-002", 5))

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


def test_tc_b_004_batch_pdf_splitting_per_seitengruppen_pattern(tmp_path):
    profile = Profile(
        version="1.0",
        page_groups=[PageGroupPattern(pattern=r"^Rechnung Nr\. \S+$", name="Rechnung")],
    )

    output_paths = split_batch_pdf(
        FIXTURES / "TC-B-004" / "batch.pdf", profile, tmp_path / "split"
    )

    assert len(output_paths) == 30
    for path in output_paths:
        assert path.is_file()

    # Jedes Einzeldokument enthält genau eine Seite mit seiner eigenen
    # Rechnungsnummer und keinen Inhalt eines anderen Dokuments.
    for i, path in enumerate(output_paths, start=1):
        pages = extract_pages(str(path))
        assert len(pages) == 1
        expected_id = f"RE-2026-{i:04d}"
        assert expected_id in pages[0]
        assert f"Betrag: {i * 10},00 EUR" in pages[0]


def test_tc_b_005_parallelverarbeitung_im_batch(local_filelist):
    result = batch_compare(local_filelist("TC-B-005", 100, digits=3), workers=4)

    assert len(result.pairs) == 100
    assert result.ok_count == 100
    assert result.error_count == 0

    # Reihenfolge muss trotz Parallelverarbeitung der Dateiliste entsprechen
    # (keine Race Conditions/Vertauschungen zwischen den Paaren).
    for i, pair in enumerate(result.pairs, start=1):
        assert f"doc_{i:03d}_ref.pdf" in pair.ref_path
        assert f"doc_{i:03d}_cnd.pdf" in pair.cnd_path
        assert pair.compare_result.has_delta is False


def test_tc_b_005_parallel_und_sequentiell_liefern_gleiches_ergebnis(local_filelist):
    filelist_path = local_filelist("TC-B-005", 100, digits=3)
    sequential = batch_compare(filelist_path, workers=1)
    parallel = batch_compare(filelist_path, workers=4)

    assert [p.status for p in sequential.pairs] == [p.status for p in parallel.pairs]
    assert [p.ref_path for p in sequential.pairs] == [p.ref_path for p in parallel.pairs]
    assert (
        [p.compare_result.has_delta for p in sequential.pairs]
        == [p.compare_result.has_delta for p in parallel.pairs]
    )


def test_batch_compare_ruft_extraktion_mit_korrekter_role_pro_seite_auf(monkeypatch, local_filelist):
    """Referenz- und Kandidat-Datei müssen mit ihrer jeweils eigenen role
    an extract_pages_for_profile übergeben werden - sonst würde ein
    vergessener Default den Kandidaten fälschlich mit der
    Referenz-OCR-Einstellung lesen (siehe Rückmeldung zum Umsetzungsplan)."""
    seen_roles = []

    def fake_extract(pdf_path, profile, role="reference", warnings=None):
        seen_roles.append((pdf_path, role))
        return extract_pages(pdf_path), False

    import engine.batch_processor as batch_processor_module

    monkeypatch.setattr(batch_processor_module, "extract_pages_for_profile", fake_extract)

    batch_compare(local_filelist("TC-B-001", 10))

    assert seen_roles
    for _, role in seen_roles:
        assert role in ("reference", "candidate")
    # jedes Paar liefert genau einen "reference"- und einen "candidate"-Aufruf
    assert seen_roles[0][1] == "reference"
    assert seen_roles[1][1] == "candidate"


def test_batch_compare_mit_profile_exclude_regions_end_to_end_tc_e_002(tmp_path):
    """TC-E-002 end-to-end über den Produktivpfad batch_compare (nicht nur
    über den direkten Aufruf von region_filter.extract_pages_excluding_regions):
    Ausschluss ist nur für Seite 1 konfiguriert, der Datumsunterschied im
    Kopfbereich auf Seite 2 muss weiterhin als Delta erkannt werden."""
    ref_path = FIXTURES / "TC-E-002" / "ref.pdf"
    cnd_path = FIXTURES / "TC-E-002" / "cnd.pdf"

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(
        version="1.0",
        exclude_regions=[ExcludeRegion(page=1, x=0, y=0, width=250, height=80)],
    )

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is True
    assert any(delta.page == 2 for delta in pair.compare_result.deltas)


def test_batch_compare_reicht_profile_compare_mode_an_compare_durch(monkeypatch, local_filelist):
    """Verdrahtungstest: profile.compare_mode muss bei batch_compare an
    text_comparator.compare durchgereicht werden, nicht nur im Profil
    geladen/validiert werden."""
    seen_modes = []

    import engine.batch_processor as batch_processor_module
    real_compare = batch_processor_module.compare

    def spy_compare(*args, **kwargs):
        seen_modes.append(kwargs.get("compare_mode"))
        return real_compare(*args, **kwargs)

    monkeypatch.setattr(batch_processor_module, "compare", spy_compare)

    profile = Profile(version="1.0", compare_mode="chars")
    result = batch_compare(local_filelist("TC-B-001", 10), profile=profile)

    assert result.ok_count == 10
    assert seen_modes == ["chars"] * 10
