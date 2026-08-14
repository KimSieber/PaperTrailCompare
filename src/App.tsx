/**
 * @file    src/App.tsx
 * @purpose Root component with sidebar navigation and view switching
 *          (single comparison, batch, settings).
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Sidebar } from "./layout/Sidebar";
import { SingleComparisonView } from "./views/SingleComparisonView";
import { BatchView } from "./views/BatchView";
import { SettingsView } from "./views/SettingsView";
import { formatGermanDate } from "./components/AboutDialog";
import type { EngineInfo, ViewKey } from "./types";

const CONTACT_EMAIL = "PaperTrail@Sieber-BW.de";

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("single");
  const [expiredInfo, setExpiredInfo] = useState<EngineInfo | null>(null);

  // Ablaufprüfung beim Start (siehe engine_version / engine.__expiry__).
  // Ist die Engine (noch) nicht erreichbar, bleibt die App nutzbar - der
  // Fehler zeigt sich erst beim tatsächlichen Vergleichsversuch.
  useEffect(() => {
    (async () => {
      try {
        const info = await invoke<EngineInfo>("engine_version");
        if (info.expired) {
          setExpiredInfo(info);
        }
      } catch {
        // Engine (noch) nicht erreichbar - kein Blocker beim Start.
      }
    })();
  }, []);

  if (expiredInfo) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-900/90">
        <div className="max-w-md rounded-lg bg-white p-8 text-center shadow-xl">
          <h1 className="text-lg font-semibold text-red-600">Testversion abgelaufen</h1>
          <p className="mt-3 text-sm text-slate-700">
            Diese Testversion von PaperTrail Compare ist am{" "}
            {formatGermanDate(expiredInfo.expiry)} abgelaufen. Bitte wenden Sie sich an{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">
              {CONTACT_EMAIL}
            </a>{" "}
            für eine aktuelle Version.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 text-slate-900">
      <Sidebar active={activeView} onSelect={setActiveView} />

      {activeView === "single" && <SingleComparisonView />}
      {activeView === "batch" && <BatchView />}
      {activeView === "settings" && <SettingsView />}
    </div>
  );
}

export default App;
