import { MainPanel } from "../layout/MainPanel";
import { PlaceholderPanel } from "../layout/PlaceholderPanel";

export function SingleComparisonView() {
  return (
    <MainPanel
      title="Einzelvergleich"
      description="Referenz- und Kandidat-PDF auswählen und textlich vergleichen."
    >
      <PlaceholderPanel label="Datei-Auswahl und Vergleichsergebnis folgen." />
    </MainPanel>
  );
}
