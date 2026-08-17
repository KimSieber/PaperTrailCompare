# file:    tools/ocr_feasibility_probe.py
# purpose: Feasibility probe comparing native text extraction against
#          Tesseract OCR output on individual PDF pages to evaluate OCR
#          quality for specific document types.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Machbarkeitsnachweis: OCR (Tesseract/deu) vs. native Textextraktion
auf der Type3-ohne-ToUnicode Referenzdatei aus TC_REAL.

Nur ein Messskript, keine Aenderung an engine/. Nicht Teil der
Produktionslogik oder der Testsuite.

Aufruf: .venv/bin/python tools/ocr_feasibility_probe.py
"""

import time
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image
import io

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "TC_REAL"
REF_PDF = FIXTURES / "EBR.PY.E300PY10.WUBP.20260622142440.B001_WEP000000228397609_514.pdf"

PROBLEM_TERMS = [
    "SparkassenVersicherung",
    "Gebäudeversicherung",
    "Verlässlichkeit",
    "dafür",
]


def render_page(doc, page_no, dpi):
    page = doc[page_no]
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return img


def ocr_page(img, lang="deu"):
    t0 = time.perf_counter()
    text = pytesseract.image_to_string(img, lang=lang)
    elapsed = time.perf_counter() - t0
    return text, elapsed


def report_terms(label, text):
    for term in PROBLEM_TERMS:
        found = term in text
        print(f"    [{label}] {'OK  ' if found else 'FEHL'} '{term}'")


def main():
    print(f"Referenzdatei: {REF_PDF.name}")
    print(f"Existiert: {REF_PDF.exists()}\n")

    doc = pymupdf.open(REF_PDF)
    print(f"Seitenanzahl gesamt: {doc.page_count}\n")

    print("=" * 70)
    print("SCHRITT 2+3: Seite 1 und Seite 4, 300 DPI, deu — nativ vs. OCR")
    print("=" * 70)

    for page_no in (0, 3):
        page = doc[page_no]
        native_text = page.get_text()
        print(f"\n--- Seite {page_no + 1} — nativer Text (Ausschnitt, erste 400 Zeichen) ---")
        print(repr(native_text[:400]))
        report_terms("nativ", native_text)

        img = render_page(doc, page_no, 300)
        ocr_text, elapsed = ocr_page(img, "deu")
        print(f"\n--- Seite {page_no + 1} — OCR-Text @300dpi (Ausschnitt, erste 400 Zeichen), {elapsed:.2f}s ---")
        print(repr(ocr_text[:400]))
        report_terms("ocr", ocr_text)

    print("\n" + "=" * 70)
    print("SCHRITT 4: Laufzeitmessung Rendern+OCR pro Seite (300 DPI, deu)")
    print("=" * 70)
    timings = []
    for page_no in (0, 3):
        t0 = time.perf_counter()
        img = render_page(doc, page_no, 300)
        render_time = time.perf_counter() - t0
        _, ocr_time = ocr_page(img, "deu")
        total = render_time + ocr_time
        timings.append(total)
        print(f"  Seite {page_no + 1}: Rendern={render_time:.2f}s OCR={ocr_time:.2f}s Summe={total:.2f}s")

    avg = sum(timings) / len(timings)
    print(f"\n  Durchschnitt pro Seite: {avg:.2f}s")
    print(f"  Hochgerechnet auf 43 Seiten: {avg * 43:.1f}s (~{avg * 43 / 60:.1f} min)")

    print("\n" + "=" * 70)
    print("SCHRITT 5: DPI-Vergleich an Seite 1 (200 / 300 / 400 dpi)")
    print("=" * 70)
    for dpi in (200, 300, 400):
        t0 = time.perf_counter()
        img = render_page(doc, 0, dpi)
        render_time = time.perf_counter() - t0
        text, ocr_time = ocr_page(img, "deu")
        print(f"\n  DPI={dpi}: Rendern={render_time:.2f}s OCR={ocr_time:.2f}s Summe={render_time+ocr_time:.2f}s")
        report_terms(f"dpi{dpi}", text)

    doc.close()


if __name__ == "__main__":
    main()
