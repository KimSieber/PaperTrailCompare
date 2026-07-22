import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { openPath } from "@tauri-apps/plugin-opener";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { MainPanel } from "../layout/MainPanel";
import type { CompareResult } from "../types";

type DropTarget = "reference" | "candidate" | null;

interface FilePickerRowProps {
  label: string;
  path: string;
  onPick: () => void;
  dropTarget: "reference" | "candidate";
  isDropActive: boolean;
  isDragPending: boolean;
}

function FilePickerRow({ label, path, onPick, dropTarget, isDropActive, isDragPending }: FilePickerRowProps) {
  return (
    <div
      data-drop-target={dropTarget}
      className={[
        "flex items-center gap-4 rounded-md p-2 transition-colors",
        isDropActive
          ? "border-2 border-dashed border-blue-400 bg-blue-50 ring-2 ring-blue-400"
          : isDragPending
            ? "border-2 border-dashed border-slate-300 bg-slate-50"
            : "border-2 border-transparent",
      ].join(" ")}
    >
      <span className="w-28 shrink-0 text-sm font-medium text-slate-700">{label}</span>
      <span className="flex-1 truncate rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        {isDropActive ? "Datei hier ablegen…" : path || "Keine Datei ausgewählt"}
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
  const [activeDropTarget, setActiveDropTarget] = useState<DropTarget>(null);
  const [isDragPending, setIsDragPending] = useState(false);

  useEffect(() => {
    // Verhindert, dass der Browser eine gedroppte Datei selbst öffnet.
    const preventDefault = (event: DragEvent) => event.preventDefault();
    window.addEventListener("dragover", preventDefault);
    window.addEventListener("drop", preventDefault);

    let unlisten: (() => void) | undefined;

    // Tauri liefert die Cursor-Position fensterweit in physischen/logischen
    // Pixeln mit einem konstanten, aber unbekannten Y-Offset gegenüber
    // getBoundingClientRect()/document.elementFromPoint() (vermutlich durch
    // Titelleiste/Fensterdekoration). Statt den Offset zu berechnen, wird er
    // pro Drag-Session einmalig empirisch kalibriert: Sobald der Cursor über
    // einem der Zielfelder steht, liefert einer der getesteten Offsets (0-50)
    // einen Treffer per elementFromPoint — dieser wird für den Rest der
    // Drag-Session wiederverwendet.
    let calibratedYOffset: number | null = null;

    function resolveDropTarget(tauriX: number, tauriY: number): DropTarget {
      if (calibratedYOffset === null) {
        for (let testOffset = 0; testOffset <= 50; testOffset++) {
          const el = document.elementFromPoint(tauriX, tauriY - testOffset);
          const hit = el?.closest("[data-drop-target]");
          if (hit) {
            calibratedYOffset = testOffset;
            break;
          }
        }
      }

      if (calibratedYOffset === null) {
        return null;
      }

      const el = document.elementFromPoint(tauriX, tauriY - calibratedYOffset);
      const hit = el?.closest<HTMLElement>("[data-drop-target]");
      return (hit?.dataset.dropTarget as DropTarget) ?? null;
    }

    getCurrentWebview()
      .onDragDropEvent((event) => {
        const payload = event.payload;

        if (payload.type === "enter") {
          calibratedYOffset = null;
          setIsDragPending(true);
          return;
        }

        if (payload.type === "over") {
          setActiveDropTarget(resolveDropTarget(payload.position.x, payload.position.y));
          return;
        }

        if (payload.type === "drop") {
          const target = resolveDropTarget(payload.position.x, payload.position.y);
          setActiveDropTarget(null);
          setIsDragPending(false);
          calibratedYOffset = null;

          if (!target) {
            return;
          }
          if (payload.paths.length > 1) {
            setError("Es kann nur eine Datei pro Feld abgelegt werden. Nur die erste Datei wurde übernommen.");
          }
          const droppedPath = payload.paths[0];
          if (!droppedPath || !droppedPath.toLowerCase().endsWith(".pdf")) {
            setError("Nur PDF-Dateien können per Drag & Drop abgelegt werden.");
            return;
          }
          if (payload.paths.length <= 1) {
            setError("");
          }
          if (target === "reference") {
            setRefPath(droppedPath);
          } else {
            setCndPath(droppedPath);
          }
          return;
        }

        // "leave": Drag hat das Fenster verlassen oder wurde abgebrochen.
        setActiveDropTarget(null);
        setIsDragPending(false);
        calibratedYOffset = null;
      })
      .then((fn) => {
        unlisten = fn;
      });

    return () => {
      window.removeEventListener("dragover", preventDefault);
      window.removeEventListener("drop", preventDefault);
      unlisten?.();
    };
  }, []);

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
