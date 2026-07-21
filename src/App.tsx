import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";

function App() {
  const [engineStatus, setEngineStatus] = useState<string>("");
  const [error, setError] = useState<string>("");

  async function checkEngine() {
    setError("");
    setEngineStatus("");
    try {
      // Ruft die Python Core Engine als Sidecar-Prozess auf (lokales IPC
      // über Tauri-Commands, kein Netzwerk-Socket).
      const version = await invoke<string>("engine_version");
      setEngineStatus(version);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 p-8 text-slate-900">
      <h1 className="text-2xl font-semibold">PaperTrail Compare</h1>
      <p className="text-slate-600">
        Textlicher Vergleich von PDF-Dateien für Output-Management-Migrationen.
      </p>

      <button
        type="button"
        onClick={checkEngine}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        Engine-Sidecar prüfen
      </button>

      {engineStatus && (
        <p className="text-sm text-emerald-700">
          Sidecar antwortet: <code>{engineStatus}</code>
        </p>
      )}
      {error && (
        <p className="text-sm text-red-700">
          Fehler: <code>{error}</code>
        </p>
      )}
    </main>
  );
}

export default App;
