/**
 * @file    src/views/BatchView.tsx
 * @purpose Batch comparison view. Manages CSV file list selection, live
 *          progress display via Tauri events, and batch result summary
 *          with per-pair status and report access.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import { MainPanel } from "../layout/MainPanel";
import { FilePickerRow } from "../components/FilePickerRow";
import { MiddleTruncate } from "../components/MiddleTruncate";
import { useDragDropTarget } from "../hooks/useDragDropTarget";
import type { BatchOutput, BatchPairResult, BatchProgressEvent } from "../types";

type DropTarget = "csv" | "outputDir";

/** Übereinstimmung in % je Paar, analog zur Zusammenfassungsseite des
 * Einzelvergleich-Reports: (Seiten ohne Delta) / (Gesamtseitenzahl). */
function matchPercent(pair: BatchPairResult): number | null {
  if (pair.status !== "ok" || !pair.compare_result || !pair.total_pages) {
    return null;
  }
  const deltaPageCount = new Set(pair.compare_result.deltas.map((d) => d.page)).size;
  const matchRatio = (pair.total_pages - deltaPageCount) / pair.total_pages;
  return Math.round(matchRatio * 100);
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function BatchView() {
  const [csvPath, setCsvPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [rows, setRows] = useState<BatchPairResult[]>([]);
  const [progress, setProgress] = useState({ index: 0, total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [doneResult, setDoneResult] = useState<BatchOutput | null>(null);

  const { activeDropTarget, isDragPending } = useDragDropTarget<DropTarget>({
    isValidPath: (target, path) => target !== "csv" || path.toLowerCase().endsWith(".csv"),
    onInvalidDrop: () => setError("Für die Dateiliste können nur CSV-Dateien per Drag & Drop abgelegt werden."),
    onMultipleDropped: () => setError("Es kann nur ein Pfad pro Feld abgelegt werden. Nur der erste wurde übernommen."),
    onDrop: (target, path, wasMultiple) => {
      if (!wasMultiple) {
        setError("");
      }
      if (target === "csv") {
        setCsvPath(path);
      } else {
        setOutputDir(path);
      }
    },
  });

  async function pickCsv() {
    const path = await open({
      multiple: false,
      directory: false,
      filters: [{ name: "CSV", extensions: ["csv"] }],
    });
    if (typeof path === "string") {
      setCsvPath(path);
    }
  }

  async function pickOutputDir() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path === "string") {
      setOutputDir(path);
    }
  }

  async function handleStart() {
    setError("");
    setRows([]);
    setProgress({ index: 0, total: 0 });
    setDoneResult(null);
    setLoading(true);

    const unlisten = await listen<BatchProgressEvent>("batch-progress", (event) => {
      const { index, total, pair } = event.payload;
      setProgress({ index, total });
      setRows((prev) => [...prev, pair]);
    });

    try {
      const output = await invoke<BatchOutput>("start_batch_compare", {
        filelistPath: csvPath,
        outputDir,
      });
      setDoneResult(output);
    } catch (err) {
      setError(String(err));
    } finally {
      unlisten();
      setLoading(false);
    }
  }

  async function handleOpenReport() {
    if (!doneResult?.report_path) {
      return;
    }
    try {
      await openPath(doneResult.report_path);
    } catch (err) {
      setError(String(err));
    }
  }

  const canStart = csvPath !== "" && outputDir !== "" && !loading;
  const progressPercent = progress.total > 0 ? Math.round((progress.index / progress.total) * 100) : 0;

  return (
    <MainPanel
      title="Batch"
      description="Massenvergleich per Dateiliste (CSV ohne Kopfzeile: Referenzdatei,Kandidatendatei)."
    >
      <div className="max-w-3xl space-y-6">
        <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
          <FilePickerRow
            label="Dateiliste"
            path={csvPath}
            onPick={pickCsv}
            dropTarget="csv"
            isDropActive={activeDropTarget === "csv"}
            isDragPending={isDragPending && activeDropTarget === null}
            placeholder="Keine CSV-Dateiliste ausgewählt"
          />
          <FilePickerRow
            label="Ausgabe"
            path={outputDir}
            onPick={pickOutputDir}
            dropTarget="outputDir"
            isDropActive={activeDropTarget === "outputDir"}
            isDragPending={isDragPending && activeDropTarget === null}
            placeholder="Kein Ausgabeverzeichnis ausgewählt"
          />

          <button
            type="button"
            onClick={handleStart}
            disabled={!canStart}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Vergleiche…" : "Vergleichen"}
          </button>
        </section>

        {error && (
          <p className="text-sm text-red-700">
            Fehler: <code>{error}</code>
          </p>
        )}

        {(loading || rows.length > 0) && (
          <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-5">
            <div className="space-y-1">
              <div className="flex items-center justify-between text-sm text-slate-600">
                <span>
                  {progress.index} von {progress.total}
                </span>
                {doneResult && <span>Fertig</span>}
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-slate-900 transition-all"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            <div className="max-h-96 overflow-y-auto rounded-md border border-slate-200">
              <table className="w-full table-fixed text-sm">
                <colgroup>
                  <col className="w-[38%]" />
                  <col className="w-[38%]" />
                  <col className="w-[12%]" />
                  <col className="w-[12%]" />
                </colgroup>
                <thead className="sticky top-0 bg-slate-50 text-left text-xs font-medium text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Referenz</th>
                    <th className="px-3 py-2">Kandidat</th>
                    <th className="px-3 py-2">Deltas</th>
                    <th className="px-3 py-2">Übereinstimmung</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((pair, index) => {
                    const isError = pair.status === "error";
                    const percent = matchPercent(pair);
                    return (
                      <tr
                        key={`${pair.ref_path}-${pair.cnd_path}-${index}`}
                        className={isError ? "bg-red-50 text-red-800" : "text-slate-700"}
                      >
                        <td className="overflow-hidden px-3 py-2">
                          <MiddleTruncate text={fileName(pair.ref_path)} />
                        </td>
                        <td className="overflow-hidden px-3 py-2">
                          <MiddleTruncate text={fileName(pair.cnd_path)} />
                        </td>
                        {isError ? (
                          <td className="overflow-hidden px-3 py-2" colSpan={2}>
                            <MiddleTruncate text={`Fehler: ${pair.error}`} tailLength={16} />
                          </td>
                        ) : (
                          <>
                            <td className="px-3 py-2">{pair.compare_result?.deltas.length ?? "—"}</td>
                            <td className="px-3 py-2">{percent !== null ? `${percent} %` : "—"}</td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {doneResult && (
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700">
              {doneResult.ok_count} OK · {doneResult.error_count} Fehler
            </span>
            <button
              type="button"
              onClick={handleOpenReport}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Batch-Report öffnen
            </button>
          </div>
        )}
      </div>
    </MainPanel>
  );
}
