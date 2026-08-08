/**
 * @file    src/layout/PlaceholderPanel.tsx
 * @purpose Placeholder component for not-yet-implemented UI sections,
 *          displaying a centered label in a dashed border panel.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

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
