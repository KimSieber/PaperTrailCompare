# file:    engine/comparison.py
# purpose: Shared comparison logic used by both CLI single comparison
#          (__main__._run_compare) and batch processing
#          (batch_processor._compare_pair). Single source of truth for
#          the extraction→compare→merge→sort pipeline.
# author:  Kim Sieber
# created: 2026-08-17
# changed: 2026-08-17

"""Extraktion→Vergleich→Merge→Sortierung als gemeinsame Pipeline.

`_run_compare()` (Einzelvergleich, CLI) und `_compare_pair()`
(Batch-Verarbeitung) führten bisher identische Schritte redundant aus
(Code-Review-Finding B12, Rule 2 - Redundanz). `run_comparison()` fasst diese
Schritte zusammen; beide Aufrufer bleiben für Datei-Existenzprüfung,
Fehlerbehandlung (siehe B11), Report-Erzeugung und Ausgabeformat zuständig -
diese Aspekte unterscheiden sich zwischen CLI und Batch und gehören daher
NICHT in diese Funktion.
"""
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import List, Optional

from engine.compare_region_comparator import merge_compare_region_comparison
from engine.pdf_extractor import extract_pages_for_profile
from engine.profile_loader import Profile
from engine.text_comparator import CompareResult, compare


@dataclass
class ComparisonOutput:
    """Ergebnis eines einzelnen Ref/Cnd-Vergleichs inkl. aller Metadaten,
    die sowohl CLI- als auch Batch-Aufrufer benötigen."""
    result: CompareResult
    total_pages: int
    ref_ocr_used: bool
    cnd_ocr_used: bool
    region_warnings: List[str]
    duration_seconds: float


def run_comparison(
    ref_path: str,
    cnd_path: str,
    profile: Optional[Profile],
) -> ComparisonOutput:
    """Führt die Extraktion→Vergleich→Merge→Sortierung für ein Ref/Cnd-Paar
    aus. Prüft NICHT die Dateiexistenz, fängt KEINE Exceptions, erzeugt
    KEINE Reports und gibt KEINE Warnungen aus - das bleibt Sache des
    jeweiligen Aufrufers (CLI: `__main__._run_compare`, Batch:
    `batch_processor._compare_pair`)."""
    region_warnings: List[str] = []
    start = time.perf_counter()

    ref_pages, ref_ocr_used, ref_tr_texts = extract_pages_for_profile(
        ref_path, profile, role="reference", warnings=region_warnings
    )
    cnd_pages, cnd_ocr_used, cnd_tr_texts = extract_pages_for_profile(
        cnd_path, profile, role="candidate", warnings=region_warnings
    )

    result = compare(
        ref_pages, cnd_pages,
        case_sensitive=profile.case_sensitive if profile else True,
        normalize_whitespace=profile.normalize_whitespace if profile else False,
        ocr_used=ref_ocr_used or cnd_ocr_used,
        compare_mode=profile.compare_mode if profile else "words",
        merge_hyphenation=profile.merge_hyphenation if profile else True,
        normalize_orphan_hyphens=profile.normalize_orphan_hyphens if profile else True,
    )
    # compare_region_texts (3. Rückgabewert von extract_pages_for_profile) wurde
    # bereits aus ref_pages/cnd_pages herausgefiltert (siehe
    # pdf_extractor.separate_compare_region_blocks) - hier fließen die
    # zugehörigen Multiset-Deltas zusätzlich in has_delta/deltas ein (siehe
    # docs/prompt_table_regions.md, Step 4).
    compare_region_deltas = merge_compare_region_comparison(ref_tr_texts, cnd_tr_texts, profile)
    if compare_region_deltas:
        result = dataclasses.replace(
            result,
            deltas=result.deltas + compare_region_deltas,
            has_delta=True,
        )
    # Stabil NUR nach Seite sortieren (siehe docs/prompt_compare_regions_mode.md,
    # Task 3): compare_region-Deltas wurden bisher immer ans Ende angehängt, egal
    # zu welcher Seite sie gehören (siehe oben) - eine Seite-1-Region-Delta
    # erschien so hinter Seite-17-Deltas und wurde von Testern übersehen.
    # Bewusst KEIN sekundärer Sortierschlüssel auf position: Region-interne
    # Positionen haben einen anderen Bezugsrahmen als Dokumentpositionen, und
    # bei Spalten/Tabellen/Querformat entspricht die Lesereihenfolge ohnehin
    # nicht dem visuellen Eindruck im Viewer. Pythons sort ist stabil, die
    # ursprüngliche Generierungsreihenfolge innerhalb einer Seite bleibt also
    # erhalten.
    result = dataclasses.replace(result, deltas=sorted(result.deltas, key=lambda d: d.page))
    duration_seconds = time.perf_counter() - start
    total_pages = max(len(ref_pages), len(cnd_pages))

    return ComparisonOutput(
        result=result,
        total_pages=total_pages,
        ref_ocr_used=ref_ocr_used,
        cnd_ocr_used=cnd_ocr_used,
        region_warnings=region_warnings,
        duration_seconds=duration_seconds,
    )
