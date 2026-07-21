import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { MainPanel } from "../layout/MainPanel";
import { PlaceholderPanel } from "../layout/PlaceholderPanel";

export function SettingsView() {
  const [engineStatus, setEngineStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [checking, setChecking] = useState(false);

  async function checkEngine() {
    setError("");
    setEngineStatus("");
    setChecking(true);
    try {
      // Ruft die Python Core Engine als Sidecar-Prozess auf (lokales IPC
      // über Tauri-Commands, kein Netzwerk-Socket).
      const version = await invoke<string>("engine_version");
      setEngineStatus(version);
    } catch (err) {
      setError(String(err));
    } finally {
      setChecking(false);
    }
  }

  return (
    <MainPanel
      title="Einstellungen"
      description="Vergleichsprofile, Lizenz und Engine-Status."
    >
      <div className="space-y-6">
        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">Engine-Status</h2>
          <p className="mt-1 text-sm text-slate-500">
            Prüft, ob die Python Core Engine als lokaler Sidecar-Prozess
            erreichbar ist.
          </p>

          <button
            type="button"
            onClick={checkEngine}
            disabled={checking}
            className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {checking ? "Prüfe…" : "Engine-Sidecar prüfen"}
          </button>

          {engineStatus && (
            <p className="mt-3 text-sm text-emerald-700">
              Sidecar antwortet: <code>{engineStatus}</code>
            </p>
          )}
          {error && (
            <p className="mt-3 text-sm text-red-700">
              Fehler: <code>{error}</code>
            </p>
          )}
        </section>

        <section>
          <h2 className="mb-2 text-sm font-semibold text-slate-900">
            Vergleichsprofile
          </h2>
          <PlaceholderPanel label="Profil-Verwaltung (JSON) folgt." />
        </section>
      </div>
    </MainPanel>
  );
}
