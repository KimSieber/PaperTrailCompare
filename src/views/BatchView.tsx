import { MainPanel } from "../layout/MainPanel";
import { PlaceholderPanel } from "../layout/PlaceholderPanel";

export function BatchView() {
  return (
    <MainPanel
      title="Batch / Job-Queue"
      description="Massenvergleich per Dateiliste oder XMP-Zuordnung; Job-Status verwalten."
    >
      <PlaceholderPanel label="Job-Queue-Verwaltung folgt." />
    </MainPanel>
  );
}
