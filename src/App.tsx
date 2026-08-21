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
  const [appVersion, setAppVersion] = useState<string | null>(null);
  const [engineInfo, setEngineInfo] = useState<EngineInfo | null>(null);

  // Sofortige Versionsanzeige aus Cargo.toml (compile-time, kein Sidecar).
  useEffect(() => {
    invoke<string>("get_app_version")
      .then((v) => setAppVersion(v))
      .catch(() => {});
  }, []);

  // Vollständiger Engine-Check (Sidecar, dauert 10-60s) — läuft im
  // Hintergrund, blockiert die Versionsanzeige nicht mehr.
  useEffect(() => {
    invoke<EngineInfo>("engine_version")
      .then((info) => setEngineInfo(info))
      .catch(() => {});
  }, []);

  if (engineInfo?.expired) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-900/90">
        <div className="max-w-md rounded-lg bg-white p-8 text-center shadow-xl">
          <h1 className="text-lg font-semibold text-red-600">Testversion abgelaufen</h1>
          <p className="mt-3 text-sm text-slate-700">
            Diese Testversion von PaperTrail Compare ist am{" "}
            {formatGermanDate(engineInfo.expiry)} abgelaufen. Bitte wenden Sie sich an{" "}
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
      <Sidebar
        active={activeView}
        onSelect={setActiveView}
        appVersion={appVersion}
        engineInfo={engineInfo}
      />

      {activeView === "single" && <SingleComparisonView />}
      {activeView === "batch" && <BatchView />}
      {activeView === "settings" && <SettingsView />}
    </div>
  );
}

export default App;
