# Windows Build Readiness — Analyse (Stand: 2026-07-30)

Reine Bestandsaufnahme, keine Codeänderungen. Ziel: unsignierter Windows-Installer (MSI/NSIS) via GitHub Actions `windows-latest`. Bisher wurde noch nie ein Windows-Build tatsächlich ausgeführt — der Workflow selbst enthält bereits einen Hinweis darauf ([build.yml:12-16](.github/workflows/build.yml#L12-L16)).

## 1. GitHub Actions Workflow ([.github/workflows/build.yml](.github/workflows/build.yml))

| Punkt | Befund | Risiko | Empfehlung |
|---|---|---|---|
| Trigger | `push` auf `main`, `pull_request`, `workflow_dispatch` — unauffällig | low | — |
| Matrix | `macos-latest`/`aarch64-apple-darwin` + `windows-latest`/`x86_64-pc-windows-msvc`, `fail-fast: false` | low | — |
| Tauri-Action | Kein `tauri-apps/tauri-action` im Einsatz; Build läuft manuell über `npm run tauri build` (ruft `@tauri-apps/cli` aus `package.json` auf, Version `^2`) | low | Falls später doch die offizielle Action gewünscht wird, separat prüfen — aktuell funktioniert der manuelle Weg plattformunabhängig identisch. |
| Python-Sidecar-Zeitpunkt | Wird **nicht** als eigener Workflow-Schritt gebaut, sondern indirekt über `tauri.conf.json:beforeBuildCommand` → `npm run sidecar:build` → `packaging/prepare_sidecar.mjs --build` → `packaging/build_sidecar.py`, ausgelöst innerhalb des Schritts "Build Tauri app" ([build.yml:75-78](.github/workflows/build.yml#L75-L78)) | medium | Funktional korrekt (kein CI-spezifischer Sonderpfad), aber macht Fehler im Sidecar-Build schwerer lokalisierbar (kein eigenes CI-Log-Segment, kein Caching-Ansatzpunkt). Für Windows-Erstlauf ggf. temporär als eigenen Step ausführen, um Fehler klarer zuzuordnen. |
| Tesseract (Windows) | `choco install tesseract --version=5.3.3.20231005 -y`, explizit als **ungetestet** markiert; `deu`-Sprachmodell wird von diesem Choco-Paket möglicherweise nicht mitgeliefert | high | Vor dem ersten echten Lauf verifizieren, ob `deu.traineddata` im choco-Paket enthalten ist; falls nicht, zusätzlichen Download-Schritt von `tessdata` (offline/vendored, keine Laufzeit-Netzwerkabhängigkeit!) ergänzen. |
| Python-Version | `actions/setup-python@v5` mit `"3.13"`, während `pyproject.toml` `requires-python = ">=3.12"` fordert — kein Widerspruch, aber ungetestete Kombination unter Windows | medium | Auf `3.12` fixieren oder bewusst mit `3.13` gegen alle Abhängigkeiten (insb. PyMuPDF-Wheels) testen. |
| Artifact-Upload | Pfadmuster erfasst `*.dmg`, `*.msi`, `*.exe`; `if-no-files-found: warn` statt `error` | medium | Auf `error` setzen, damit ein fehlgeschlagener Windows-Bundle-Schritt nicht stillschweigend als "kein Artefakt" durchrutscht. |
| NSIS explizit | Kein expliziter NSIS-Ziel-Schritt — `bundle.targets: "all"` in `tauri.conf.json` entscheidet, ob NSIS/MSI erzeugt werden | low | Siehe Punkt 2. |

## 2. Tauri-Konfiguration ([src-tauri/tauri.conf.json](src-tauri/tauri.conf.json))

| Punkt | Befund | Risiko | Empfehlung |
|---|---|---|---|
| `bundle.targets` | `"all"` — erzeugt auf Windows sowohl MSI als auch NSIS automatisch, kein Einschränken nötig | low | Falls nur eines der beiden gewünscht ist, auf `["msi"]` bzw. `["nsis"]` einschränken; sonst unverändert lassen. |
| `bundle.externalBin` | `["binaries/papertrail-engine"]` registriert — Tauri hängt selbst `-<target-triple>[.exe]` an und erwartet exakt diese Datei | low | Konsistent mit `build_sidecar.py`, siehe Punkt 3. |
| Erwarteter Dateiname | `src-tauri/binaries/papertrail-engine-x86_64-pc-windows-msvc.exe` (Tauri hängt `.exe` unter Windows automatisch an den in `externalBin` konfigurierten Basisnamen + Target-Triple an) | medium | Noch nie tatsächlich erzeugt/verifiziert — beim ersten Windows-Lauf genau diesen Dateinamen im Build-Log/Artefakt prüfen. |
| `bundle.resources` | Nicht definiert (Feld fehlt komplett) | low | Tesseract-Binary/tessdata werden bereits über PyInstaller ins Sidecar-Exe gebündelt (`papertrail-engine.spec`), nicht über Tauri-`resources` — konsistent, kein zusätzlicher Bedarf erkennbar. |
| `webviewInstallMode` | Nicht konfiguriert (Tauri-Default für Windows: `downloadBootstrapper`) | medium | Default lädt WebView2-Bootstrapper bei Installation herunter — das ist ein **Netzwerkzugriff während der Installation** auf einer Maschine ohne vorhandenes WebView2, was CLAUDE.md Abschnitt 2 ("kein ausgehender Netzwerkverkehr während der Verarbeitung") zumindest im Geiste widerspricht, auch wenn es sich um die Installation und nicht die Dokumentenverarbeitung handelt. Empfehlung: `webviewInstallMode` explizit auf `embedBootstrapper` oder `offlineInstaller` setzen, um jede Netzwerkabhängigkeit bei der Installation auszuschließen (Installer wird dadurch größer). |
| `icons/icon.ico` | Ist in `bundle.icon` gelistet | low | Nur verifizieren, dass die Datei tatsächlich unter `src-tauri/icons/icon.ico` existiert (nicht per Workflow-Analyse geprüft). |

## 3. Sidecar-Build ([packaging/build_sidecar.py](packaging/build_sidecar.py), [packaging/papertrail-engine.spec](packaging/papertrail-engine.spec))

| Punkt | Befund | Risiko | Empfehlung |
|---|---|---|---|
| Pfadbehandlung allgemein | Durchgehend `pathlib.Path`, keine String-Konkatenation mit `/` oder hartkodierte POSIX-Pfade | low | — |
| Target-Triple/Output-Name | `sidecar_name = f"papertrail-engine-{target_triple}"`, `.exe`-Suffix wird korrekt via `platform.system() == "Windows"` angehängt ([build_sidecar.py:175](packaging/build_sidecar.py#L175)) — triple-konform zu `bundle.externalBin` | low | — |
| `chmod(0o755)` | Wird nur ausgeführt, wenn `platform.system() != "Windows"` ([build_sidecar.py:217-218](packaging/build_sidecar.py#L217-L218)) | low | Korrekt behandelt (chmod auf Windows sinnlos/fehleranfällig). |
| `_stage_tesseract_windows` | Kopiert pauschal alle `.exe`/`.dll` aus dem Tesseract-Installationsverzeichnis (`install_dir.iterdir()`, nicht rekursiv) neben die Sidecar-Binary; explizit als **ungetestet** kommentiert | high | Choco-Tesseract-Installationen legen häufig Unterordner an (z. B. `tessdata` separat, ggf. weitere DLL-Abhängigkeiten in Unterverzeichnissen wie `libs/`) — die flache `iterdir()`-Kopie könnte Abhängigkeiten übersehen. Beim ersten Windows-Lauf das tatsächliche Choco-Installationslayout prüfen und ggf. rekursiv/gezielt kopieren. |
| `_find_tessdata_deu` Windows-Kandidat | Nutzt `tesseract_symlink.resolve().parent / "tessdata"` ([build_sidecar.py:72](packaging/build_sidecar.py#L72)) — passt zum Standard-Tesseract-Installer-Layout, aber choco installiert ggf. an einem anderen Pfad (`C:\ProgramData\chocolatey\lib\tesseract\...` vs. `C:\Program Files\Tesseract-OCR\`) | medium | Prüfen, ob `shutil.which("tesseract")` nach `choco install` überhaupt einen PATH-Eintrag liefert, der zu diesem Kandidatenpfad führt; ansonsten Kandidatenliste um choco-typische Pfade erweitern. |
| `_run_pyinstaller` / `sys.executable` | Plattformunabhängig, kein Shell-Aufruf (`subprocess.run([...])` mit Listenargumenten statt `shell=True`) | low | — |
| `rustc -vV` Aufruf | Setzt voraus, dass `rustc` im PATH ist — via `dtolnay/rust-toolchain@stable` im Workflow sichergestellt | low | — |
| PyInstaller-Spec | Rein deklarativ, keine plattformspezifischen Pfad-Strings; `collect_all` für `pymupdf`/`pypdfium2` behandelt beide Plattformen gleich | low | Beim ersten Windows-Lauf prüfen, ob PyInstaller alle nativen PyMuPDF-DLLs findet (bekannte Stolperfalle laut Kommentar im Spec selbst). |

## 4. Tesseract/OCR-Erkennung zur Laufzeit ([engine/ocr_extractor.py](engine/ocr_extractor.py))

| Punkt | Befund | Risiko | Empfehlung |
|---|---|---|---|
| Bundle-Fall (`sys.frozen`) | `pytesseract.tesseract_cmd` wird explizit auf `<MEIPASS>/tesseract/bin/tesseract.exe` (Windows) bzw. `.../tesseract` (sonst) gesetzt, `TESSDATA_PREFIX` auf `<MEIPASS>/tesseract/tessdata` ([ocr_extractor.py:37-42](engine/ocr_extractor.py#L37-L42)) — korrekt plattformabhängig über `sys.platform == "win32"` | low | — |
| Dev-Fall (`sys.frozen` nicht gesetzt) | Fällt auf pytesseract-Standardverhalten zurück = PATH-Suche nach `tesseract` | medium | Für lokale Windows-Entwicklung (außerhalb des Bundles) muss Tesseract manuell installiert und im PATH sein — laut Kommentar bereits so in README dokumentiert, nicht separat verifiziert in dieser Analyse. |
| Fehlerverhalten bei fehlendem Tesseract | Kein expliziter Try/Except um den `pytesseract.image_to_string`-Aufruf; bei fehlender/falscher Binary wirft pytesseract `TesseractNotFoundError` bzw. `subprocess`-Fehler ungefangen durch bis zum Aufrufer | medium | Kein sauberer Fallback vorhanden — ein fehlerhaftes Windows-Tesseract-Staging (siehe Punkt 3) würde zur Laufzeit mit einer rohen Exception abbrechen statt mit einer verständlichen Fehlermeldung. Da OCR aber laut CLAUDE.md nur ein Teilfeature ist, wäre ein gezielter Catch mit klarer Fehlermeldung ("OCR nicht verfügbar") sinnvoll, ist aber kein Blocker für den reinen Build. |

## 5. Plattformabhängige Pfade — Python-Engine & Rust ([src-tauri/src/lib.rs](src-tauri/src/lib.rs))

| Punkt | Befund | Risiko | Empfehlung |
|---|---|---|---|
| Python-Engine allgemein | Durchgehend `pathlib.Path` in `batch_processor.py`, `report_generator.py`, `profile_loader.py`, `__main__.py`; keine hartkodierten `/`-Konkatenationen, kein `/tmp`, kein `os.path.join("/...")` gefunden | low | — |
| Temp-Dateien | Kein `tempfile`-Modul im Engine-Code im Einsatz (keine Treffer) | low | Sofern Zwischendateien anderswo (z. B. GUI/Rust-Seite) entstehen, separat prüfen — außerhalb des Scopes dieser Python-fokussierten Prüfung. |
| Ausgabeverzeichnis "Documents" | `reports_dir()` in Rust nutzt `app.path().document_dir()` (Tauri-API, löst das OS-"Known Folder" auf) statt hartkodiertem `~/Documents` ([lib.rs:118-126](src-tauri/src/lib.rs#L118-L126)) | low | Korrekt implementiert — `document_dir()` fragt unter Windows den tatsächlichen (ggf. durch OneDrive umgeleiteten) Dokumente-Pfad über die Windows-Known-Folder-API ab, kein Hardcoding auf `C:\Users\<user>\Documents`. Keine Änderung nötig, aber beim ersten Windows-Test explizit mit OneDrive-umgeleitetem Dokumente-Ordner verifizieren. |
| Dateinamen-Sanitizing | `sanitize_filename_part()` ersetzt alles außer ASCII-Alphanumerisch durch `_` ([lib.rs:132-136](src-tauri/src/lib.rs#L132-L136)) — deckt Windows-verbotene Zeichen (`\ / : * ? " < > \|`) sowie Umlaute ab | low | — |
| `prepare_sidecar.mjs` | Wählt `.venv/Scripts/python.exe` vs. `.venv/bin/python` korrekt über `process.platform === "win32"` ([prepare_sidecar.mjs:34-40](packaging/prepare_sidecar.mjs#L34-L40)) | low | — |
| `dev_sidecar.sh` (Dev-Fallback) | Ist ein Bash-Skript, wird im Workflow aber nicht für Release-Builds verwendet (`--build`-Modus ruft `build_sidecar.py` auf, nicht `dev_sidecar.sh`) | low | Für Windows-Entwicklung außerhalb WSL/Git-Bash müsste `sidecar:dev` ggf. gesondert betrachtet werden — betrifft nicht den CI-Release-Build. |

## 6. Python-Abhängigkeiten ([pyproject.toml](pyproject.toml))

| Paket | Windows-Wheel-Verfügbarkeit (Py 3.12/3.13) | Risiko | Empfehlung |
|---|---|---|---|
| `pymupdf` | Bietet offizielle Windows-Wheels (`cp312`/`cp313`, `win_amd64`) auf PyPI | low | — |
| `pdfplumber` | Reines Python, zieht `pypdfium2` (hat Windows-Wheels) als native Abhängigkeit | low | — |
| `pytesseract` | Reines Python (nur Wrapper, ruft externe `tesseract`-Binary auf) — keine native Kompilierung nötig | low | Die eigentliche Systemabhängigkeit ist die Tesseract-Binary selbst, nicht das Python-Paket, siehe Punkt 3/4. |
| `reportlab` | Bietet Windows-Wheels | low | — |
| `pyinstaller` + `pyinstaller-hooks-contrib` (build-Extra) | Beide unterstützen Windows offiziell | low | — |
| `pytest`, `pytest-cov` (test-Extra) | Reines Python | low | — |
| Gesamtbild | Keines der deklarierten Pakete erfordert eine Systembibliothek (z. B. `libmagic`, `poppler-utils`) außerhalb von Tesseract | low | Kein Blocker erkennbar; tatsächliche Installation (`pip install -e ".[build,test]"`) muss dennoch beim ersten Windows-Lauf verifiziert werden, insbesondere Wheel- vs. Source-Build-Verhalten für `pypdfium2`. |

## 7. Rust/Node-Seite ([src-tauri/Cargo.toml](src-tauri/Cargo.toml), [package.json](package.json))

| Punkt | Befund | Risiko | Empfehlung |
|---|---|---|---|
| Rust-Toolchain | `dtolnay/rust-toolchain@stable` im Workflow — keine Versionspinnung, holt jeweils aktuelles Stable pro Runner-Lauf | medium | Für reproduzierbare Builds (macOS und Windows exakt gleiche Toolchain-Version) ggf. auf eine feste Version pinnen (z. B. `with: { toolchain: "1.8x.x" }|`); aktuell besteht das Risiko, dass ein zukünftiges Rust-Stable-Release den Build auf einer Plattform bricht, ohne dass Code geändert wurde. |
| `Cargo.toml`-Abhängigkeiten | `tauri`, `tauri-plugin-opener`, `tauri-plugin-shell`, `tauri-plugin-dialog`, `serde`, `serde_json`, `chrono` (mit `default-features = false, features = ["clock"]`) — alle offiziell cross-platform, keine POSIX-only-Crates (kein `nix`, `libc`-only-Feature o. Ä.) erkennbar | low | — |
| `crate-type = ["staticlib", "cdylib", "rlib"]` + `name = "papertrail_compare_lib"` | Kommentar im File selbst weist auf ein Windows-spezifisches Cargo-Problem hin (Lib-/Bin-Namenskollision, [rust-lang/cargo#8519](Cargo.toml)) und ist bereits korrekt umgangen | low | Bereits vorausschauend gelöst, keine Aktion nötig. |
| `tauri-plugin-shell` | Wird eingebunden — potenziell relevant für CLAUDE.md-Vorgabe "kein Netzwerk/keine Shell-Hintertüren"; tatsächliche Nutzung im Rust-Code nicht im Rahmen dieser Analyse geprüft | medium | Separat verifizieren, wofür `tauri-plugin-shell` in `lib.rs` tatsächlich verwendet wird (z. B. nur zum Starten des Python-Sidecars, was der Architektur in CLAUDE.md Abschnitt 6 #1 entspricht) und dass keine beliebigen Shell-Kommandos von der GUI aus ausführbar sind. |
| Node-Version | `actions/setup-node@v4` mit `node-version: 20` — LTS, unproblematisch unter Windows | low | — |
| `package.json`-Abhängigkeiten | `@tauri-apps/*`, `react`, `react-dom`, Vite/Tailwind-Toolchain — alle rein JS/TS, keine nativen Node-Addons erkennbar | low | — |
| Lockfiles | `package-lock.json` und `src-tauri/Cargo.lock` sind vorhanden und eingecheckt | low | `npm ci` im Workflow nutzt das Lockfile korrekt ([build.yml:72-73](.github/workflows/build.yml#L72-L73)); Cargo nutzt `Cargo.lock` automatisch. Kein Handlungsbedarf. |

## Zusammenfassung — Top-Risiken vor dem ersten Windows-Lauf

1. **Hoch:** `deu.traineddata` im choco-Tesseract-Paket unklar — größtes Risiko für einen kompletten OCR-Ausfall im Windows-Bundle.
2. **Hoch:** `_stage_tesseract_windows` kopiert flach alle `.exe`/`.dll` — Installationslayout von choco nie gegen den tatsächlichen Code verifiziert.
3. **Mittel:** `webviewInstallMode` nicht gesetzt → Installer lädt WebView2-Bootstrapper per Netzwerk nach, was dem "kein Netzwerkzugriff"-Grundsatz zumindest im Installationskontext widerspricht.
4. **Mittel:** Rust-Toolchain ungepinnt, Python 3.13 in CI vs. `>=3.12` in `pyproject.toml` — beides funktional wahrscheinlich unkritisch, aber nie unter Windows verifiziert.
5. **Mittel:** `if-no-files-found: warn` beim Artifact-Upload verschleiert einen fehlgeschlagenen Windows-Bundle-Schritt.

Alles andere (Pfadbehandlung in Python/Rust, Target-Triple-Namensgebung, Lockfiles, Python-Abhängigkeiten) ist bereits sauber plattformunabhängig implementiert und sollte beim ersten `windows-latest`-Lauf ohne Codeänderung funktionieren — vorausgesetzt, die Tesseract-Kette (Punkte 1–2) hält.
