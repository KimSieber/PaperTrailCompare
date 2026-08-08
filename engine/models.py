# file:    engine/models.py
# purpose: Layer-neutral result data models (PairResult, BatchResult) shared
#          by batch_processor and report_generator without cross-imports.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Schichtneutrale Ergebnis-Datenmodelle für Batch-Verarbeitung und Reporting.

Analog zu text_comparator.CompareResult: reine Datenklassen ohne eigene
Schicht-Zugehörigkeit, damit Schicht-3-Module (batch_processor,
report_generator) sie gemeinsam nutzen können, ohne sich gegenseitig zu
importieren.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from engine.text_comparator import CompareResult


@dataclass
class PairResult:
    ref_path: str
    cnd_path: str
    status: str  # "ok" oder "error"
    compare_result: Optional[CompareResult] = None
    error: Optional[str] = None
    # max(Seitenzahl Referenz, Seitenzahl Kandidat) - Grundlage für die
    # Übereinstimmungs-Prozentangabe je Paar in der Batch-GUI (analog zur
    # Zusammenfassungsseite des Einzelvergleich-Reports, siehe
    # report_generator._build_summary_page_pdf_bytes: match_ratio).
    total_pages: Optional[int] = None


@dataclass
class BatchResult:
    pairs: List[PairResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for p in self.pairs if p.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for p in self.pairs if p.status == "error")
