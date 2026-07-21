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

from engine.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures"


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


def test_version_flag(capsys):
    exit_code = main(["--version"])

    assert exit_code == 0
    assert "papertrail-engine" in capsys.readouterr().out


def test_ohne_argumente_zeigt_hilfe(capsys):
    exit_code = main([])

    assert exit_code == 0
    assert "usage" in capsys.readouterr().out.lower()
