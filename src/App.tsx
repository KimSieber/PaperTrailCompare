/**
 * @file    src/App.tsx
 * @purpose Root component with sidebar navigation and view switching
 *          (single comparison, batch, settings).
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import { useState } from "react";
import { Sidebar } from "./layout/Sidebar";
import { SingleComparisonView } from "./views/SingleComparisonView";
import { BatchView } from "./views/BatchView";
import { SettingsView } from "./views/SettingsView";
import type { ViewKey } from "./types";

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("single");

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
