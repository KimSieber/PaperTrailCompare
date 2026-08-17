# file:    tests/test_comparison.py
# purpose: Unit tests for engine.comparison.run_comparison() - the shared
#          extraction→compare→merge→sort pipeline used by both the CLI
#          single comparison and batch processing.
# author:  Kim Sieber
# created: 2026-08-17
# changed: 2026-08-17

"""Testet engine.comparison.run_comparison() isoliert von den beiden
Aufrufern (engine.__main__._run_compare, engine.batch_processor._compare_pair),
die diese Pipeline seit docs/prompt_B11_B12_shared_comparison.md
(Code-Review-Finding B12) gemeinsam nutzen.
"""
from pathlib import Path

from reportlab.pdfgen import canvas

from engine.comparison import run_comparison
from engine.profile_loader import Profile


def _write_single_page_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.save()


def test_run_comparison_identical_pdfs_no_delta(tmp_path):
    """Basis-Smoke-Test: identische PDFs -> kein Delta."""
    ref = tmp_path / "ref.pdf"
    cnd = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref, "Hallo Welt")
    _write_single_page_pdf(cnd, "Hallo Welt")

    output = run_comparison(str(ref), str(cnd), None)

    assert output.result.has_delta is False
    assert output.total_pages == 1
    assert output.duration_seconds > 0


def test_run_comparison_different_pdfs_has_delta(tmp_path):
    """Unterschiedlicher Inhalt -> Delta wird erkannt."""
    ref = tmp_path / "ref.pdf"
    cnd = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref, "Hallo Welt")
    _write_single_page_pdf(cnd, "Hallo Mond")

    output = run_comparison(str(ref), str(cnd), None)

    assert output.result.has_delta is True


def test_run_comparison_with_profile(tmp_path):
    """Profil-Parameter (case_sensitive) werden korrekt durchgereicht."""
    ref = tmp_path / "ref.pdf"
    cnd = tmp_path / "cnd.pdf"
    _write_single_page_pdf(ref, "ABC")
    _write_single_page_pdf(cnd, "abc")

    profile = Profile(version="1.0", case_sensitive=False)
    output_case_insensitive = run_comparison(str(ref), str(cnd), profile)
    assert output_case_insensitive.result.has_delta is False

    output_default = run_comparison(str(ref), str(cnd), None)
    assert output_default.result.has_delta is True
