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

from reportlab.pdfgen import canvas

from engine.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures"


def _write_single_page_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.save()


def test_compare_json_ohne_delta(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is False
    assert payload["deltas"] == []


def test_compare_json_mit_deltas(capsys):
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_delta"] is True
    assert len(payload["deltas"]) == 3
    delta = payload["deltas"][0]
    assert set(delta.keys()) == {"page", "position", "ref_text", "cnd_text"}


def test_compare_ohne_json_flag_liefert_lesbare_zusammenfassung(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path)])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "Kein Delta gefunden."


def test_compare_ohne_json_flag_zeigt_delta_anzahl(capsys):
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path)])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "3 Delta(s) gefunden."


def test_compare_mit_fehlender_datei_liefert_fehler_und_exit_code(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "does-not-exist.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert "does-not-exist.pdf" in captured.err


def test_compare_mit_report_flag_erzeugt_pdf_und_json_feld(tmp_path, capsys):
    ref_path = FIXTURES / "TC-R-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-R-001" / "cnd.pdf"
    report_path = tmp_path / "report.pdf"

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--report", str(report_path), "--json"]
    )

    assert exit_code == 0
    assert report_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_path"] == str(report_path)


def test_compare_mit_ungueltigem_report_pfad_liefert_fehler_und_exit_code(tmp_path, capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"
    # Elternverzeichnis des Report-Pfads ist eine Datei statt eines Ordners
    # -> generate_report() kann das Verzeichnis nicht anlegen und wirft.
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("x")
    report_path = blocker / "report.pdf"

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--report", str(report_path), "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err != ""


def test_compare_ohne_report_flag_kein_report_path_im_json(capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"

    exit_code = main(["compare", str(ref_path), str(cnd_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "report_path" not in payload


def test_compare_mit_report_ohne_json_zeigt_pfad_in_zusammenfassung(tmp_path, capsys):
    ref_path = FIXTURES / "TC-T-001" / "ref.pdf"
    cnd_path = FIXTURES / "TC-T-001" / "cnd.pdf"
    report_path = tmp_path / "report.pdf"

    exit_code = main(
        ["compare", str(ref_path), str(cnd_path), "--report", str(report_path)]
    )

    assert exit_code == 0
    assert report_path.exists()
    assert str(report_path) in capsys.readouterr().out


def test_compare_mit_profile_flag_normalize_whitespace_unterdrueckt_delta(tmp_path, capsys):
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


def test_compare_mit_ungueltigem_profile_liefert_fehler_und_exit_code(tmp_path, capsys):
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


def test_version_flag(capsys):
    exit_code = main(["--version"])

    assert exit_code == 0
    assert "papertrail-engine" in capsys.readouterr().out


def test_ohne_argumente_zeigt_hilfe(capsys):
    exit_code = main([])

    assert exit_code == 0
    assert "usage" in capsys.readouterr().out.lower()
