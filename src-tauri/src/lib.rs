// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::Manager;
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

/// Verzeichnis für Vergleichs-Reports innerhalb des App-Caches (nicht neben
/// den Kundendokumenten, da deren Ablageort ggf. nicht beschreibbar sein
/// soll oder nicht mit Zusatzdateien versehen werden darf).
fn reports_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_cache_dir()
        .map_err(|e| e.to_string())?
        .join("reports");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

/// Entfernt alle Dateien im Report-Verzeichnis. Reports enthalten
/// Kundendokument-Inhalte (Delta-Markierungen aus Referenz- und
/// Kandidat-PDF) und müssen daher vollständig bereinigt werden (TC-S-002) –
/// beim App-Start (verwaiste Reports nach Absturz/hartem Beenden), beim
/// App-Exit und vor jedem neuen Vergleich.
fn clear_reports_dir(dir: &Path) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let _ = std::fs::remove_file(entry.path());
    }
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
) -> Result<CompareOutput, String> {
    let dir = reports_dir(&app)?;
    clear_reports_dir(&dir);

    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_nanos();
    let report_path = dir.join(format!("report-{timestamp}.pdf"));
    let report_path_str = report_path.to_string_lossy().to_string();

    let sidecar = app
        .shell()
        .sidecar("papertrail-engine")
        .map_err(|e| e.to_string())?;

    let output = sidecar
        .args([
            "compare",
            &ref_path,
            &cnd_path,
            "--json",
            "--report",
            &report_path_str,
        ])
        .output()
        .await
        .map_err(|e| e.to_string())?;

    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }

    serde_json::from_slice::<CompareOutput>(&output.stdout).map_err(|e| e.to_string())
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
        .setup(|app| {
            // Verwaiste Reports aus einer vorherigen Sitzung entfernen (z. B.
            // nach Absturz oder hartem Beenden) – TC-S-002.
            if let Ok(dir) = reports_dir(app.handle()) {
                clear_reports_dir(&dir);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            engine_version,
            compare_documents
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Ok(dir) = reports_dir(app_handle) {
                    clear_reports_dir(&dir);
                }
            }
        });
}
