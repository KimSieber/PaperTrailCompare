/**
 * @file    src/views/SingleComparisonView.tsx
 * @purpose Single document comparison view. Provides drag-and-drop file
 *          selection for reference/candidate PDFs and displays comparison
 *          results with delta details and report links.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import { MainPanel } from "../layout/MainPanel";
import { FilePickerRow } from "../components/FilePickerRow";
import { ProfileSelect } from "../components/ProfileSelect";
import { useDragDropTarget } from "../hooks/useDragDropTarget";
import type { CompareResult } from "../types";

type DropTarget = "reference" | "candidate" | "outputDir";

/** Erzeugt einen Zeitstempel im Format YYYY-MM-DD_HH-MM-SS für die
 * Ausgabeverzeichnis-Vorbelegung. */
function nowTimestamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
}

export function SingleComparisonView() {
  const [refPath, setRefPath] = useState("");
  const [cndPath, setCndPath] = useState("");
  const [profileName, setProfileName] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [isCustomDir, setIsCustomDir] = useState(false);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Wird bei jedem frischen Mount (auch Tab-Wechsel) neu vom heutigen Datum
  // abgeleitet - anders als das Profil wird das Ausgabeverzeichnis bewusst
  // nicht persistiert (siehe Sprint-Doku Block 4c).
  useEffect(() => {
    invoke<string>("get_default_output_dir")
      .then(setOutputDir)
      .catch((err) => setError(String(err)));
  }, []);

  const { activeDropTarget, isDragPending } = useDragDropTarget<DropTarget>({
    isValidPath: (target, path) => target === "outputDir" || path.toLowerCase().endsWith(".pdf"),
    onInvalidDrop: () => setError("Nur PDF-Dateien können per Drag & Drop abgelegt werden."),
    onMultipleDropped: () =>
      setError("Es kann nur eine Datei pro Feld abgelegt werden. Nur die erste Datei wurde übernommen."),
    onDrop: (target, path, wasMultiple) => {
      if (!wasMultiple) {
        setError("");
      }
      if (target === "reference") {
        setRefPath(path);
      } else if (target === "candidate") {
        setCndPath(path);
      } else {
        setOutputDir(path);
        setIsCustomDir(true);
      }
    },
  });

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

  async function pickOutputDir() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path === "string") {
      setOutputDir(path);
      setIsCustomDir(true);
    }
  }

  async function handleCompare() {
    setError("");
    setResult(null);
    setLoading(true);
    try {
      // Ruft die Python Core Engine als Sidecar-Prozess auf (lokales IPC
      // über Tauri-Commands, kein Netzwerk-Socket).
      const effectiveOutputDir = isCustomDir
        ? outputDir
        : `${outputDir}/${nowTimestamp()}`;
      const compareResult = await invoke<CompareResult>("compare_documents", {
        refPath,
        cndPath,
        profileName: profileName || undefined,
        outputDir: effectiveOutputDir || undefined,
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
          <ProfileSelect value={profileName} onChange={setProfileName} persistMode="single" />
          <FilePickerRow
            label="Referenz"
            path={refPath}
            onPick={() => pickFile(setRefPath)}
            dropTarget="reference"
            isDropActive={activeDropTarget === "reference"}
            isDragPending={isDragPending && activeDropTarget === null}
          />
          <FilePickerRow
            label="Kandidat"
            path={cndPath}
            onPick={() => pickFile(setCndPath)}
            dropTarget="candidate"
            isDropActive={activeDropTarget === "candidate"}
            isDragPending={isDragPending && activeDropTarget === null}
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
