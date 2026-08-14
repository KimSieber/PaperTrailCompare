/**
 * @file    src/components/ProfileSelect.tsx
 * @purpose Dropdown for choosing a comparison profile (.json file) from the
 *          directory configured in SettingsView. Shared by
 *          SingleComparisonView and BatchView. Works with plain filename
 *          strings - "Kein Profil" (empty string) means no --profile is
 *          passed to the sidecar, so engine defaults apply. Visually
 *          matches FilePickerRow so both can sit as rows in the same white
 *          <section> block. With `persistMode` set, the selection is
 *          restored on mount and persisted on every change via
 *          get_selected_profiles/set_selected_profile (src-tauri/src/lib.rs).
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-14
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

interface ProfileSelectProps {
  value: string;
  onChange: (profileName: string) => void;
  persistMode?: "single" | "batch";
}

export function ProfileSelect({ value, onChange, persistMode }: ProfileSelectProps) {
  const [profiles, setProfiles] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    invoke<string[]>("list_profiles")
      .then(setProfiles)
      .catch((err) => setError(String(err)));
  }, []);

  // Restauriert die persistierte Auswahl beim ersten Rendern.
  useEffect(() => {
    if (!persistMode) {
      return;
    }
    invoke<[string | null, string | null]>("get_selected_profiles")
      .then(([single, batch]) => {
        const restored = persistMode === "single" ? single : batch;
        onChange(restored ?? "");
      })
      .catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persistMode]);

  function handleChange(profileName: string) {
    onChange(profileName);
    if (persistMode) {
      void invoke("set_selected_profile", {
        mode: persistMode,
        profileName: profileName || null,
      }).catch((err) => setError(String(err)));
    }
  }

  return (
    <div>
      <div className="flex items-center gap-4 rounded-md p-2">
        <span className="w-28 shrink-0 text-sm font-medium text-slate-700">Profil:</span>
        <select
          value={value}
          onChange={(event) => handleChange(event.target.value)}
          className="flex-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600"
        >
          <option value="">Kein Profil</option>
          {profiles.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p className="px-2 text-xs text-red-700">
          Fehler: <code>{error}</code>
        </p>
      )}
    </div>
  );
}
