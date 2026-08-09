/**
 * @file    src/components/ProfileSelect.tsx
 * @purpose Dropdown for choosing a comparison profile (.json file) from the
 *          directory configured in SettingsView. Shared by
 *          SingleComparisonView and BatchView. Works with plain filename
 *          strings - "Kein Profil" (empty string) means no --profile is
 *          passed to the sidecar, so engine defaults apply.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

interface ProfileSelectProps {
  value: string;
  onChange: (profileName: string) => void;
}

export function ProfileSelect({ value, onChange }: ProfileSelectProps) {
  const [profiles, setProfiles] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    invoke<string[]>("list_profiles")
      .then(setProfiles)
      .catch((err) => setError(String(err)));
  }, []);

  return (
    <div>
      <label htmlFor="profile-select" className="block text-sm font-medium text-slate-900">
        Vergleichsprofil
      </label>
      <select
        id="profile-select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
      >
        <option value="">Kein Profil</option>
        {profiles.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      {error && (
        <p className="mt-1 text-xs text-red-700">
          Fehler: <code>{error}</code>
        </p>
      )}
    </div>
  );
}
