import type { ReactNode } from "react";

interface MainPanelProps {
  title: string;
  description: string;
  children: ReactNode;
}

export function MainPanel({ title, description, children }: MainPanelProps) {
  return (
    <div className="flex h-full flex-1 flex-col overflow-y-auto bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-8 py-5">
        <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
        <p className="mt-0.5 text-sm text-slate-500">{description}</p>
      </header>

      <div className="flex-1 px-8 py-6">{children}</div>
    </div>
  );
}
