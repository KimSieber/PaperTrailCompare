/**
 * @file    src/components/AboutDialog.tsx
 * @purpose Modal "About" overlay shown when the sidebar version number is
 *          clicked (see Sidebar). Displays app icon, name, version, expiry
 *          date, copyright and contact links.
 * @author  Kim Sieber
 * @created 2026-08-14
 * @changed 2026-08-14
 */

import { useEffect } from "react";
import type { MouseEvent } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import appIcon from "../assets/app-icon.png";

const WEBSITE_URL = "https://papertrail.sieber-bw.de";
const CONTACT_EMAIL = "PaperTrail@Sieber-BW.de";

/** Formatiert ein ISO-Datum (YYYY-MM-DD) als deutsches Datum (DD.MM.YYYY). */
export function formatGermanDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
}

export interface AboutDialogProps {
  version: string;
  expiry: string;
  onClose: () => void;
}

/** Modal-Overlay mit App-Infos; schließt per Backdrop-Klick, Escape oder
 * X-Button. Der Website-Link öffnet über das Tauri-Opener-Plugin im
 * externen Standardbrowser (kein interner Webview-Navigationssprung). */
export function AboutDialog({ version, expiry, onClose }: AboutDialogProps) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function handleWebsiteClick(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    void openUrl(WEBSITE_URL);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-[400px] rounded-lg bg-white p-6 text-center shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Schließen"
          className="absolute right-3 top-3 text-slate-400 hover:text-slate-600"
        >
          ✕
        </button>

        <img src={appIcon} alt="PaperTrail Compare" className="mx-auto h-16 w-16" />
        <h2 className="mt-3 text-lg font-semibold text-slate-900">PaperTrail Compare</h2>
        <p className="mt-1 text-sm text-slate-600">Version {version}</p>
        <p className="text-sm text-slate-600">
          Testversion gültig bis: {formatGermanDate(expiry)}
        </p>

        <hr className="my-4 border-slate-200" />

        <p className="text-xs text-slate-500">© 2026 Kim Sieber, Stuttgart</p>
        <p className="mt-2 text-sm">
          <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline">
            {CONTACT_EMAIL}
          </a>
        </p>
        <p className="mt-1 text-sm">
          <a href={WEBSITE_URL} onClick={handleWebsiteClick} className="text-blue-600 hover:underline">
            {WEBSITE_URL}
          </a>
        </p>
      </div>
    </div>
  );
}
