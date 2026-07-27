export interface FilePickerRowProps {
  label: string;
  path: string;
  onPick: () => void;
  dropTarget: string;
  isDropActive: boolean;
  isDragPending: boolean;
  placeholder?: string;
}

/** Eine Auswahlzeile für eine Datei oder ein Verzeichnis: Klick auf
 * "Durchsuchen…" oder Drag & Drop auf die Zeile (siehe useDragDropTarget). */
export function FilePickerRow({
  label,
  path,
  onPick,
  dropTarget,
  isDropActive,
  isDragPending,
  placeholder = "Keine Datei ausgewählt",
}: FilePickerRowProps) {
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
        {isDropActive ? "Hier ablegen…" : path || placeholder}
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
