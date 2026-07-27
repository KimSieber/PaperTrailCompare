import { useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";

interface UseDragDropTargetOptions<T extends string> {
  /** Wird für jeden gedroppten Pfad aufgerufen, um zu prüfen, ob er für das
   * jeweilige Zielfeld akzeptiert werden darf (z.B. Dateiendung). */
  isValidPath: (target: T, path: string) => boolean;
  /** Wird mit dem ersten akzeptierten Pfad aufgerufen, sobald über dem
   * jeweiligen Zielfeld gedroppt wurde. wasMultiple zeigt an, ob mehr als
   * eine Datei gedroppt wurde (nur die erste wird übernommen). */
  onDrop: (target: T, path: string, wasMultiple: boolean) => void;
  /** Wird aufgerufen, wenn der gedroppte Pfad isValidPath nicht erfüllt. */
  onInvalidDrop: (target: T, path: string) => void;
  /** Wird aufgerufen, wenn mehr als eine Datei auf einem Zielfeld gedroppt wurde. */
  onMultipleDropped?: (target: T) => void;
}

/**
 * Kapselt die Drag-n-Drop-Logik für ein Set benannter Drop-Zielfelder
 * (data-drop-target="<target>"), inkl. der einmalig pro Drag-Session
 * empirisch kalibrierten Y-Offset-Korrektur zwischen Tauris
 * fensterweiten Cursor-Koordinaten und document.elementFromPoint()
 * (siehe SingleComparisonView / CLAUDE.md). Wird von SingleComparisonView
 * und BatchView gemeinsam genutzt, damit diese Kalibrierung nicht doppelt
 * gepflegt werden muss.
 */
export function useDragDropTarget<T extends string>({
  isValidPath,
  onDrop,
  onInvalidDrop,
  onMultipleDropped,
}: UseDragDropTargetOptions<T>) {
  const [activeDropTarget, setActiveDropTarget] = useState<T | null>(null);
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

    function resolveDropTarget(tauriX: number, tauriY: number): T | null {
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
      return (hit?.dataset.dropTarget as T | undefined) ?? null;
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
          const wasMultiple = payload.paths.length > 1;
          if (wasMultiple) {
            onMultipleDropped?.(target);
          }
          const droppedPath = payload.paths[0];
          if (!droppedPath) {
            return;
          }
          if (!isValidPath(target, droppedPath)) {
            onInvalidDrop(target, droppedPath);
            return;
          }
          onDrop(target, droppedPath, wasMultiple);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { activeDropTarget, isDragPending };
}
