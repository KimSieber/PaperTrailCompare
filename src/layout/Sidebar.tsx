/**
 * @file    src/layout/Sidebar.tsx
 * @purpose Navigation sidebar with view selection buttons (single, batch,
 *          settings) and active-state highlighting.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { EngineInfo, ViewKey } from "../types";
import { AboutDialog } from "../components/AboutDialog";
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
  const [engineInfo, setEngineInfo] = useState<EngineInfo | null>(null);
  const [showAbout, setShowAbout] = useState(false);

  async function fetchEngineInfo(): Promise<EngineInfo | null> {
    try {
      const info = await invoke<EngineInfo>("engine_version");
      setEngineInfo(info);
      return info;
    } catch {
      // Engine (noch) nicht erreichbar - Versionsanzeige bleibt leer, kein
      // Dialog. Der Fehler zeigt sich erst beim tatsächlichen Vergleich.
      return null;
    }
  }

  useEffect(() => {
    void fetchEngineInfo();
  }, []);

  async function handleVersionClick() {
    const info = await fetchEngineInfo();
    if (info) {
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
        className="cursor-pointer border-t border-slate-800 px-5 py-3 text-left text-xs text-slate-500 hover:underline"
      >
        Version {engineInfo?.version ?? "…"}
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
