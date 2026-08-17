# file:    tests/test_batch_processor.py
# purpose: Integration tests TC-B-001 to TC-B-005 for engine.batch_processor.
#          Covers file-list batch, error handling, XMP pairing, PDF splitting,
#          and parallel processing.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

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
import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engine.batch_processor import batch_compare, batch_compare_by_xmp, read_filelist, split_batch_pdf
from engine.pdf_extractor import extract_pages
from engine.profile_loader import ExcludeRegion, OcrConfig, PageGroupPattern, Profile, CompareRegion

FIXTURES = Path(__file__).parent / "fixtures"


def _write_single_page_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.save()


def _write_image_pdf(path: Path, text: str) -> None:
    """Rendert `text` via Pillow auf eine seitengroße Bitmap (kein
    Textlayer) und bettet diese in ein einseitiges PDF ein - analog zu
    tests/generate_fixtures.py::_render_text_as_scanned_page, deren
    Auflösung/Fontgröße sich bereits als zuverlässig für Tesseract erwiesen
    hat. Erfordert echtes OCR zur Extraktion (kein nativer Text)."""
    from PIL import Image, ImageDraw, ImageFont

    px_w, px_h = 1600, 2262  # ~ A4 bei 200dpi, wie generate_fixtures.py
    img = Image.new("RGB", (px_w, px_h), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except OSError:
        font = ImageFont.load_default()

    draw.text((120, 150), text, fill="black", font=font)

    img_path = path.with_suffix(".png")
    img.save(img_path)

    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(str(img_path), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()
    img_path.unlink()


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
    assert "PTC-Vergleich_doc_01_ref_doc_01_cnd.pdf" in names
    assert "PTC-Vergleich_doc_10_ref_doc_10_cnd.pdf" in names


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
    assert report_files == ["PTC-Vergleich_ref_cnd.pdf", "PTC-Vergleich_ref_cnd_2.pdf"]


def test_batch_compare_einzel_report_zeigt_verarbeitungsdauer_statt_strich(tmp_path, local_filelist):
    """_compare_pair() misst die Extraktions-/Vergleichsdauer und reicht sie
    als duration_seconds an generate_report() durch, damit die
    Zusammenfassungsseite des Einzel-Reports aus dem Batch-Lauf einen echten
    Sekundenwert statt "--" bei "Verarbeitungsdauer" zeigt (Sprint PTC-2,
    Task A)."""
    filelist_path = local_filelist("TC-B-001", 1)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    result = batch_compare(filelist_path, report_dir=report_dir)

    assert result.ok_count == 1
    report_files = sorted(report_dir.glob("*.pdf"))
    assert len(report_files) == 1

    import re

    import pymupdf

    doc = pymupdf.open(report_files[0])
    page_text = doc[0].get_text()
    doc.close()

    match = re.search(r"Verarbeitungsdauer\s*\n?\s*([\d,.]+)\s*s", page_text)
    assert match is not None, f"Kein numerischer Dauerwert gefunden in: {page_text!r}"
    assert match.group(1) != "--"


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
        pages = extract_pages(pdf_path)
        return pages, False, [{} for _ in pages]

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


# --- compare_regions end-to-end via batch_compare (Sprint PTC-S3 Task C, siehe
# docs/prompt_table_regions.md, Step 4) ---


def test_batch_compare_compare_region_eliminiert_false_delta_tc_tr_001(tmp_path):
    """TC-TR-001 über den Produktivpfad batch_compare: ref.pdf schreibt die
    Fußzeile als einen breiten Block, cnd.pdf als vier schmale Blöcke -
    identischer Wortinhalt. Mit korrekt konfigurierter compare_region darf
    das nicht als Delta erkannt werden."""
    ref_path = FIXTURES / "TC-TR-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-TR-001" / "cnd.pdf"

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(
        version="1.0",
        compare_regions=[
            CompareRegion(
                page=1, x=0, y=650, width=400, height=250,
                condition="SV SparkassenVersicherung",
                # mode="unordered" explizit (siehe docs/prompt_compare_regions_mode.md,
                # Task 2) - dieser Test prüft genau das Zeichen-Multiset-Verhalten,
                # nicht den neuen sequenziellen Default.
                mode="unordered",
            )
        ],
    )

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is False
    assert pair.compare_result.deltas == []


def test_batch_compare_compare_region_erkennt_echte_aenderung_tc_tr_002(tmp_path):
    """TC-TR-002 über batch_compare: die Telefonnummer in der Kandidaten-
    Fußzeile ist tatsächlich geändert - der Whitespace-freie Vergleich muss
    das als GENAU EIN Delta für die gesamte Region melden (siehe
    docs/prompt_table_regions_whitespace_free.md), mit lesbarem Text."""
    ref_path = FIXTURES / "TC-TR-002" / "ref.pdf"
    cnd_path = FIXTURES / "TC-TR-002" / "cnd.pdf"

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(
        version="1.0",
        compare_regions=[
            CompareRegion(
                page=1, x=0, y=650, width=400, height=250,
                condition="SV SparkassenVersicherung",
                mode="unordered",
            )
        ],
    )

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is True
    assert len(pair.compare_result.deltas) == 1
    delta = pair.compare_result.deltas[0]
    assert "0800-1234" in delta.ref_text
    assert "0800-5678" in delta.cnd_text


# --- Delta-Liste seitenweise sortiert über batch_compare (docs/prompt_compare_regions_mode.md, Task 3) ---


def _write_multi_page_pdf(path: Path, page_1_footer: str, body_lines: list) -> None:
    """Siehe tests/test_main.py::_write_multi_page_pdf - identische Logik,
    hier separat gehalten, damit test_batch_processor.py nicht von
    test_main.py importieren muss."""
    c = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    c.setFont("Helvetica", 11)
    c.drawString(30, height - 100, "Seite 1 Fliesstext (identisch in ref und cnd).")
    c.drawString(30, height - 750, page_1_footer)
    c.showPage()
    for line in body_lines:
        c.drawString(30, height - 100, line)
        c.showPage()
    c.save()


def test_batch_compare_delta_liste_ist_seitenweise_sortiert(tmp_path):
    """Wie test_main.py::test_delta_liste_ist_seitenweise_sortiert_..., aber
    über den batch_compare-Pfad (engine.batch_processor), der dieselbe
    Merge-Logik verwendet - Task 3 muss an BEIDEN Stellen greifen (Einzel-
    UND Batch-Vergleich, siehe docs/prompt_compare_regions_mode.md)."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"

    _write_multi_page_pdf(
        ref_path, "Footer Alpha Beta",
        ["Seite zwei referenz", "Seite drei referenz", "Seite vier referenz", "Seite fuenf referenz"],
    )
    _write_multi_page_pdf(
        cnd_path, "Footer Alpha Gamma",
        ["Seite zwei kandidat", "Seite drei kandidat", "Seite vier kandidat", "Seite fuenf kandidat"],
    )

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(
        version="1.0",
        compare_regions=[
            CompareRegion(page=1, x=0, y=650, width=400, height=250, condition="Footer Alpha")
        ],
    )

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    deltas = result.pairs[0].compare_result.deltas
    pages = [d.page for d in deltas]
    assert pages == sorted(pages), f"Delta-Liste nicht seitenweise sortiert: {pages}"
    assert pages[0] == 1, "compare_region-Delta (Seite 1) muss an erster Stelle stehen"
    assert 2 in pages and 5 in pages


# --- Regression: stdout-Progress-Contract (siehe docs/prompt_bugfix_batch_progress.md) ---
#
# Root Cause des Bugs: compare_region_comparator._NO_POSITION war -1. Die
# GUI (src-tauri/src/lib.rs) bildet Delta.position auf ein Rust `u32` ab;
# ein negativer Wert lässt serde_json::from_value fehlschlagen, was in
# start_batch_compare per `if let Ok(...)` OHNE Fehlermeldung verschluckt
# wird - kein Progress-Event, keine Ergebnisliste in der GUI, obwohl der
# Python-Batch selbst fehlerfrei durchläuft und "N ok" meldet. Dieser Test
# sperrt den Vertrag: JEDES Feld, das die JSON-Progress-Zeile pro Paar
# transportiert (insbesondere Delta.position), muss mit einem
# vorzeichenlosen 32-Bit-Integer kompatibel sein - nicht nur "irgendein
# gültiger JSON-Wert", wie ein reiner Python-seitiger Test es abdecken
# würde (pytest allein hätte diesen Bug nie gefunden, siehe Root-Cause-
# Bericht: das Python-JSON war immer syntaktisch valide, nur der WERT
# verletzte die Rust-Seite unsichtbar für Python-Tests).
def test_batch_json_lines_positionsfeld_ist_stets_nicht_negativ_tc_tr_002(tmp_path):
    """Regressionstest für den Progress-Anzeige-Bug: eine compare_region mit
    echtem Delta (TC-TR-002) darf im emittierten JSON keine negativen
    Zahlenwerte enthalten - src-tauri/src/lib.rs::Delta.position ist ein
    Rust `u32` (vorzeichenlos); ein negativer Sentinel-Wert lässt die
    Deserialisierung dort silently fehlschlagen (kein Fehler, kein Event),
    obwohl der Python-Batch selbst korrekt durchläuft. Läuft über
    engine.__main__.main(), nicht batch_compare() direkt, weil der Bug
    exakt an der JSON-Serialisierungsgrenze (stdout) auftrat, nicht in den
    Python-Objekten selbst."""
    from engine.__main__ import main

    ref_path = FIXTURES / "TC-TR-002" / "ref.pdf"
    cnd_path = FIXTURES / "TC-TR-002" / "cnd.pdf"

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "compare_regions": [
                {
                    "page": 1, "x": 0, "y": 650, "width": 400, "height": 250,
                    "condition": "SV SparkassenVersicherung",
                    # mode="unordered" explizit, weil dieser Test GENAU den
                    # _NO_POSITION-Sentinel (0) des Multiset-Vergleichs prüft
                    # (siehe docs/prompt_bugfix_batch_progress.md) - mit dem
                    # neuen Default mode="sequential" (siehe
                    # docs/prompt_compare_regions_mode.md, Task 2) trüge das
                    # Delta stattdessen eine echte Wort-Position.
                    "mode": "unordered",
                }
            ],
        }),
        encoding="utf-8",
    )

    import subprocess
    import sys as _sys

    proc = subprocess.run(
        [
            _sys.executable, "-m", "engine", "batch", str(filelist_path),
            "--output-dir", str(tmp_path), "--profile", str(profile_path),
        ],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )

    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 2  # 1 Progress-Zeile + 1 done-Zeile

    progress = json.loads(lines[0])
    assert progress["type"] == "progress"
    done = json.loads(lines[1])
    assert done["type"] == "done"  # Progress-Zeile(n) VOR der done-Zeile

    pair = progress["pair"]
    assert pair["compare_result"]["has_delta"] is True
    deltas = pair["compare_result"]["deltas"]
    assert len(deltas) == 1  # bestätigt: der compare_region-Pfad wurde tatsächlich getroffen

    # Der eigentliche Regressionstest: JEDER Zahlenwert im Payload muss
    # nicht-negativ sein (u32-kompatibel) - nicht nur "ist JSON", was
    # reines json.loads() bereits für den alten, kaputten Wert -1 bestätigt
    # hätte.
    def assert_no_negative_numbers(value, path="root"):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            assert value >= 0, f"Negativer Zahlenwert bei {path}: {value}"
        elif isinstance(value, dict):
            for key, sub in value.items():
                assert_no_negative_numbers(sub, f"{path}.{key}")
        elif isinstance(value, list):
            for index, sub in enumerate(value):
                assert_no_negative_numbers(sub, f"{path}[{index}]")

    assert_no_negative_numbers(progress)
    assert deltas[0]["position"] == 0


def test_batch_compare_mit_profile_case_sensitive_false_end_to_end(tmp_path):
    """case_sensitive=false muss über den Produktivpfad batch_compare
    wirken: ein reiner Groß-/Kleinschreibungsunterschied darf dann kein
    Delta mehr ergeben."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Die Rechnung wurde versendet.")
    _write_single_page_pdf(cnd_path, "die rechnung wurde versendet.")

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(version="1.0", case_sensitive=False)

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is False
    assert pair.compare_result.deltas == []


def test_batch_compare_mit_profile_normalize_whitespace_end_to_end(tmp_path):
    """normalize_whitespace=true muss über den Produktivpfad batch_compare
    wirken: ein reiner Leerzeichen-Trennfehler darf dann kein Delta mehr
    ergeben."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Die Vertragsbedingungen gelten sofort.")
    _write_single_page_pdf(cnd_path, "Die Vertrags bedingungen gelten sofort.")

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(version="1.0", normalize_whitespace=True)

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is False


def test_batch_compare_reicht_text_extraction_reconstruct_durch(monkeypatch, local_filelist):
    """Verdrahtungstest: profile.text_extraction muss bei batch_compare über
    extract_pages_for_profile ankommen (als Attribut des übergebenen
    profile-Objekts), nicht nur im Profil geladen/validiert werden."""
    from engine.pdf_extractor import extract_pages_for_profile as real_extract

    seen_profiles = []

    def fake_extract(pdf_path, profile, role="reference", warnings=None):
        seen_profiles.append(profile)
        return real_extract(pdf_path, profile, role=role, warnings=warnings)

    import engine.batch_processor as batch_processor_module

    monkeypatch.setattr(batch_processor_module, "extract_pages_for_profile", fake_extract)

    profile = Profile(version="1.0", text_extraction="reconstruct")
    result = batch_compare(local_filelist("TC-B-001", 10), profile=profile)

    assert result.ok_count == 10
    assert len(seen_profiles) == 20
    assert all(p.text_extraction == "reconstruct" for p in seen_profiles)


def test_batch_compare_mit_ocr_mode_reference_force_end_to_end(tmp_path):
    """ocr.mode_reference="force" muss über den Produktivpfad batch_compare
    wirken: die Referenz ist ein Scan-PDF (kein nativer Text), der Kandidat
    enthält denselben Text nativ - der OCR-gelesene Referenztext muss mit
    dem nativen Kandidatentext übereinstimmen, sodass kein Delta entsteht."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_image_pdf(ref_path, "Tesseract OCR Pruefung")
    _write_single_page_pdf(cnd_path, "Tesseract OCR Pruefung")

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(
        version="1.0",
        ocr=OcrConfig(enabled=True, mode_reference="force", mode_candidate="off", dpi=300),
    )

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is False


def test_batch_compare_mit_profile_exclude_region_page_from_end_to_end(tmp_path):
    """exclude_regions mit page_from muss über den Produktivpfad batch_compare
    wirken: ein Kopfbereich, der sich ab Seite 2 unterscheidet, wird ab
    dort ausgeschlossen - der Unterschied auf Seite 1 bleibt als Delta
    erhalten."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"

    c = canvas.Canvas(str(ref_path))
    for n in (1, 2, 3):
        c.drawString(30, 750, f"Ref-Header Seite {n}")
        c.drawString(30, 400, f"Body Seite {n} unveraendert.")
        c.showPage()
    c.save()

    c = canvas.Canvas(str(cnd_path))
    for n in (1, 2, 3):
        c.drawString(30, 750, f"Cnd-Header Seite {n}")
        c.drawString(30, 400, f"Body Seite {n} unveraendert.")
        c.showPage()
    c.save()

    filelist_path = tmp_path / "filelist.csv"
    filelist_path.write_text(f"{ref_path},{cnd_path}\n", encoding="utf-8")

    profile = Profile(
        version="1.0",
        exclude_regions=[ExcludeRegion(page_from=2, x=0, y=0, width=250, height=80)],
    )

    result = batch_compare(filelist_path, profile=profile)

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.status == "ok"
    assert pair.compare_result.has_delta is True
    assert {delta.page for delta in pair.compare_result.deltas} == {1}


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
