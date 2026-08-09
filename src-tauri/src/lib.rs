// file:    src-tauri/src/lib.rs
// purpose: Tauri command handlers for the desktop shell: document comparison,
//          batch processing, profile directory/dropdown management, and
//          sidecar process management. All GUI-to-engine communication
//          flows through here.
// author:  Kim Sieber
// created: YYYY-MM-DD
// changed: 2026-08-09

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tauri::{Emitter, Manager};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// Entspricht 1:1 engine.text_comparator.Delta (siehe engine/__main__.py
/// `compare --json`) – keine eigenen Feldnamen, damit die JSON-Ausgabe der
/// Engine ohne Übersetzungsschicht deserialisiert werden kann.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct Delta {
    page: u32,
    position: u32,
    ref_text: String,
    cnd_text: String,
}

/// Entspricht 1:1 engine.text_comparator.CompareResult, ergänzt um den Pfad
/// des von der Engine erzeugten Delta-Report-PDFs (--report).
#[derive(Debug, Clone, Serialize, Deserialize)]
struct CompareOutput {
    has_delta: bool,
    deltas: Vec<Delta>,
    report_path: Option<String>,
}

/// Persistierte App-Konfiguration (nicht zu verwechseln mit einem
/// engine.profile_loader.Profile - das ist ein Vergleichsprofil, dies hier
/// ist reine Tauri-Shell-Konfiguration). Liegt als app_config.json im
/// App-Konfigurationsverzeichnis, siehe app_config_path.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct AppConfig {
    profile_directory: Option<String>,
}

/// Pfad der persistierten App-Konfiguration im App-Konfigurationsverzeichnis
/// (macOS: ~/Library/Application Support/<bundle-id>/, Windows:
/// %APPDATA%/<bundle-id>/). Bewusst ein eigener Dateiname (nicht
/// "profile.json") - das war früher ein engine-Vergleichsprofil, hier geht
/// es nur um das konfigurierte Profilverzeichnis.
fn app_config_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("app_config.json"))
}

/// Lädt die persistierte App-Konfiguration; liefert Defaults (kein
/// Profilverzeichnis konfiguriert), falls noch keine app_config.json
/// existiert (z.B. beim allerersten Programmstart).
fn read_app_config(app: &tauri::AppHandle) -> Result<AppConfig, String> {
    let path = app_config_path(app)?;
    if !path.exists() {
        return Ok(AppConfig::default());
    }
    let raw = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&raw).map_err(|e| e.to_string())
}

/// Liefert das konfigurierte Profilverzeichnis (Settings-Reiter: Text-Feld +
/// "Durchsuchen..."-Button), oder None, falls noch keins gewählt wurde.
#[tauri::command]
fn get_profile_directory(app: tauri::AppHandle) -> Result<Option<String>, String> {
    Ok(read_app_config(&app)?.profile_directory)
}

/// Persistiert das gewählte Profilverzeichnis in app_config.json.
#[tauri::command]
fn set_profile_directory(app: tauri::AppHandle, path: String) -> Result<(), String> {
    let config_path = app_config_path(&app)?;
    let config = AppConfig {
        profile_directory: Some(path),
    };
    let json = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
    std::fs::write(&config_path, json).map_err(|e| e.to_string())
}

/// Listet alle .json-Dateinamen (ohne Pfad) im konfigurierten
/// Profilverzeichnis - Grundlage für das Profil-Dropdown in Einzel- und
/// Batch-Vergleich. Liefert eine leere Liste, falls kein Verzeichnis
/// konfiguriert ist oder es nicht (mehr) existiert, statt einen Fehler zu
/// werfen - das Dropdown zeigt in dem Fall einfach nur "Kein Profil".
#[tauri::command]
fn list_profiles(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    let Some(dir) = read_app_config(&app)?.profile_directory else {
        return Ok(Vec::new());
    };
    let entries = match std::fs::read_dir(&dir) {
        Ok(entries) => entries,
        Err(_) => return Ok(Vec::new()),
    };
    let mut names: Vec<String> = entries
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.path().extension().and_then(|ext| ext.to_str()) == Some("json"))
        .filter_map(|entry| entry.file_name().to_str().map(|s| s.to_string()))
        .collect();
    names.sort();
    Ok(names)
}

/// Konstruiert den vollen Profilpfad aus dem konfigurierten Profilverzeichnis
/// und dem in der GUI gewählten Dateinamen - None, falls kein Profil
/// ausgewählt wurde (Dropdown = "Kein Profil"), dann greifen die
/// Engine-Defaults (siehe engine/__main__.py).
fn resolve_profile_path(
    app: &tauri::AppHandle,
    profile_name: &Option<String>,
) -> Result<Option<PathBuf>, String> {
    let Some(name) = profile_name else {
        return Ok(None);
    };
    if name.is_empty() {
        return Ok(None);
    }
    let Some(dir) = read_app_config(app)?.profile_directory else {
        return Err("Kein Profilverzeichnis konfiguriert".to_string());
    };
    Ok(Some(Path::new(&dir).join(name)))
}

/// Verzeichnis für Vergleichs-Reports unterhalb der Dokumente des Nutzers
/// (macOS: ~/Documents/PaperTrailCompare/, Windows: Eigene
/// Dokumente\PaperTrailCompare\). Reports bleiben dauerhaft erhalten und
/// werden nicht automatisch geleert.
fn reports_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .document_dir()
        .map_err(|e| e.to_string())?
        .join("PaperTrailCompare");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

/// Ersetzt alle Zeichen, die nicht auf jedem Zielbetriebssystem in
/// Dateinamen zulässig sind (Leerzeichen, Umlaute, Sonderzeichen), durch
/// Unterstriche, damit der resultierende Report-Pfad sowohl unter macOS als
/// auch unter Windows gültig ist.
fn sanitize_filename_part(name: &str) -> String {
    name.chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
        .collect()
}

/// Dateiname ohne Endung, z. B. "Rechnung_2024_alt.pdf" -> "Rechnung_2024_alt".
fn file_stem_sanitized(path: &str) -> String {
    let stem = Path::new(path)
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| path.to_string());
    sanitize_filename_part(&stem)
}

/// Vergleicht zwei PDF-Dateien textlich über die Python Core Engine
/// (Sidecar-Prozess, siehe CLAUDE.md Architekturentscheidung #1). Ruft
/// `papertrail-engine compare <ref> <cnd> --json --report <pfad>` auf und
/// parst die JSON-Ausgabe in ein typisiertes Ergebnis.
#[tauri::command]
async fn compare_documents(
    app: tauri::AppHandle,
    ref_path: String,
    cnd_path: String,
    profile_name: Option<String>,
) -> Result<CompareOutput, String> {
    let dir = reports_dir(&app)?;

    let ref_name = file_stem_sanitized(&ref_path);
    let cnd_name = file_stem_sanitized(&cnd_path);
    let now = chrono::Local::now();
    let day_dir = dir.join(now.format("%Y-%m-%d").to_string());
    std::fs::create_dir_all(&day_dir).map_err(|e| e.to_string())?;
    let timestamp = now.format("%Y-%m-%d_%H-%M");
    let report_path = day_dir.join(format!("{ref_name}_{cnd_name}_{timestamp}.pdf"));
    let report_path_str = report_path.to_string_lossy().to_string();

    let sidecar = app
        .shell()
        .sidecar("papertrail-engine")
        .map_err(|e| e.to_string())?;

    let mut cli_args = vec![
        "compare".to_string(),
        ref_path.clone(),
        cnd_path.clone(),
        "--json".to_string(),
        "--report".to_string(),
        report_path_str.clone(),
    ];
    if let Some(profile_path) = resolve_profile_path(&app, &profile_name)? {
        cli_args.push("--profile".to_string());
        cli_args.push(profile_path.to_string_lossy().to_string());
    }

    let output = sidecar
        .args(cli_args)
        .output()
        .await
        .map_err(|e| e.to_string())?;

    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }

    serde_json::from_slice::<CompareOutput>(&output.stdout).map_err(|e| e.to_string())
}

/// Entspricht 1:1 engine.text_comparator.CompareResult (ohne report_path,
/// der existiert bei Batch-Paaren nicht) - Teil von BatchPairResult.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BatchCompareResult {
    has_delta: bool,
    deltas: Vec<Delta>,
    ocr_was_used: bool,
}

/// Entspricht 1:1 engine.models.PairResult (siehe engine/__main__.py
/// `batch --json-lines` bzw. die "progress"-Zeilen von `batch`).
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BatchPairResult {
    ref_path: String,
    cnd_path: String,
    status: String,
    compare_result: Option<BatchCompareResult>,
    error: Option<String>,
    total_pages: Option<u32>,
}

/// Payload des an das Frontend emittierten "batch-progress"-Events - 1:1 zur
/// "progress"-JSON-Zeile des Sidecar-Prozesses (siehe engine/__main__.py
/// `_run_batch`), abzüglich des Discriminator-Felds "type".
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BatchProgressEvent {
    index: u32,
    total: u32,
    pair: BatchPairResult,
}

/// Ergebnis von start_batch_compare nach Abschluss des gesamten Batch-Laufs -
/// 1:1 zur abschließenden "done"-JSON-Zeile des Sidecar-Prozesses.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BatchOutput {
    ok_count: u32,
    error_count: u32,
    report_path: String,
}

/// Startet den Massenvergleich über die Python Core Engine (Sidecar-Prozess,
/// `papertrail-engine batch <filelist.csv> --output-dir <dir>`) und emittiert
/// pro verarbeitetem Paar ein "batch-progress"-Event Richtung Frontend.
///
/// Anders als compare_documents (sidecar.output(), wartet auf vollständige
/// Prozessbeendigung) wird hier sidecar.spawn() verwendet: der Sidecar-
/// Prozess streamt pro Paar sofort eine JSON-Zeile auf stdout (siehe
/// engine/__main__.py `_run_batch`), die hier zeilenweise gelesen und als
/// Tauri-Event weitergereicht wird - erst so ist Live-Progress ohne
/// Frontend-Polling-Schleife möglich (siehe prompt_batch_verarbeitung.md,
/// "Live-Progress via Tauri-Events").
///
/// workers bleibt bewusst auf 1 (sequentiell) beschränkt - siehe
/// prompt_batch_verarbeitung.md, "Nicht Teil dieser Session": workers>1 wird
/// erst in einem späteren Schritt an die GUI angebunden.
#[tauri::command]
async fn start_batch_compare(
    app: tauri::AppHandle,
    filelist_path: String,
    output_dir: String,
    profile_name: Option<String>,
) -> Result<BatchOutput, String> {
    let sidecar = app
        .shell()
        .sidecar("papertrail-engine")
        .map_err(|e| e.to_string())?;

    let mut cli_args = vec![
        "batch".to_string(),
        filelist_path,
        "--output-dir".to_string(),
        output_dir,
    ];
    if let Some(profile_path) = resolve_profile_path(&app, &profile_name)? {
        cli_args.push("--profile".to_string());
        cli_args.push(profile_path.to_string_lossy().to_string());
    }

    let (mut rx, mut _child) = sidecar.args(cli_args).spawn().map_err(|e| e.to_string())?;

    let mut stderr_output = String::new();
    let mut done_output: Option<BatchOutput> = None;

    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line_bytes) => {
                let line = String::from_utf8_lossy(&line_bytes);
                let Ok(value) = serde_json::from_str::<serde_json::Value>(line.trim()) else {
                    continue;
                };
                match value.get("type").and_then(|t| t.as_str()) {
                    Some("progress") => {
                        if let Ok(progress) = serde_json::from_value::<BatchProgressEvent>(value) {
                            let _ = app.emit("batch-progress", progress);
                        }
                    }
                    Some("done") => {
                        if let Ok(done) = serde_json::from_value::<BatchOutput>(value) {
                            done_output = Some(done);
                        }
                    }
                    _ => {}
                }
            }
            CommandEvent::Stderr(bytes) => {
                stderr_output.push_str(&String::from_utf8_lossy(&bytes));
            }
            CommandEvent::Terminated(payload) => {
                if payload.code != Some(0) {
                    return Err(if stderr_output.is_empty() {
                        format!("Batch-Verarbeitung fehlgeschlagen (Exit-Code {:?})", payload.code)
                    } else {
                        stderr_output.trim().to_string()
                    });
                }
            }
            _ => {}
        }
    }

    done_output.ok_or_else(|| "Batch-Verarbeitung lieferte kein Ergebnis".to_string())
}

/// Startet die Python Core Engine als Sidecar-Prozess (Kind-Prozess, kein
/// Netzwerk-Socket) und gibt deren stdout zurück. Kommunikation läuft
/// ausschließlich über Prozessargumente/stdout – siehe CLAUDE.md
/// Architekturentscheidung #1 (Tauri Sidecar-Prozess statt Netzwerk-IPC).
///
/// Der Sidecar-Binärname "papertrail-engine" muss auf die in
/// tauri.conf.json unter bundle.externalBin deklarierte Datei passen; für
/// die Auslieferung wird das die PyInstaller-gebündelte Engine sein
/// (Architekturentscheidung #2). Siehe src-tauri/binaries/README.md für
/// den aktuellen Entwicklungsstand.
#[tauri::command]
async fn engine_version(app: tauri::AppHandle) -> Result<String, String> {
    let sidecar = app
        .shell()
        .sidecar("papertrail-engine")
        .map_err(|e| e.to_string())?;

    let output = sidecar
        .args(["--version"])
        .output()
        .await
        .map_err(|e| e.to_string())?;

    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            engine_version,
            compare_documents,
            start_batch_compare,
            get_profile_directory,
            set_profile_directory,
            list_profiles
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, _event| {});
}
