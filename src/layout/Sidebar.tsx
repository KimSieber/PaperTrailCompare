/**
 * @file    src/layout/Sidebar.tsx
 * @purpose Navigation sidebar with view selection buttons (single, batch,
 *          settings) and active-state highlighting.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useState } from "react";
import type { ReactElement } from "react";
import type { EngineInfo, ViewKey } from "../types";
import { AboutDialog } from "../components/AboutDialog";
import { CompareIcon, QueueIcon, SettingsIcon, InfoIcon } from "./icons";

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
  appVersion: string | null;
  engineInfo: EngineInfo | null;
}

export function Sidebar({ active, onSelect, appVersion, engineInfo }: SidebarProps) {
  const [showAbout, setShowAbout] = useState(false);

  function handleVersionClick() {
    if (engineInfo) {
      setShowAbout(true);
    }
  }

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

      <button
        type="button"
        onClick={handleVersionClick}
        className="flex w-full items-center gap-2 border-t border-slate-800 px-5 py-3 text-left text-xs text-slate-400 transition-colors hover:text-slate-200"
      >
        <InfoIcon className="h-3.5 w-3.5 shrink-0" />
        Version {appVersion ?? "…"}
      </button>

      {showAbout && engineInfo && (
        <AboutDialog
          version={engineInfo.version}
          expiry={engineInfo.expiry}
          onClose={() => setShowAbout(false)}
        />
      )}
    </aside>
  );
}
