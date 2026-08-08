# file:    tools/ocr_mode_ab_test.py
# purpose: A/B test comparing delta counts between different OCR mode
#          configurations (off/fallback/force) on real document pairs.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Entscheidungsmessung: native Extraktion vs. OCR-Force für Referenz/
Kandidat auf den TC_REAL-Dateien, mit dem neuen ocr.mode_reference/
mode_candidate.

Nur ein Messskript, keine Aenderung an engine/. Nicht Teil der
Produktionslogik oder der Testsuite.

Lauf A: beide nativ (heutiges Verhalten)
Lauf B: Referenz per OCR (force), Kandidat nativ
Lauf C: beide per OCR (force) - nur zur Einordnung

Aufruf: .venv/bin/python tools/ocr_mode_ab_test.py
"""

import time
from pathlib import Path

from engine.pdf_extractor import extract_pages_for_profile
from engine.profile_loader import OcrConfig, Profile
from engine.text_comparator import compare

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "TC_REAL"
REF_PDF = FIXTURES / "EBR.PY.E300PY10.WUBP.20260622142440.B001_WEP000000228397609_514.pdf"
CND_PDF = FIXTURES / "DISAP500_50047699491_O_4099749_SV-ST_2026.06.22_14_53_01_WEMB00000228397814_1.pdf"

RUNS = {
    "A (beide nativ)": OcrConfig(mode_reference="off", mode_candidate="off", dpi=200),
    "B (Referenz OCR, Kandidat nativ)": OcrConfig(mode_reference="force", mode_candidate="off", dpi=200),
    "C (beide OCR)": OcrConfig(mode_reference="force", mode_candidate="force", dpi=200),
}


def main():
    print(f"Referenz: {REF_PDF.name}")
    print(f"Kandidat: {CND_PDF.name}\n")

    for label, ocr in RUNS.items():
        profile = Profile(version="1.0", normalize_whitespace=True, ocr=ocr)

        t0 = time.perf_counter()
        ref_pages, ref_ocr_used = extract_pages_for_profile(str(REF_PDF), profile, role="reference")
        cnd_pages, cnd_ocr_used = extract_pages_for_profile(str(CND_PDF), profile, role="candidate")
        result = compare(
            ref_pages, cnd_pages,
            case_sensitive=profile.case_sensitive,
            normalize_whitespace=profile.normalize_whitespace,
            ocr_used=ref_ocr_used or cnd_ocr_used,
        )
        elapsed = time.perf_counter() - t0

        print("=" * 78)
        print(f"Lauf {label}")
        print("=" * 78)
        print(f"  ref_ocr_used={ref_ocr_used} cnd_ocr_used={cnd_ocr_used}")
        print(f"  Laufzeit gesamt: {elapsed:.1f}s")
        print(f"  Anzahl Deltas: {len(result.deltas)}")

        sample = result.deltas[:5]
        print(f"  Stichprobe (erste {len(sample)} von {len(result.deltas)}):")
        for i, d in enumerate(sample, start=1):
            print(f"    [{i}] Seite {d.page} Position {d.position}")
            print(f"        ref: {d.ref_text!r}")
            print(f"        cnd: {d.cnd_text!r}")
        print()


if __name__ == "__main__":
    main()
