export type ViewKey = "single" | "batch" | "settings";

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
