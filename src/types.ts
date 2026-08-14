/**
 * @file    src/types.ts
 * @purpose Shared TypeScript type definitions mirroring the Rust/Python data
 *          models (Delta, CompareResult, BatchPairResult, etc.). Profile
 *          selection works with plain filename strings (see SettingsView,
 *          SingleComparisonView, BatchView) - no dedicated type needed.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

export type ViewKey = "single" | "batch" | "settings";

/** Entspricht 1:1 der JSON-Ausgabe von `engine --version` (engine/__main__.py)
 * bzw. dem Rust EngineInfo-Struct des engine_version-Commands. */
export interface EngineInfo {
  version: string;
  expiry: string;
  expired: boolean;
}

/** Entspricht 1:1 engine.text_comparator.Delta / src-tauri Delta-Struct. */
export interface Delta {
  page: number;
  position: number;
  ref_text: string;
  cnd_text: string;
}

/** Entspricht 1:1 engine.text_comparator.CompareResult / src-tauri CompareOutput-Struct. */
export interface CompareResult {
  has_delta: boolean;
  deltas: Delta[];
  report_path: string | null;
}

/** Entspricht 1:1 engine.models.PairResult / src-tauri BatchPairResult-Struct. */
export interface BatchPairResult {
  ref_path: string;
  cnd_path: string;
  status: "ok" | "error";
  compare_result: { has_delta: boolean; deltas: Delta[]; ocr_was_used: boolean } | null;
  error: string | null;
  total_pages: number | null;
}

/** Payload des "batch-progress"-Events (src-tauri BatchProgressEvent-Struct). */
export interface BatchProgressEvent {
  index: number;
  total: number;
  pair: BatchPairResult;
}

/** Rückgabewert von start_batch_compare nach Abschluss des Batch-Laufs. */
export interface BatchOutput {
  ok_count: number;
  error_count: number;
  report_path: string;
}
