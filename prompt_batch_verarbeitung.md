# Claude Code Prompt: Batch-Verarbeitung (Dialog + Live-Progress + Report)

## Kontext

PaperTrail Compare ist eine lokale Desktop-Anwendung (Tauri + React/TS + Python-Engine)
zum inhaltlichen Vergleich von PDF-Dateien im Rahmen von Drucksystem-Migrationen.
Kritische Anforderung: **alles läuft ausschließlich lokal** – keine Cloud, kein Server,
keine Netzwerkverbindung während der Verarbeitung.

Der Einzelvergleich (SingleComparisonView) funktioniert bereits: Dateiauswahl per
Klick oder Drag-n-Drop über die Komponente `FilePickerRow` (siehe
`src/views/SingleComparisonView`), Vergleich per Tauri-Command an die Python-Engine,
Ergebnisanzeige, PDF-Report-Erzeugung.

Für die Batch-Verarbeitung existiert bereits:
- Ein GUI-Gerüst `BatchView.tsx` (noch ohne Funktion)
- `engine/batch_processor.py` mit `batch_compare()`, `read_filelist()`,
  `_compare_pair()` etc. (siehe angehängte Datei / Repo)

**Bitte zunächst den aktuellen Stand im Repo verifizieren, bevor du mit der
Implementierung beginnst** (Dateien können seit dieser Prompt-Erstellung
weiterentwickelt worden sein):
- `src/views/SingleComparisonView` – Interface `FilePickerRowProps`, Komponente
  `FilePickerRow` (Klick + Drag-n-Drop, inkl. der bereits gelösten
  Tauri-Drop-Koordinaten-Problematik über `document.elementFromPoint()` mit
  Y-Offset-Kalibrierung – siehe `CLAUDE.md` / Kommentare im Code)
- `src/views/BatchView.tsx` – aktuelles Gerüst
- `engine/batch_processor.py` – aktuelle Fassung
- `engine/report_generator.py` – Status von `generate_batch_report`
  (laut Notizen implementiert, aber **nicht** in die Produktions-Pipeline
  eingebunden – bitte prüfen und ggf. im Rahmen dieser Aufgabe korrekt verdrahten)
- Tauri-Commands für den Einzelvergleich (Name, Signatur, Fehlerbehandlung) als
  Vorbild für die neuen Batch-Commands

## Ziel dieser Session

Ein eigener Tab/View "Batch" wird voll funktionsfähig:

1. Auswahl einer CSV-Dateiliste (Klick oder Drag-n-Drop, wie beim Einzelvergleich)
2. Auswahl eines Ausgabeverzeichnisses (Klick oder Drag-n-Drop)
3. Button "Vergleichen" startet die sequentielle Verarbeitung aller Paare
4. Während der Verarbeitung: kleiner Fortschrittsbalken ("105 von 328") +
   darunter eine scrollbare, sich aufbauende Liste mit je Zeile:
   Ref-Dateiname, Cnd-Dateiname, Anzahl Deltas, Übereinstimmung in %
5. Am Ende: eine zusätzliche PDF-Datei im Ausgabeverzeichnis mit:
   - Kopfbereich: Gesamtanzahl Dokumente, Laufzeit, Zeitpunkt
   - Tabelle: alle Paare mit Delta-Anzahl und Übereinstimmung in %

## Getroffene Architekturentscheidungen (bitte so umsetzen, nicht neu diskutieren)

- **CSV-Format geändert:** Die Dateiliste hat **keine Kopfzeile**. Jede Zeile:
  `Referenzdatei,Kandidatendatei`. `read_filelist()` in `batch_processor.py`
  muss entsprechend von `csv.DictReader` auf `csv.reader` mit Spaltenindex
  `[0]`/`[1]` umgestellt werden. **Bestehende Tests für `read_filelist`
  müssen entsprechend angepasst werden (TDD: Test zuerst anpassen, dann
  Implementierung).**
- **Live-Progress via Tauri-Events (nicht Frontend-Schleife):**
  `batch_compare()` bekommt einen optionalen Callback-Parameter
  (z.B. `on_progress: Optional[Callable[[int, int, PairResult], None]]`),
  der nach jedem verarbeiteten Paar aufgerufen wird
  (aktueller Index, Gesamtanzahl, Ergebnis des Paares). Der Tauri-Command,
  der `batch_compare()` aufruft, nutzt diesen Callback, um pro Paar ein
  Event Richtung Frontend zu emittieren (`window.emit(...)` bzw. das im
  Projekt übliche Äquivalent). Das Frontend abonniert dieses Event, aktualisiert
  Fortschrittsbalken und Liste inkrementell.
- **`workers` bleibt für diesen Schritt fest auf `1`** (sequentiell). Die
  Parallelverarbeitung (`workers>1`) wird bewusst **nicht** in dieser Session
  an die GUI angebunden – das ist ein späterer, eigener Schritt (siehe
  "Nicht Teil dieser Session" unten). Bitte den Callback-Mechanismus aber so
  bauen, dass er später mit `workers>1` kompatibel ist (Ergebnisreihenfolge
  kann dann von der Dateilisten-Reihenfolge abweichen).
- **Ausgabe-Report:** PDF-Format, analog zum Aufbau des Einzelvergleich-Reports
  (gleiche Bibliothek/Stil: PyMuPDF + ReportLab). Dateiname z.B.
  `Batch-Report_{YYYY-MM-DD_HH-MM}.pdf` im gewählten Ausgabeverzeichnis.
  Falls `generate_batch_report` in `report_generator.py` bereits eine
  passende Grundlage bietet: wiederverwenden und korrekt in die Pipeline
  einbinden statt zu duplizieren.
- **Fehlerbehandlung pro Paar:** Fehlt eine Datei, wird das Paar mit
  `status="error"` protokolliert (bereits in `_compare_pair` vorhanden) und
  in der GUI-Liste entsprechend markiert (z.B. rote Zeile mit Fehlertext
  statt Delta-Anzahl/Prozent); die Verarbeitung der übrigen Paare läuft
  weiter (siehe TC-B-002).
- **Komponenten-Wiederverwendung:** `FilePickerRow` aus
  `SingleComparisonView` wird für die CSV-Auswahl direkt wiederverwendet.
  Für die Ausgabeverzeichnis-Auswahl: prüfen, ob `FilePickerRow` einen Modus
  für Verzeichnisse statt Dateien unterstützt bzw. leicht darauf erweiterbar
  ist (Tauri-Dialog mit `directory: true`), ohne die bestehende
  Drag-n-Drop-Logik zu duplizieren.

## Nicht Teil dieser Session (bewusst zurückgestellt)

- Freischalten von `workers>1` in der GUI (eigener, späterer Prompt)
- Batch-Zuordnung per XMP (`batch_compare_by_xmp`) an die GUI anbinden
- Batch-PDF-Splitting (`split_batch_pdf`) an die GUI anbinden
- Abbrechen-Button während laufender Verarbeitung

## Arbeitsweise (bitte unbedingt einhalten)

- **Schritt für Schritt vorgehen, nach max. 2 Schritten pausieren** und auf
  Rückmeldung/Bestätigung warten, bevor der nächste Schritt begonnen wird.
- **TDD:** Vor jeder Implementierungsänderung erst den/die passenden Test(s)
  schreiben bzw. anpassen, `pytest` laufen lassen, dann implementieren.
- Vorgeschlagene Schrittfolge (jeweils nach Abschluss pausieren):
  1. `read_filelist()` auf kopfzeilenlose CSV umstellen (Test + Implementierung)
  2. Progress-Callback in `batch_compare()` einbauen (Test + Implementierung)
  3. Tauri-Command für Batch-Start inkl. Event-Emission pro Paar
  4. `BatchView.tsx`: CSV-Auswahl (FilePickerRow wiederverwenden)
  5. `BatchView.tsx`: Ausgabeverzeichnis-Auswahl
  6. `BatchView.tsx`: Fortschrittsbalken + wachsende, scrollbare Ergebnisliste
     (Event-Listener anbinden)
  7. Report-Erzeugung (`generate_batch_report` prüfen/verdrahten) am Ende
     des Batch-Laufs
  8. Manueller End-to-End-Test mit einer kleinen Beispiel-CSV (synthetische
     Fixture-PDFs, keine echten Kundendokumente)
- Commit an sinnvollen Meilensteinen (nach jedem grün getesteten Schritt).
- Bei Unklarheiten im Code (z.B. genaue Signatur des bestehenden
  Einzelvergleich-Tauri-Commands) bitte selbst im Repo nachsehen, bevor
  nachgefragt wird – nur bei echten Entscheidungsfragen (nicht im Repo
  auffindbar) nachfragen.
