/**
 * @file    src/views/BatchView.tsx
 * @purpose Batch comparison view. Manages CSV file list selection, live
 *          progress display via Tauri events, and batch result summary
 *          with per-pair status and report access.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import { MainPanel } from "../layout/MainPanel";
import { FilePickerRow } from "../components/FilePickerRow";
import { MiddleTruncate } from "../components/MiddleTruncate";
import { ProfileSelect } from "../components/ProfileSelect";
import { useDragDropTarget } from "../hooks/useDragDropTarget";
import type { BatchOutput, BatchPairResult, BatchProgressEvent } from "../types";

type DropTarget = "csv" | "outputDir";

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/** Erzeugt einen Zeitstempel im Format YYYY-MM-DD_HH-MM-SS für die
 * Ausgabeverzeichnis-Vorbelegung. */
function nowTimestamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
}

export function BatchView() {
  const [csvPath, setCsvPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [isCustomDir, setIsCustomDir] = useState(false);
  const [profileName, setProfileName] = useState("");
  const [rows, setRows] = useState<BatchPairResult[]>([]);
  const [progress, setProgress] = useState({ index: 0, total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [doneResult, setDoneResult] = useState<BatchOutput | null>(null);
  const [cancelled, setCancelled] = useState(false);
  // Live-Flag für die catch-Auswertung in handleStart: `cancelled` (State)
  // ist in der zum Startzeitpunkt erzeugten Closure "eingefroren" und würde
  // dort nicht die Aktualisierung durch handleCancel sehen - der Ref liest
  // dagegen immer den aktuellen Wert.
  const cancelledRef = useRef(false);

  // Wird bei jedem frischen Mount (auch Tab-Wechsel) neu geladen - analog zu
  // SingleComparisonView (siehe get_default_output_dir).
  useEffect(() => {
    invoke<string>("get_default_output_dir")
      .then(setOutputDir)
      .catch(() => {});
  }, []);

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
        setIsCustomDir(true);
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
      setIsCustomDir(true);
    }
  }

  async function handleStart() {
    setError("");
    setRows([]);
    setProgress({ index: 0, total: 0 });
    setDoneResult(null);
    setCancelled(false);
    cancelledRef.current = false;
    setLoading(true);

    const unlisten = await listen<BatchProgressEvent>("batch-progress", (event) => {
      const { index, total, pair } = event.payload;
      setProgress({ index, total });
      setRows((prev) => [...prev, pair]);
    });

    try {
      const effectiveOutputDir = isCustomDir
        ? outputDir
        : `${outputDir}/${nowTimestamp()}`;
      const output = await invoke<BatchOutput>("start_batch_compare", {
        filelistPath: csvPath,
        outputDir: effectiveOutputDir,
        profileName: profileName || undefined,
      });
      setDoneResult(output);
    } catch (err) {
      // Wird der Sidecar per cancel_batch gekillt, schlägt der Aufruf hier
      // ebenfalls fehl (siehe start_batch_compare) - das ist dann kein
      // echter Fehler, sondern der erwartete Abbruch (siehe cancelled-Flag,
      // gesetzt in handleCancel).
      if (!cancelledRef.current) {
        setError(String(err));
      }
    } finally {
      unlisten();
      setLoading(false);
    }
  }

  async function handleCancel() {
    setCancelled(true);
    cancelledRef.current = true;
    try {
      await invoke("cancel_batch");
    } catch (err) {
      setError(String(err));
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
          <ProfileSelect value={profileName} onChange={setProfileName} persistMode="batch" />
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

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleStart}
              disabled={!canStart}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Vergleiche…" : "Vergleichen"}
            </button>
            {loading && (
              <button
                type="button"
                onClick={handleCancel}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
              >
                Abbrechen
              </button>
            )}
          </div>
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

            {/* Feste Höhe für genau 6 sichtbare Zeilen (Kopfzeile 32px +
                6 × 36px Datenzeile ≈ 248px zzgl. 2px Rahmen), unabhängig von
                der Fensterhöhe - bei weniger Zeilen schrumpft der Container
                auf die tatsächliche Inhaltshöhe, da max-height statt height
                gesetzt ist. */}
            <div className="max-h-[250px] overflow-y-auto rounded-md border border-slate-200">
              <table className="w-full table-fixed text-sm">
                <colgroup>
                  <col className="w-[42%]" />
                  <col className="w-[42%]" />
                  <col className="w-[16%]" />
                </colgroup>
                <thead className="sticky top-0 bg-slate-50 text-left text-xs font-medium text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Referenz</th>
                    <th className="px-3 py-2">Kandidat</th>
                    <th className="px-3 py-2">Deltas</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((pair, index) => {
                    const isError = pair.status === "error";
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
                          <td className="overflow-hidden px-3 py-2">
                            <MiddleTruncate text={`Fehler: ${pair.error}`} tailLength={16} />
                          </td>
                        ) : (
                          <td className="px-3 py-2">{pair.compare_result?.deltas.length ?? "—"}</td>
                        )}
                      </tr>
                    );
                  })}
                  {cancelled && !loading && (
                    <tr className="bg-red-50 text-red-800">
                      <td className="px-3 py-2 text-center font-medium" colSpan={3}>
                        Abbruch
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {cancelled && !loading && (
          <p className="text-sm font-medium text-red-700">
            Batch abgebrochen nach {rows.length} von {progress.total} Paaren
          </p>
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
