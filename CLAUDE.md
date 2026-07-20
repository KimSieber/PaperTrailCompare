# CLAUDE.md — PaperTrail Compare

Diese Datei gibt Claude Code den Projektkontext für die Implementierung von **PaperTrail Compare**. Sie fasst Projektbeschreibung, Rahmenbedingungen, Testspezifikation und Architekturspezifikation zusammen und ist verbindliche Arbeitsgrundlage.

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

**Konsequenz für die Implementierung:** Keine Abhängigkeiten einbauen, die einen Server, eine Cloud-API oder eine externe Netzwerkverbindung voraussetzen (auch nicht optional/versteckt, z. B. Telemetrie in Libraries). Bei der Auswahl von Bibliotheken (z. B. für OCR) ist auf rein lokale Verarbeitung zu achten. Die GUI kommuniziert ausschließlich über lokales IPC (Tauri-Commands) mit der Python-Engine — es werden keine Netzwerk-Sockets geöffnet.

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
- **Primäres Format: PDF.** Delta-Markierungen direkt im PDF sichtbar (PyMuPDF + ReportLab). HTML ist ein konfigurierbares Alternativformat, kein Default.

### Grafische Admin-/Benutzeroberfläche (Tauri Desktop-Shell)
- Einzelvergleich von Dateipaaren.
- Massenvergleich mit Administration von Job-Queues.
- **Hinweis:** Die GUI wird laut Testspezifikation manuell getestet, nicht per Unit-/Integrationstest.

## 4. Architektur

### 4.1 Überblick — Dreischichtiges Modell

- **Desktop-Shell (Tauri):** natives Fenster, Installer-Erzeugung, IPC-Bridge zum Python-Prozess.
- **Python Core Engine:** gesamte Fachlogik — PDF-Extraktion, Diff, OCR, Batch, Report.
- **Lokaler Speicher:** Dateisystem (PDFs), SQLite (Jobs/Status), JSON (Profile).

Die Kommunikation zwischen GUI und Engine läuft **ausschließlich über Tauri-Commands (lokales IPC)**, nicht über Netzwerk-Sockets.

### 4.2 Modulschichten (TDD-Strategie)

Implementierung folgt strikt von innen nach außen. **Schicht 1 zuerst, P1-Tests müssen bestehen, bevor an Schicht 2/3 weitergearbeitet wird.** Ziel: ≥ 90 % Test-Coverage für Schicht 1.

| Schicht | Modul | Schwerpunkt | Testtyp |
|---|---|---|---|
| 1 – Vergleichskern | `text_comparator` | Normalisierung, Silbentrennung, Seitenumbruch-Toleranz, Diff | Unit-Tests |
| 1 – Vergleichskern | `pdf_extractor` | PDF-Text, Mehrspaltigkeit, Tabellen, OCR-Erkennung | Unit-Tests |
| 1 – Vergleichskern | `region_filter` | Koordinatenbasierter Ausschluss definierter Seitenbereiche | Unit-Tests |
| 2 – Konfiguration | `profile_loader` | JSON-Validierung, typsichere Konfigurationsobjekte | Unit-Tests |
| 2 – Konfiguration | `page_group_detector` | Pattern-basierte Seitengruppen für Batch-PDFs | Unit-Tests |
| 2 – Konfiguration | `ocr_extractor` | OCR-Verarbeitung (Tesseract) | Unit-Tests |
| 3 – Batch & Report | `batch_processor` | Dateiliste, XMP-Zuordnung, Parallelverarbeitung | Integrationstests |
| 3 – Batch & Report | `report_generator` | Delta-PDF, HTML-Übersicht, Batch-Report | Integrationstests |
| GUI | Tauri + React | Desktop-Shell, Einzelvergleich, Job-Queue-Verwaltung | Manuell |
| Q | privacy / compliance | Datenschutz, Standalone-Betrieb, Temp-Dateien | Systemtests |

`text_comparator` nimmt zwei normalisierte Textstränge entgegen und liefert ein `CompareResult`-Objekt zurück (u. a. `has_delta`, Delta-Liste mit Seiten-/Positionsangabe).

## 5. Tech-Stack

| Schicht | Technologie | Begründung |
|---|---|---|
| Desktop-Shell | Tauri (Rust + WebView2 / WebKit) | Kein Electron-Overhead; nativer Installer ohne Server-Installation; klein (~10 MB) |
| GUI-Frontend | React 18 + TypeScript | Komponentenbasiert, gute Tauri-Integration |
| GUI-Styling | Tailwind CSS | Utility-first, kein Build-Overhead für eigene CSS-Architektur |
| IPC / API | Tauri-Commands (lokales IPC) | Direkte Rust↔Python-Kommunikation ohne Netzwerk-Socket; keine offenen Ports |
| Core Engine | Python 3.12 | Stärkstes Ökosystem für PDF-Verarbeitung, OCR, Diff-Algorithmen |
| PDF-Extraktion | PyMuPDF (fitz) | Präzise Koordinaten, Spalten- und Tabellenerkennung, Performance |
| PDF alternativ | pdfplumber | Ergänzung für komplexe Tabellen; komplementär zu PyMuPDF nutzbar |
| Text-Diff | diff-match-patch | Semantischer Diff; Toleranz für Whitespace/Umbrüche nach Konfiguration |
| OCR | Tesseract 5 + pytesseract | Vollständig lokal, Open Source; **nur Deutsch (deu)** gebündelt |
| XMP-Metadaten | python-xmp-toolkit / PyMuPDF | Auslesen von Document-IDs für Batch-Zuordnung |
| Batchverarbeitung | Python `multiprocessing` | Parallele Verarbeitung ohne externen Queue-Server |
| Job-Persistenz | SQLite (via `sqlite3` stdlib) | Kein Datenbankserver; Job-History und Status lokal |
| Konfiguration | JSON-Profildateien | Menschenlesbar, versionierbar, einfach per GUI editierbar |
| Report-Erzeugung | PyMuPDF + ReportLab | Delta-Markierung in PDF; HTML-Report als Alternative |
| Lizenzprüfung | Eigene Implementierung (datei-basiert) | Offline-Lizenzschlüssel; keine Cloud-Aktivierung |
| Ziel-Plattformen | macOS + Windows (Cross-Platform) | Entwicklung auf macOS; Auslieferung für beide; Tauri CI/CD mit je eigenem Runner |
| Test-Framework | pytest ≥ 8 + pytest-cov | Coverage-Ziel ≥ 90 % für Schicht 1 |
| Fixture-PDFs | reportlab | Synthetische Test-PDFs ohne echte Kundendaten |

## 6. Getroffene Architekturentscheidungen (verbindlich)

| # | Thema | Entscheidung | Konsequenz |
|---|---|---|---|
| 1 | Tauri-IPC-Protokoll | Tauri Sidecar-Prozess | Python wird von Tauri als Kind-Prozess gestartet; kein offener Netzwerk-Port |
| 2 | Python-Distribution | PyInstaller | Python-Runtime wird in .exe/.app eingebettet (~50 MB); kein separater Python-Installer beim Kunden |
| 3 | OCR-Sprachmodelle | Nur Deutsch (deu) | Kleineres Paket; andere Sprachen entfallen (Erweiterung wäre späteres Change Request) |
| 4 | Report-Format | PDF als primäres Format | HTML entfällt als Default, bleibt konfigurierbare Alternative |
| 5 | Lizenzmodell | Offline-Lizenzschlüssel (datei-basiert) | Lizenzprüfung vollständig lokal; Lizenzdatei wird beim Start gelesen |
| 6 | Betriebssystem | Cross-Platform von Anfang an (macOS + Windows) | Entwicklung auf macOS, Auslieferung für beide; CI/CD baut beide Targets |
| 7 | Update-Mechanismus | Manueller Installer-Download | Kein Update-Server nötig; kein Telemetrie-Risiko |

**Warum Tauri statt Electron:** systemeigenes WebView (WebView2/WebKit) statt gebündeltem Chromium → Installer ~10 MB statt ~150 MB, geringerer RAM-Verbrauch, Memory-Safety durch Rust ohne GC, native Installer-Erzeugung (.msi/.exe/.dmg) out of the box. WebView2 ist auf Windows 11 vorinstalliert, auf Windows 10 kommt es automatisch per Windows Update — kein manueller Schritt beim Kunden nötig.

## 7. Verzeichnisstruktur (verbindlich)

```
papertrail-compare/
├── src-tauri/          # Tauri/Rust Shell
├── src/                # React/TypeScript GUI
├── engine/             # Python Core Engine
│   ├── text_comparator.py
│   ├── pdf_extractor.py
│   ├── region_filter.py
│   ├── page_group_detector.py
│   ├── profile_loader.py
│   ├── batch_processor.py
│   └── report_generator.py
├── tests/
│   ├── fixtures/       # Synthetische PDFs (reportlab)
│   └── test_*.py
└── profiles/           # JSON-Vergleichsprofile
```

Neue Python-Module der Core Engine gehören nach `engine/`, zugehörige Tests nach `tests/test_<modulname>.py`. GUI-Code (React/TS) gehört nach `src/`, Tauri-/Rust-Code nach `src-tauri/`. JSON-Vergleichsprofile gehören nach `profiles/`.

## 8. Test- und Fixture-Regeln

- **Niemals echte Kundendokumente als Testdaten verwenden** — ausschließlich synthetisch erzeugte Fixture-PDFs (via reportlab).
- Fixtures liegen versioniert unter `tests/fixtures/` und dokumentieren gleichzeitig die Anforderungen (Fixture = lebende Spezifikation).
- Testfall-IDs folgen dem Schema `TC-<Modulkürzel>-<Nummer>` (z. B. `TC-T-001` für `text_comparator`, `TC-E-*` für `region_filter`, `TC-G-*` für `page_group_detector`, `TC-O-*` für `ocr_extractor`, `TC-P-*` für `profile_loader`, `TC-B-*` für `batch_processor`, `TC-R-*` für `report_generator`, `TC-S-*` für privacy/compliance).
- Priorität steuert Implementierungsreihenfolge:
  - **P1 – Muss:** Kernfunktionalität, TDD-Einstieg, blockiert andere Tests bei Fehlschlag.
  - **P2 – Soll:** wichtig für Produktionsreife, nach P1 umzusetzen.
  - **P3 – Kann:** Nice-to-have, optional.
- Vollständige Testfall-Matrix (32 Testfälle: 18×P1, 13×P2, 1×P3) ist in `PaperTrailCompare_Testspezifikation.docx` dokumentiert — bei Implementierung eines Moduls immer zuerst die zugehörigen Testfälle aus diesem Dokument als Grundlage nehmen (Test-First / TDD).
- Datenschutz-Tests (TC-S-001 bis TC-S-003) sind Systemtests auf frischer Maschine ohne Internetverbindung.
- Schicht 1 wird ausschließlich mit Unit-Tests abgedeckt (`pytest.mark.parametrize`), Schicht 3 mit Integrationstests, GUI-Tests erfolgen manuell.

## 9. Arbeitsweise für Claude Code

1. **TDD strikt einhalten:** Erst den (fehlschlagenden) Test aus der Testspezifikation schreiben bzw. übernehmen, dann die Implementierung, die ihn grün macht.
2. **Reihenfolge:** Schicht 1 (`text_comparator`, `pdf_extractor`, `region_filter`) vollständig mit P1-Tests grün, bevor Schicht 2 begonnen wird; danach Schicht 3; GUI/Tauri-Integration zuletzt bzw. parallel, sobald die Engine-Commands stehen.
3. Bei jedem neuen Modul zuerst in der Testspezifikation nachsehen, welche Testfälle (ID, Vorbedingung, erwartetes Ergebnis) dafür vorgesehen sind, und diese als Ausgangspunkt für die pytest-Tests verwenden.
4. **Keine Netzwerkzugriffe** in Produktivcode einbauen (siehe Abschnitt 2) — das gilt auch für Hilfsbibliotheken, Update-Checks o. Ä. Kommunikation GUI ↔ Engine nur über Tauri-Commands (Sidecar-Prozess), nie über Netzwerk-Sockets.
5. Bei Unsicherheit zwischen mehreren möglichen Implementierungen: diejenige wählen, die den Betrieb **ohne Server und rein lokal** unterstützt, und die zur Verzeichnisstruktur in Abschnitt 7 passt.
6. Coverage-Ziel für Schicht 1 beachten: ≥ 90 %.
7. GUI-Code (React/TS in `src/`, Rust/Tauri in `src-tauri/`) nicht mit automatisierten Tests überfrachten — die GUI wird laut Spezifikation manuell getestet.
8. Python-Distribution ist auf PyInstaller ausgelegt (Abschnitt 6, #2) — keine Annahmen treffen, die eine separate Python-Installation beim Kunden voraussetzen.
9. OCR-Funktionalität nur für Deutsch (`deu`-Sprachmodell) implementieren/bündeln, sofern nicht explizit anders beauftragt.

## 10. Referenzdokumente im Projekt

- `Projektbeschreibung` — Management Summary, Funktionsumfang.
- `Rahmenbedingungen` — Zielgruppe, rechtliche und technische Vorgaben.
- `PaperTrailCompare_Testspezifikation.docx` — vollständige Testfall-Matrix (Quelle der Wahrheit für alle Testfälle).
- `PaperTrailCompare_Architekturspezifikation.docx` — Architektur, Tech-Stack, Verzeichnisstruktur, getroffene Architekturentscheidungen (Quelle der Wahrheit für alle technischen Entscheidungen).

Diese CLAUDE.md ist eine Verdichtung dieser Dokumente. Bei Widersprüchen oder Detailfragen gelten die Originaldokumente als maßgeblich.

.