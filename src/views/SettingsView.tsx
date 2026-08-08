/**
 * @file    src/views/SettingsView.tsx
 * @purpose Settings view for comparison profiles (whitespace tolerance,
 *          compare mode), engine sidecar health check, and future profile
 *          management UI.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { MainPanel } from "../layout/MainPanel";
import { PlaceholderPanel } from "../layout/PlaceholderPanel";
import { RadioGroup } from "../layout/RadioGroup";
import { Toggle } from "../layout/Toggle";
import type { CompareMode, Profile } from "../types";

const COMPARE_MODE_OPTIONS: { value: CompareMode; label: string; description: string }[] = [
  {
    value: "words",
    label: "words — Standardvergleich",
    description: "Voreinstellung. Vergleicht auf Wortebene.",
  },
  {
    value: "hybrid",
    label: "hybrid — toleriert zerrissene Wortgrenzen",
    description:
      "Empfohlen bei Dokumenten aus älteren Drucksystemen, bei denen Wörter durch die PDF-Erzeugung fälschlich mit Leerzeichen zerrissen werden.",
  },
  {
    value: "chars",
    label: "chars — ignoriert Leerzeichen vollständig",
    description:
      "Vergleicht zeichenweise ohne jegliche Wortgrenzen. Kann bei ansonsten stark abweichenden Dokumenten viele kleine, verstreute Unterschiede erzeugen - in diesem Fall ist hybrid vorzuziehen.",
  },
];

export function SettingsView() {
  const [engineStatus, setEngineStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [checking, setChecking] = useState(false);
  const [normalizeWhitespace, setNormalizeWhitespace] = useState(true);
  const [compareMode, setCompareMode] = useState<CompareMode>("words");

  useEffect(() => {
    invoke<Profile>("load_settings")
      .then((profile) => {
        setNormalizeWhitespace(profile.normalize_whitespace);
        setCompareMode(profile.compare_mode);
      })
      .catch((err) => setError(String(err)));
  }, []);

  async function handleNormalizeWhitespaceChange(checked: boolean) {
    setNormalizeWhitespace(checked);
    try {
      await invoke("save_settings", {
        normalizeWhitespace: checked,
        compareMode,
      });
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleCompareModeChange(mode: CompareMode) {
    setCompareMode(mode);
    try {
      await invoke("save_settings", {
        normalizeWhitespace,
        compareMode: mode,
      });
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

        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">Vergleich</h2>
          <div className="mt-4">
            <Toggle
              label="Leerzeichen-Toleranz"
              description="Ignoriert Unterschiede, die nur durch zusätzliche oder fehlende Leerzeichen innerhalb von Wörtern entstehen (z.B. durch OCR-Fehler bei gescannten Dokumenten)."
              checked={normalizeWhitespace}
              onChange={handleNormalizeWhitespaceChange}
            />
          </div>
          <div className="mt-6 border-t border-slate-100 pt-5">
            <RadioGroup
              name="compare-mode"
              label="Vergleichsmodus"
              description="Bestimmt, auf welcher Ebene Referenz- und Kandidat-Text verglichen werden."
              value={compareMode}
              options={COMPARE_MODE_OPTIONS}
              onChange={handleCompareModeChange}
            />
          </div>
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
