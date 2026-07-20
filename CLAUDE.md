# CLAUDE.md — PaperTrail Compare

Diese Datei gibt Claude Code den Projektkontext für die Implementierung von **PaperTrail Compare**. Sie fasst Projektbeschreibung, Rahmenbedingungen und Testspezifikation zusammen und ist verbindliche Arbeitsgrundlage.

## 1. Projektüberblick

PaperTrail Compare ist eine Anwendung zum **textlichen Vergleich von PDF-Dateien**. Haupteinsatzzweck: Migrationen zwischen unterschiedlichen Output-Management-/Drucksystemen. Dabei muss geprüft werden, ob ein neues System inhaltlich dieselben Dokumente erzeugt wie das alte System — trotz unterschiedlicher Formatierer, Fonts-Rendering und Seitenumbrüchen.

**Kernidee:** Ein reiner Pixelvergleich scheitert, weil verschiedene Formatierer denselben Text unterschiedlich rendern und Seitenumbrüche sich verschieben können. PaperTrail Compare vergleicht daher **inhaltlich/textlich**, nicht pixelbasiert.

**Zielgruppe:** Unternehmen mit zentralen Drucksystemen, die einen Wechsel ihres Drucksystems planen oder durchführen.

## 2. Verbindliche Rahmenbedingungen (nicht verhandelbar)

### Datenschutz / Rechtlich
- Eingegebene Daten bzw. zu vergleichende Dokumente dürfen **das Unternehmen/den Kunden niemals verlassen**.
- Verarbeitung und Speicherung **ausschließlich lokal** beim Kunden.
- **Keine Cloud-Zugriffe, keine Telemetrie, keine externen API-Aufrufe.**
- Während der Verarbeitung darf **kein ausgehender Netzwerkverkehr** stattfinden (siehe TC-S-001).
- Temporäre Dateien mit Dokumenteninhalt müssen nach Verarbeitung vollständig bereinigt werden (siehe TC-S-002).

### Technik / Deployment
- Muss **beim Kunden lokal betreibbar** sein (Standalone).
- **Keine eigene Serverinstallation** erforderlich — lange interne Freigabeprozesse bei Kunden würden sonst den Verkauf/Rollout behindern (siehe TC-S-003).
- Läuft ohne Admin-Rechte auf einer frischen Maschine.

**Konsequenz für die Implementierung:** Keine Abhängigkeiten einbauen, die einen Server, eine Cloud-API oder eine externe Netzwerkverbindung voraussetzen (auch nicht optional/versteckt, z. B. Telemetrie in Libraries). Bei der Auswahl von Bibliotheken (z. B. für OCR) ist auf rein lokale Verarbeitung zu achten.

## 3. Funktionsumfang

### Vergleich
- Gleiche Texte trotz unterschiedlicher Silbentrennung werden **nicht** als Delta gewertet.
- Unterschiedliche Seitenumbrüche führen **nicht** zu einem Delta, solange der Text gleich ist.
- Bestimmte Seitenbereiche können vom Vergleich ausgeschlossen werden (Regionen).
- Seitengruppen können über Such-Patterns definiert werden.
- Vergleich kann auf bestimmte Seitengruppen eingeschränkt werden.
- Vergleichsprofile werden über JSON-Dateien konfiguriert.
- Automatische Erkennung von mehrspaltigem Text.
- Automatische Erkennung von Tabellen.
- OCR-Erkennung + Textvergleich für eingescannten/als Grafik hinterlegten Text.

### Batchprocessing
- Massenvergleich per Dateiliste (Datei-Pärchen).
- Massenvergleich per XMP-Metadaten (z. B. gleiche Document-ID).
- Massenvergleich von Dokumenten innerhalb großer Batch-PDFs, Dokumentenpaare werden über Texte in definierten Seitengruppen ermittelt.

### Report
- Markierung der Deltas im Reference- und im Candidate-Dokument.
- Batch-Report über alle Dateivergleiche.
- Detaillierter Report über Deltas mit Seiten- und Dateiangabe.
- Report-Format konfigurierbar (PDF / HTML).

### Grafische Admin-/Benutzeroberfläche
- Einzelvergleich von Dateipaaren.
- Massenvergleich mit Administration von Job-Queues.
- **Hinweis:** Die GUI wird laut Testspezifikation manuell getestet, nicht per Unit-/Integrationstest.

## 4. Architektur — Modulschichten (TDD-Strategie)

Implementierung folgt strikt von innen nach außen. **Schicht 1 zuerst, P1-Tests müssen bestehen, bevor an Schicht 2/3 weitergearbeitet wird.**

| Schicht | Modul | Schwerpunkt | Testtyp |
|---|---|---|---|
| 1 | `text_comparator` | Textvergleich, Normalisierung, Silbentrennung, Seitenumbruch | Unit-Tests |
| 1 | `pdf_extractor` | PDF-Textextraktion, Mehrspaltigkeit, Tabellen, OCR | Unit-Tests |
| 2 | `profile_loader` | JSON-Profilvalidierung, Region-Ausschluss, Seitengruppen | Unit-Tests |
| 2 | `region_filter` | Ausschluss-Regionen pro Seite | Unit-Tests |
| 2 | `page_group_detector` | Seitengruppen per Such-Pattern | Unit-Tests |
| 2 | `ocr_extractor` | OCR-Verarbeitung (Tesseract) | Unit-Tests |
| 3 | `batch_processor` | Massenvergleich, XMP-Zuordnung, Fehlerbehandlung | Integrationstests |
| 3 | `report_generator` | Delta-Markierung, Batch-Report, Formate | Integrationstests |
| Q | privacy / compliance | Datenschutz, Standalone-Betrieb, Temp-Dateien | Systemtests |

`text_comparator` nimmt zwei normalisierte Textstränge entgegen und liefert ein `CompareResult`-Objekt zurück (u. a. `has_delta`, Delta-Liste mit Seiten-/Positionsangabe).

## 5. Tech-Stack

| Komponente | Technologie |
|---|---|
| Test-Framework | pytest ≥ 8 |
| PDF-Erstellung (Fixtures) | reportlab |
| PDF-Extraktion | pdfplumber / pymupdf |
| OCR | tesseract via pytesseract |
| Parametrisierung | pytest.mark.parametrize |
| Coverage | pytest-cov (Ziel: ≥ 90 % für Schicht 1) |

## 6. Test- und Fixture-Regeln

- **Niemals echte Kundendokumente als Testdaten verwenden** — ausschließlich synthetisch erzeugte Fixture-PDFs (via reportlab).
- Fixtures liegen versioniert unter `tests/fixtures/` und dokumentieren gleichzeitig die Anforderungen (Fixture = lebende Spezifikation).
- Testfall-IDs folgen dem Schema `TC-<Modulkürzel>-<Nummer>` (z. B. `TC-T-001` für `text_comparator`, `TC-E-*` für `region_filter`, `TC-G-*` für `page_group_detector`, `TC-O-*` für `ocr_extractor`, `TC-P-*` für `profile_loader`, `TC-B-*` für `batch_processor`, `TC-R-*` für `report_generator`, `TC-S-*` für privacy/compliance).
- Priorität steuert Implementierungsreihenfolge:
  - **P1 – Muss:** Kernfunktionalität, TDD-Einstieg, blockiert andere Tests bei Fehlschlag.
  - **P2 – Soll:** wichtig für Produktionsreife, nach P1 umzusetzen.
  - **P3 – Kann:** Nice-to-have, optional.
- Vollständige Testfall-Matrix (32 Testfälle: 18×P1, 13×P2, 1×P3) ist in `PaperTrailCompare_Testspezifikation.docx` dokumentiert — bei Implementierung eines Moduls immer zuerst die zugehörigen Testfälle aus diesem Dokument als Grundlage nehmen (Test-First / TDD).

## 7. Arbeitsweise für Claude Code

1. **TDD strikt einhalten:** Erst den (fehlschlagenden) Test aus der Testspezifikation schreiben bzw. übernehmen, dann die Implementierung, die ihn grün macht.
2. **Reihenfolge:** Schicht 1 (`text_comparator`, `pdf_extractor`) vollständig mit P1-Tests grün, bevor Schicht 2 begonnen wird; danach Schicht 3.
3. Bei jedem neuen Modul zuerst in der Testspezifikation nachsehen, welche Testfälle (ID, Vorbedingung, erwartetes Ergebnis) dafür vorgesehen sind, und diese als Ausgangspunkt für die pytest-Tests verwenden.
4. **Keine Netzwerkzugriffe** in Produktivcode einbauen (siehe Abschnitt 2) — das gilt auch für Hilfsbibliotheken, Update-Checks o. Ä.
5. Bei Unsicherheit zwischen mehreren möglichen Implementierungen: diejenige wählen, die den Betrieb **ohne Server und rein lokal** unterstützt.
6. Coverage-Ziel für Schicht 1 (`text_comparator`, `pdf_extractor`) beachten: ≥ 90 %.
7. GUI-Code nicht mit automatisierten Tests überfrachten — die GUI wird laut Spezifikation manuell getestet.

## 8. Referenzdokumente im Projekt

- `Projektbeschreibung` — Management Summary, Funktionsumfang.
- `Rahmenbedingungen` — Zielgruppe, rechtliche und technische Vorgaben.
- `PaperTrailCompare_Testspezifikation.docx` — vollständige Testfall-Matrix (Quelle der Wahrheit für alle Testfälle).

Diese CLAUDE.md ist eine Verdichtung dieser Dokumente. Bei Widersprüchen oder Detailfragen gelten die Originaldokumente als maßgeblich.
