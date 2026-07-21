import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import { MainPanel } from "../layout/MainPanel";
import type { CompareResult } from "../types";

interface FilePickerRowProps {
  label: string;
  path: string;
  onPick: () => void;
}

function FilePickerRow({ label, path, onPick }: FilePickerRowProps) {
  return (
    <div className="flex items-center gap-4">
      <span className="w-28 shrink-0 text-sm font-medium text-slate-700">{label}</span>
      <span className="flex-1 truncate rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        {path || "Keine Datei ausgewählt"}
      </span>
      <button
        type="button"
        onClick={onPick}
        className="shrink-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        Durchsuchen…
      </button>
    </div>
  );
}

export function SingleComparisonView() {
  const [refPath, setRefPath] = useState("");
  const [cndPath, setCndPath] = useState("");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function pickFile(onPicked: (path: string) => void) {
    const path = await open({
      multiple: false,
      directory: false,
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (typeof path === "string") {
      onPicked(path);
    }
  }

  async function handleCompare() {
    setError("");
    setResult(null);
    setLoading(true);
    try {
      // Ruft die Python Core Engine als Sidecar-Prozess auf (lokales IPC
      // über Tauri-Commands, kein Netzwerk-Socket).
      const compareResult = await invoke<CompareResult>("compare_documents", {
        refPath,
        cndPath,
      });
      setResult(compareResult);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenReport() {
    if (!result?.report_path) {
      return;
    }
    try {
      await openPath(result.report_path);
    } catch (err) {
      setError(String(err));
    }
  }

  const canCompare = refPath !== "" && cndPath !== "" && !loading;

  return (
    <MainPanel
      title="Einzelvergleich"
      description="Referenz- und Kandidat-PDF auswählen und textlich vergleichen."
    >
      <div className="max-w-2xl space-y-6">
        <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
          <FilePickerRow
            label="Referenz"
            path={refPath}
            onPick={() => pickFile(setRefPath)}
          />
          <FilePickerRow
            label="Kandidat"
            path={cndPath}
            onPick={() => pickFile(setCndPath)}
          />

          <button
            type="button"
            onClick={handleCompare}
            disabled={!canCompare}
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

        {result && (
          <div className="flex items-center gap-3">
            <span
              className={[
                "inline-flex items-center rounded-full px-3 py-1 text-sm font-medium",
                result.has_delta
                  ? "bg-red-100 text-red-800"
                  : "bg-emerald-100 text-emerald-800",
              ].join(" ")}
            >
              {result.has_delta
                ? `${result.deltas.length} Delta(s) gefunden`
                : "Keine Deltas"}
            </span>

            {result.report_path && (
              <button
                type="button"
                onClick={handleOpenReport}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Vergleichs-PDF öffnen
              </button>
            )}
          </div>
        )}
      </div>
    </MainPanel>
  );
}
