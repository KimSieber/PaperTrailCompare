# file:    tests/test_main.py
# purpose: Tests for the CLI entry point engine/__main__.py. Verifies JSON
#          output, exit codes, profile handling, role-based extraction, and
#          end-to-end exclude-region wiring.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09
# 
"""Testfälle für den `compare`-Unterbefehl des CLI-Einstiegspunkts engine/__main__.py.

Der Sidecar-Prozess (Architekturentscheidung #1) wird von der Tauri-Shell über
`papertrail-engine compare <ref.pdf> <cnd.pdf> --json` angesteuert; die
JSON-Ausgabe muss 1:1 die Felder von text_comparator.CompareResult/Delta
abbilden, damit die Rust-Seite ohne Übersetzungsschicht deserialisieren kann.

Ruft main() direkt per Import auf statt über subprocess: main() gibt den
Exit-Code bereits als Rückgabewert zurück (sys.exit() passiert erst im
__main__-Guard), daher lässt sich das CLI-Verhalten inkl. Exit-Codes und
stderr-Ausgabe ohne Prozess-Isolation testen – subprocess-Aufrufe würden von
coverage.py im Kindprozess nicht erfasst (0 % Coverage trotz grüner Tests).

Fixtures: tests/fixtures/TC-T-001 (kein Delta), tests/fixtures/TC-R-001
(3 Deltas auf 2 Seiten).
"""
import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engine import __expiry__, __version__
from engine.__main__ import main

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


def test_compare_json_without_delta(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_json_with_deltas(capsys):
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is True
    assert len(payload["deltas"]) == 3
    delta = payload["deltas"][0]
    assert set(delta.keys()) == {"page", "position", "ref_text", "cnd_text"}


def test_compare_without_json_flag_returns_readable_summary(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path)])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "Kein Delta gefunden."


def test_compare_without_json_flag_shows_delta_count(capsys):
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path)])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "3 Delta(s) gefunden."


def test_compare_with_missing_file_returns_error_and_exit_code(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "does-not-exist.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "does-not-exist.pdf" in captured.err


def test_compare_with_output_dir_generates_pdf_and_json_field(tmp_path, capsys):
    """PTC-S7 Task B: --output-dir statt --report - die Engine baut den
    Dateinamen selbst (build_comparison_report_filename), Rust/Aufrufer
    übergeben nur noch das Zielverzeichnis."""
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--output-dir", str(tmp_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    report_path = Path(payload["report_path"])
    assert report_path.exists()
    assert report_path.parent == tmp_path
    assert report_path.name.startswith("PTC-Vergleich_")
    assert report_path.name.endswith("_ref_cnd.pdf")


def test_compare_with_invalid_output_dir_returns_error_and_exit_code(tmp_path, capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"
    # output-dir zeigt auf eine Datei statt einen Ordner -> generate_report()
    # kann das Verzeichnis nicht anlegen und wirft.
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("x")
    output_dir = blocker / "reports"

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--output-dir", str(output_dir), "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err != ""


def test_compare_without_output_dir_flag_no_report_path_in_json(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "report_path" not in payload


def test_compare_with_output_dir_without_json_shows_path_in_summary(tmp_path, capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--output-dir", str(tmp_path)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    report_files = list(tmp_path.glob("PTC-Vergleich_*.pdf"))
    assert len(report_files) == 1
    assert str(report_files[0]) in out


def test_compare_with_profile_flag_normalize_whitespace_suppresses_delta(tmp_path, capsys):
    """--profile lädt ein JSON-Profil mit normalize_whitespace=true; ein
    reiner OCR-Wort-Trennfehler darf dann nicht als Delta erscheinen."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Die Vertragsbedingungen gelten sofort.")
    _write_single_page_pdf(cnd_path, "Die Vertrags bedingungen gelten sofort.")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0", "normalize_whitespace": True}), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_with_profile_merge_hyphenation_false_end_to_end(tmp_path, capsys):
    """merge_hyphenation=false must wire through CLI to compare()."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    # ref: "Stück-" und "und ..." auf zwei separaten Zeilen (wie beim
    # Papyrus-Formatierer, der einen visuellen Zeilenumbruch in mehrere
    # Content-Stream-Operationen aufteilt) - PyMuPDF fügt dabei "\n" ein.
    c = canvas.Canvas(str(ref_path))
    c.drawString(72, 720, "Beiträge ohne Stück-")
    c.drawString(72, 708, "und periodenabhängige Kosten")
    c.save()
    _write_single_page_pdf(cnd_path, "Beiträge ohne Stück- und periodenabhängige Kosten")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"version": "1.0", "merge_hyphenation": False}),
        encoding="utf-8",
    )

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False


def test_compare_with_invalid_profile_returns_error_and_exit_code(tmp_path, capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"
    profile_path = tmp_path / "invalid_profile.json"
    profile_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err != ""


def test_compare_calls_extraction_with_correct_role_for_ref_and_cnd(tmp_path, capsys, monkeypatch):
    """ref_pdf muss mit role="reference", cnd_pdf mit role="candidate" an
    extract_pages_for_profile übergeben werden - ein vergessener Default
    würde den Kandidaten sonst fälschlich mit der Referenz-OCR-Einstellung
    lesen (siehe Rückmeldung zum Umsetzungsplan)."""
    from engine.pdf_extractor import extract_pages

    seen_roles = {}

    def fake_extract(pdf_path, profile, role="reference", warnings=None):
        seen_roles[role] = pdf_path
        pages = extract_pages(pdf_path)
        return pages, False, [{} for _ in pages]

    import engine.comparison as comparison_module

    monkeypatch.setattr(comparison_module, "extract_pages_for_profile", fake_extract)

    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    assert seen_roles["reference"] == str(ref_path)
    assert seen_roles["candidate"] == str(cnd_path)


def test_compare_with_profile_exclude_regions_end_to_end_tc_e_001(tmp_path, capsys):
    """TC-E-001 end-to-end über den Produktivpfad (CLI --profile) - genau
    diese Lücke hatte die fehlende Verdrahtung von exclude_regions verdeckt
    (Regionen wurden geladen/validiert/im Report gezählt, wirkten aber
    nicht auf die tatsächliche Extraktion)."""
    ref_path = FIXTURES / "TC-E-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-E-001" / "cnd.pdf"

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [
                {"page": 1, "x": 0, "y": 0, "width": 250, "height": 80},
                {"page": 2, "x": 0, "y": 0, "width": 250, "height": 80},
            ],
        }),
        encoding="utf-8",
    )

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_with_profile_compare_mode_chars_end_to_end(tmp_path, capsys):
    """compare_mode="chars" muss über die CLI wirken: eine fragmentierte
    Wortgrenze in der Referenz darf kein Delta mehr ergeben."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Der Versi ch e ru n gssch u tz gilt.")
    _write_single_page_pdf(cnd_path, "Der Versicherungsschutz gilt.")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0", "compare_mode": "chars"}), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_calls_compare_with_profile_compare_mode(tmp_path, capsys, monkeypatch):
    """Verdrahtungstest: profile.compare_mode muss an text_comparator.compare
    durchgereicht werden, nicht nur geladen/validiert werden (dasselbe
    Muster wie die vorherige Verdrahtungslücke bei exclude_regions)."""
    seen_modes = []

    import engine.comparison as comparison_module
    real_compare = comparison_module.compare

    def spy_compare(*args, **kwargs):
        seen_modes.append(kwargs.get("compare_mode"))
        return real_compare(*args, **kwargs)

    monkeypatch.setattr(comparison_module, "compare", spy_compare)

    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0", "compare_mode": "chars"}), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    assert seen_modes == ["chars"]


def test_compare_with_profile_case_sensitive_false_end_to_end(tmp_path, capsys):
    """case_sensitive=false muss über die CLI wirken: ein reiner
    Groß-/Kleinschreibungsunterschied darf dann kein Delta mehr ergeben."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Die Rechnung wurde versendet.")
    _write_single_page_pdf(cnd_path, "die rechnung wurde versendet.")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0", "case_sensitive": False}), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_without_case_sensitive_false_yields_delta_on_case_difference(tmp_path, capsys):
    """Gegenprobe: ohne case_sensitive=false (Default = True) muss derselbe
    Groß-/Kleinschreibungsunterschied als Delta erkannt werden."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Die Rechnung wurde versendet.")
    _write_single_page_pdf(cnd_path, "die rechnung wurde versendet.")

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is True


def test_compare_with_profile_text_extraction_reconstruct_end_to_end(tmp_path, capsys):
    """text_extraction="reconstruct" muss über die CLI wirken, ohne den
    Vergleich zu verändern, wenn Referenz und Kandidat identisch sind."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref_path, "Der Vertrag gilt ab sofort.")
    _write_single_page_pdf(cnd_path, "Der Vertrag gilt ab sofort.")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0", "text_extraction": "reconstruct"}), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_passes_text_extraction_reconstruct_to_extract_pages_for_profile(tmp_path, capsys, monkeypatch):
    """Verdrahtungstest: profile.text_extraction muss über extract_pages_for_profile
    ankommen (als Attribut des übergebenen profile-Objekts), nicht nur im
    Profil geladen/validiert werden (dasselbe Muster wie die vorherige
    Verdrahtungslücke bei exclude_regions)."""
    from engine.pdf_extractor import extract_pages_for_profile as real_extract

    seen_profiles = []

    def fake_extract(pdf_path, profile, role="reference", warnings=None):
        seen_profiles.append(profile)
        return real_extract(pdf_path, profile, role=role, warnings=warnings)

    import engine.comparison as comparison_module

    monkeypatch.setattr(comparison_module, "extract_pages_for_profile", fake_extract)

    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps({"version": "1.0", "text_extraction": "reconstruct"}), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    assert len(seen_profiles) == 2
    assert all(profile.text_extraction == "reconstruct" for profile in seen_profiles)


def test_compare_with_ocr_mode_reference_force_end_to_end(tmp_path, capsys):
    """ocr.mode_reference="force" muss über die CLI wirken: die Referenz
    ist ein Scan-PDF (kein nativer Text), der Kandidat enthält denselben
    Text nativ - der OCR-gelesene Referenztext muss mit dem nativen
    Kandidatentext übereinstimmen, sodass kein Delta entsteht."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_image_pdf(ref_path, "Tesseract OCR Pruefung")
    _write_single_page_pdf(cnd_path, "Tesseract OCR Pruefung")

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "ocr": {"enabled": True, "mode_reference": "force", "mode_candidate": "off", "dpi": 300},
        }),
        encoding="utf-8",
    )

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False


def test_compare_with_profile_exclude_region_page_zero_end_to_end(tmp_path, capsys):
    """exclude_regions mit page=0 ("alle Seiten") muss über die CLI wirken:
    ein Kopfbereich, der sich auf jeder Seite zwischen ref und cnd
    unterscheidet, darf dann auf keiner Seite als Delta erscheinen."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"

    c = canvas.Canvas(str(ref_path))
    for n in (1, 2):
        c.drawString(30, 750, f"Ref-Header Seite {n}")
        c.drawString(30, 400, f"Body Seite {n} unveraendert.")
        c.showPage()
    c.save()

    c = canvas.Canvas(str(cnd_path))
    for n in (1, 2):
        c.drawString(30, 750, f"Cnd-Header Seite {n}")
        c.drawString(30, 400, f"Body Seite {n} unveraendert.")
        c.showPage()
    c.save()

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({
            "version": "1.0",
            "exclude_regions": [{"page": 0, "x": 0, "y": 0, "width": 250, "height": 80}],
        }),
        encoding="utf-8",
    )

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_batch_json_lines_emits_progress_per_pair_and_final_done_line(tmp_path, capsys, local_filelist):
    """`batch` streamt pro verarbeitetem Paar sofort eine JSON-Zeile auf
    stdout (Grundlage für Live-Progress-Events der Tauri-Shell, siehe
    prompt_batch_verarbeitung.md), gefolgt von einer abschließenden
    'done'-Zeile mit Batch-Report-Pfad."""
    filelist_path = local_filelist("TC-B-001", 10)

    exit_code = main(["batch", str(filelist_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 11

    progress_lines = [json.loads(line) for line in lines[:10]]
    for i, payload in enumerate(progress_lines, start=1):
        assert payload["type"] == "progress"
        assert payload["index"] == i
        assert payload["total"] == 10
        assert payload["pair"]["status"] == "ok"
        assert payload["pair"]["compare_result"]["has_delta"] is False

    done_payload = json.loads(lines[-1])
    assert done_payload["type"] == "done"
    assert done_payload["ok_count"] == 10
    assert done_payload["error_count"] == 0
    report_path = Path(done_payload["report_path"])
    assert report_path.exists()
    assert report_path.parent == tmp_path
    assert report_path.name.startswith("PTC-Batch-Report_")
    # PTC-S7 Task B: der Batch-Report-Dateiname trägt zusätzlich den Stem
    # der CSV-Dateiliste (hier "filelist", siehe local_filelist-Fixture).
    assert report_path.name.endswith(f"_{filelist_path.stem}.pdf")

    # Punkt 1 (prompt_batch_fixes.md): pro Paar zusätzlich ein Einzel-Report
    # flach im selben --output-dir, nicht nur der Batch-Report.
    individual_reports = [p for p in tmp_path.glob("*.pdf") if p != report_path]
    assert len(individual_reports) == 10
    # PTC-S7 Task B, Regel 3: Batch-Report und alle Einzel-Reports teilen
    # sich denselben (Batch-Start-)Zeitstempel. Format des Batch-Reports:
    # "PTC-Batch-Report_{YYYY-MM-DD}_{HH-MM}_{CSVStem}.pdf".
    _, date_part, time_part, _ = report_path.name.split("_", 3)
    batch_timestamp = f"{date_part}_{time_part}"
    assert all(batch_timestamp in p.name for p in individual_reports)


def test_batch_with_missing_file_is_logged_per_pair_tc_b_002(tmp_path, capsys, local_filelist):
    filelist_path = local_filelist("TC-B-002", 5)

    exit_code = main(["batch", str(filelist_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    progress_lines = [json.loads(line) for line in lines[:-1]]
    error_pairs = [p for p in progress_lines if p["pair"]["status"] == "error"]
    assert len(error_pairs) == 1
    assert "doc_03_cnd.pdf" in error_pairs[0]["pair"]["error"]

    done_payload = json.loads(lines[-1])
    assert done_payload["ok_count"] == 4
    assert done_payload["error_count"] == 1


def test_batch_with_invalid_filelist_returns_error_and_exit_code(tmp_path, capsys):
    exit_code = main(["batch", str(tmp_path / "does-not-exist.csv"), "--output-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err != ""


def test_version_flag(capsys):
    exit_code = main(["--version"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == __version__
    assert payload["expiry"] == __expiry__
    assert payload["expired"] is False


def test_without_arguments_shows_help(capsys):
    exit_code = main([])

    assert exit_code == 0
    assert "usage" in capsys.readouterr().out.lower()


# --- compare_regions end-to-end (Sprint PTC-S3 Task C, siehe docs/prompt_table_regions.md, Step 4) ---

_COMPARE_REGION_PROFILE = {
    "version": "1.0",
    "compare_regions": [
        {
            "page": 1, "x": 0, "y": 650, "width": 400, "height": 250,
            "condition": "SV SparkassenVersicherung",
            # mode="unordered" explizit (siehe docs/prompt_compare_regions_mode.md,
            # Task 2): TC-TR-001/002 testen genau das Zeichen-Multiset-Verhalten
            # (Blockreihenfolge irrelevant) - der neue Default "sequential"
            # würde hier zufällig dieselben Assertions erfüllen (die Wortreihenfolge
            # ist in diesen Fixtures ohnehin identisch), aber die Tests würden
            # dann nicht mehr das testen, was ihr Name behauptet.
            "mode": "unordered",
        }
    ],
}


def test_compare_region_eliminates_false_delta_from_differing_block_structure_tc_tr_001(tmp_path, capsys):
    """TC-TR-001: ref.pdf schreibt die Fußzeile als einen breiten Block,
    cnd.pdf als vier schmale, vertikal gestapelte Blöcke - identischer
    Wortinhalt. Ohne compare_region wäre das ein sequenzielles False-Delta
    (reine Wortumstellung); mit korrekt konfigurierter compare_region muss
    has_delta False sein."""
    ref_path = FIXTURES / "TC-TR-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-TR-001" / "cnd.pdf"

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_COMPARE_REGION_PROFILE), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_region_detects_real_change_despite_differing_block_structure_tc_tr_002(tmp_path, capsys):
    """TC-TR-002: wie TC-TR-001, aber die Telefonnummer in der Kandidaten-
    Fußzeile ist tatsächlich geändert ('...-1234' -> '...-5678'). Der
    Whitespace-freie Vergleich muss das als echtes Delta melden - GENAU EIN
    Delta für die gesamte Region (siehe docs/prompt_table_regions_whitespace_free.md),
    mit lesbarem ref_text/cnd_text für den Report."""
    ref_path = FIXTURES / "TC-TR-002" / "ref.pdf"
    cnd_path = FIXTURES / "TC-TR-002" / "cnd.pdf"

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_COMPARE_REGION_PROFILE), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is True
    assert len(payload["deltas"]) == 1
    delta = payload["deltas"][0]
    assert "0800-1234" in delta["ref_text"]
    assert "0800-5678" in delta["cnd_text"]


# --- Delta-Liste seitenweise sortiert (docs/prompt_compare_regions_mode.md, Task 3) ---


def _write_multi_page_pdf(path: Path, page_1_footer: str, body_lines: list[str]) -> None:
    """Seite 1: unveränderter Fließtext + `page_1_footer` (Ziel der
    compare_region). Seiten 2..N: je eine Zeile aus `body_lines` - eine
    Zeile pro Seite, damit sequenzielle Deltas gezielt auf bestimmte
    Seitenzahlen gemappt werden können (siehe Modultests unten)."""
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


_REGION_DELTA_ON_PAGE_1_PROFILE = {
    "version": "1.0",
    "compare_regions": [
        {
            "page": 1, "x": 0, "y": 650, "width": 400, "height": 250,
            "condition": "Footer Alpha",
        }
    ],
}


def test_delta_list_is_sorted_by_page_region_delta_before_later_pages(tmp_path, capsys):
    """Die compare_region-Delta gehört inhaltlich zu Seite 1, wurde bisher
    aber immer ans Ende der Delta-Liste angehängt - hinter alle
    sequenziellen Deltas bis Seite 5. Nach Task 3 muss die fertige
    Delta-Liste stabil nach Seite sortiert sein, sodass die Seite-1-Delta
    VOR den Deltas der Seiten 2-5 erscheint."""
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

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_REGION_DELTA_ON_PAGE_1_PROFILE), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    deltas = payload["deltas"]

    pages = [d["page"] for d in deltas]
    assert pages == sorted(pages), f"Delta-Liste nicht seitenweise sortiert: {pages}"
    assert pages[0] == 1, "compare_region-Delta (Seite 1) muss an erster Stelle stehen"
    assert 2 in pages and 5 in pages


def test_delta_list_sorting_is_stable_within_same_page(tmp_path, capsys):
    """Zwei Deltas auf DERSELBEN Seite müssen ihre ursprüngliche
    Generierungsreihenfolge (Positions-Reihenfolge des sequenziellen
    Vergleichs) behalten - sortiert wird ausschließlich nach Seite
    (`sorted(..., key=lambda d: d.page)`), NICHT zusätzlich nach position
    (siehe docs/prompt_compare_regions_mode.md, Task 3)."""
    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"

    # Seite 2 enthält zwei weit auseinanderliegende geänderte Wörter -> zwei
    # separate sequenzielle Deltas auf derselben Seite, mit aufsteigender
    # Wort-Position.
    ref_body = ["Wort1 Wort2 Wort3 Wort4 Wort5 Wort6 Wort7 Wort8 Wort9 Wort10"]
    cnd_body = ["Wort1 GEAENDERT Wort3 Wort4 Wort5 Wort6 Wort7 Wort8 GEAENDERT2 Wort10"]

    _write_multi_page_pdf(ref_path, "Footer Alpha Beta", ref_body)
    _write_multi_page_pdf(cnd_path, "Footer Alpha Beta", cnd_body)

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_REGION_DELTA_ON_PAGE_1_PROFILE), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    deltas = payload["deltas"]

    page_2_deltas = [d for d in deltas if d["page"] == 2]
    assert len(page_2_deltas) == 2
    positions = [d["position"] for d in page_2_deltas]
    assert positions == sorted(positions), (
        "Deltas derselben Seite müssen in ihrer ursprünglichen "
        f"Generierungsreihenfolge bleiben (Positionen: {positions})"
    )


# --- mode="sequential" end-to-end: Isolation vom Nachbartext (docs/prompt_compare_regions_mode.md, Task 2) ---


def _write_page_with_interleaved_blocks(path: Path, address_lines: list, info_lines: list) -> None:
    """Baut EINE Seite nach, bei der ein Adressblock links und ein
    Absenderinfo-Block rechts auf DERSELBEN Zeilenhöhe stehen (siehe
    docs/prompt_compare_regions_mode.md, Problem-Abschnitt: 'Es betreut Sie'
    rechts oben, Empfängeradresse links) - der normale sequenzielle
    Seiten-Vergleich würde deren Zeilen verschachtelt lesen (Interleaving)
    und bei jeder Änderung im Info-Block auch die unveränderten
    Adresszeilen in die Deltas hineinziehen. Deshalb muss der Info-Block
    per compare_region (mode='sequential') isoliert verglichen werden."""
    c = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    c.setFont("Helvetica", 11)
    y = height - 100
    for address_line, info_line in zip(address_lines, info_lines):
        c.drawString(30, y, address_line)
        c.drawString(350, y, info_line)
        y -= 20
    c.showPage()
    c.save()


_SEQUENTIAL_INFO_BLOCK_PROFILE = {
    "version": "1.0",
    "compare_regions": [
        {
            "page": 1, "x": 330, "y": 0, "width": 265, "height": 200,
            "condition": "Es schreibt Ihnen",
            "mode": "sequential",
        }
    ],
}


def test_compare_region_mode_sequential_isolates_info_block_from_address_block(tmp_path, capsys):
    """Reproduziert das Problem aus docs/prompt_compare_regions_mode.md:
    Adressblock (links) bleibt zwischen ref und cnd unverändert, der
    Info-Block (rechts, 'Es schreibt Ihnen ...' + Telefon + Datum) hat zwei
    echte, kleine Änderungen ('Tel.:' -> 'Tel.', Datum geändert). Mit
    mode='sequential' dürfen NUR diese beiden kleinen Änderungen als Deltas
    erscheinen - insbesondere KEIN Delta, das den unveränderten Adressblock
    enthält (das wäre der alte Interleaving-Bug), und KEIN einzelnes
    Delta, das den gesamten Info-Block als einen Klumpen enthält (das wäre
    mode='unordered')."""
    address_lines = [
        "Frau Erika Mustermann",
        "Musterstrasse 12",
        "65183 Wiesbaden",
    ]
    ref_info_lines = [
        "Es schreibt Ihnen Max Beispiel",
        "Tel.: 0611 178-49830",
        "Wiesbaden, 15.06.2026",
    ]
    cnd_info_lines = [
        "Es schreibt Ihnen Max Beispiel",
        "Tel. 0611 178-49830",
        "Wiesbaden, 03.07.2026",
    ]

    ref_path = tmp_path / "ref.pdf"
    cnd_path = tmp_path / "cnd.pdf"
    _write_page_with_interleaved_blocks(ref_path, address_lines, ref_info_lines)
    _write_page_with_interleaved_blocks(cnd_path, address_lines, cnd_info_lines)

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_SEQUENTIAL_INFO_BLOCK_PROFILE), encoding="utf-8")

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--profile", str(profile_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is True
    deltas = payload["deltas"]

    # Isolation: keine Adresszeile darf in irgendeinem Delta auftauchen.
    for delta in deltas:
        for address_line in address_lines:
            assert address_line not in delta["ref_text"]
            assert address_line not in delta["cnd_text"]

    # Mehrere kleine Deltas statt eines Klumpens für den gesamten Info-Block.
    assert len(deltas) > 1
    full_ref_block = " ".join(ref_info_lines)
    full_cnd_block = " ".join(cnd_info_lines)
    for delta in deltas:
        assert delta["ref_text"] != full_ref_block
        assert delta["cnd_text"] != full_cnd_block
