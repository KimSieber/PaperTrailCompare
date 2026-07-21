interface PlaceholderPanelProps {
  label: string;
}

/** Leerzustand für noch nicht implementierte Bereiche. */
export function PlaceholderPanel({ label }: PlaceholderPanelProps) {
  return (
    <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-sm text-slate-400">
      {label}
    </div>
  );
}
