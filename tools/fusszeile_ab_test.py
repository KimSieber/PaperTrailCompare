# file:    tools/ocr_feasibility_probe.py
# purpose: Feasibility probe comparing native text extraction against
#          Tesseract OCR output on individual PDF pages to evaluate OCR
#          quality for specific document types.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

# file:    tools/fusszeile_ab_test.py
# purpose: Diagnostic script for analyzing footer text block positions
#          across multiple PDF pages to determine exclude-region coordinates.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Vergleich Lauf 1 (nur normalize_whitespace) vs. Lauf 2 (mit
Fusszeilen-/Randmarken-Ausschluss profiles/test_fusszeile.json) auf den
TC_REAL-Dateien.

Nur ein Messskript, keine Aenderung an engine/. Nicht Teil der
Produktionslogik oder der Testsuite.

Aufruf: .venv/bin/python tools/fusszeile_ab_test.py
"""

import time
from pathlib import Path

from engine.pdf_extractor import extract_pages_for_profile
from engine.profile_loader import load_profile
from engine.text_comparator import compare

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "TC_REAL"
REF_PDF = FIXTURES / "EBR.PY.E300PY10.WUBP.20260622142440.B001_WEP000000228397609_514.pdf"
CND_PDF = FIXTURES / "DISAP500_50047699491_O_4099749_SV-ST_2026.06.22_14_53_01_WEMB00000228397814_1.pdf"

PROFILES = {
    "Lauf 1 (nur normalize_whitespace)": "profiles/test_whitespace.json",
    "Lauf 2 (+ Fusszeilen/Randmarken-Ausschluss)": "profiles/test_fusszeile.json",
}


def main():
    """Vergleicht REF_PDF/CND_PDF einmal je Profil aus PROFILES und druckt
    Laufzeit, Delta-Anzahl, Tabellenseiten-Warnungen sowie eine Stichprobe
    der ersten 5 Deltas - A/B-Vergleich, ob der Fußzeilen-/Randmarken-
    Ausschluss (profiles/test_fusszeile.json) die Delta-Anzahl gegenüber
    reinem normalize_whitespace reduziert."""
    print(f"Referenz: {REF_PDF.name}")
    print(f"Kandidat: {CND_PDF.name}\n")

    for label, profile_path in PROFILES.items():
        profile = load_profile(profile_path)
        warnings = []

        t0 = time.perf_counter()
        ref_pages, ref_ocr_used = extract_pages_for_profile(str(REF_PDF), profile, role="reference", warnings=warnings)
        cnd_pages, cnd_ocr_used = extract_pages_for_profile(str(CND_PDF), profile, role="candidate", warnings=warnings)
        result = compare(
            ref_pages, cnd_pages,
            case_sensitive=profile.case_sensitive,
            normalize_whitespace=profile.normalize_whitespace,
            ocr_used=ref_ocr_used or cnd_ocr_used,
        )
        elapsed = time.perf_counter() - t0

        print("=" * 78)
        print(f"{label}  ({profile_path})")
        print("=" * 78)
        print(f"  Laufzeit gesamt: {elapsed:.2f}s")
        print(f"  Anzahl Deltas: {len(result.deltas)}")
        print(f"  Tabellenseiten-Warnungen: {len(warnings)}")
        for w in warnings:
            print(f"    - {w}")

        sample = result.deltas[:5]
        print(f"  Stichprobe (erste {len(sample)} von {len(result.deltas)}):")
        for i, d in enumerate(sample, start=1):
            print(f"    [{i}] Seite {d.page} Position {d.position}")
            print(f"        ref: {d.ref_text!r}")
            print(f"        cnd: {d.cnd_text!r}")
        print()


if __name__ == "__main__":
    main()
