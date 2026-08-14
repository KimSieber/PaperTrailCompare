/**
 * @file    src/views/SettingsView.tsx
 * @purpose Settings view for profile directory configuration and engine
 *          sidecar health check. Comparison profiles (JSON files) are
 *          selected per-comparison via the dropdown in SingleComparisonView/
 *          BatchView, not edited here - this view only manages where the
 *          engine should look for them.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { MainPanel } from "../layout/MainPanel";

export function SettingsView() {
  const [engineStatus, setEngineStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [checking, setChecking] = useState(false);
  const [profileDirectory, setProfileDirectory] = useState<string>("");

  useEffect(() => {
    invoke<string | null>("get_profile_directory")
      .then((dir) => setProfileDirectory(dir ?? ""))
      .catch((err) => setError(String(err)));
  }, []);

  async function pickProfileDirectory() {
    const path = await open({ multiple: false, directory: true });
    if (typeof path !== "string") {
      return;
    }
    try {
      await invoke("set_profile_directory", { path });
      setProfileDirectory(path);
    } catch (err) {
      setError(String(err));
    }
  }

  async function checkEngine() {
    setError("");
    setEngineStatus("");
    setChecking(true);
    try {
      // Ruft die Python Core Engine als Sidecar-Prozess auf (lokales IPC
      // über Tauri-Commands, kein Netzwerk-Socket).
      const info = await invoke<{ version: string; expiry: string; expired: boolean }>(
        "engine_version"
      );
      setEngineStatus(info.version);
    } catch (err) {
      setError(String(err));
    } finally {
      setChecking(false);
    }
  }

  return (
    <MainPanel
      title="Einstellungen"
      description="Profilverzeichnis, Lizenz und Engine-Status."
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

        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">Vergleichsprofile</h2>
          <p className="mt-1 text-sm text-slate-500">
            Verzeichnis mit den JSON-Vergleichsprofilen. Alle darin
            gefundenen .json-Dateien stehen im Einzel- und Batch-Vergleich
            über das Profil-Dropdown zur Auswahl.
          </p>

          <div className="mt-4 flex items-center gap-3">
            <input
              type="text"
              readOnly
              value={profileDirectory}
              placeholder="Kein Profilverzeichnis ausgewählt"
              className="flex-1 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-700"
            />
            <button
              type="button"
              onClick={pickProfileDirectory}
              className="whitespace-nowrap rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Durchsuchen…
            </button>
          </div>
        </section>
      </div>
    </MainPanel>
  );
}
