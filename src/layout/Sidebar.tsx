import type { ReactElement } from "react";
import type { ViewKey } from "../types";
import { CompareIcon, QueueIcon, SettingsIcon } from "./icons";

interface NavItem {
  key: ViewKey;
  label: string;
  icon: (props: { className?: string }) => ReactElement;
}

const NAV_ITEMS: NavItem[] = [
  { key: "single", label: "Einzelvergleich", icon: CompareIcon },
  { key: "batch", label: "Batch / Job-Queue", icon: QueueIcon },
  { key: "settings", label: "Einstellungen", icon: SettingsIcon },
];

interface SidebarProps {
  active: ViewKey;
  onSelect: (key: ViewKey) => void;
}

export function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <aside className="flex h-full w-60 flex-col bg-slate-900 text-slate-300">
      <div className="flex h-14 items-center border-b border-slate-800 px-5">
        <span className="text-sm font-semibold tracking-wide text-white">
          PaperTrail Compare
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
          const isActive = key === active;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelect(key)}
              className={[
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100",
              ].join(" ")}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {label}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-slate-800 px-5 py-3 text-xs text-slate-500">
        Version 0.1.0
      </div>
    </aside>
  );
}
