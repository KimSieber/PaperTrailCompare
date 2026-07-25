// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
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

/// Entspricht dem Ausschnitt von engine.profile_loader.Profile, der über den
/// Einstellungen-Reiter editierbar ist. `version` wird von load_profile()
/// als Pflichtfeld verlangt (siehe engine/profile_loader.py).
#[derive(Debug, Clone, Serialize, Deserialize)]
struct Profile {
    version: String,
    #[serde(default = "default_normalize_whitespace")]
    normalize_whitespace: bool,
}

/// GUI-Default für den Einstellungen-Toggle "Leerzeichen-Toleranz": greift
/// sowohl beim allerersten Start (keine profile.json vorhanden) als auch,
/// falls eine vorhandene profile.json das Feld nicht enthält. Bewusst
/// getrennt vom CLI-/engine.profile_loader.Profile-Default (False, dort
/// weiterhin opt-in).
fn default_normalize_whitespace() -> bool {
    true
}

impl Default for Profile {
    fn default() -> Self {
        Profile {
            version: "1.0".to_string(),
            normalize_whitespace: default_normalize_whitespace(),
        }
    }
}

/// Pfad der persistierten Profildatei im App-Konfigurationsverzeichnis
/// (macOS: ~/Library/Application Support/<bundle-id>/, Windows:
/// %APPDATA%/<bundle-id>/). Diese Datei wird per --profile an den
/// Sidecar-Prozess übergeben, siehe compare_documents.
fn settings_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("profile.json"))
}

/// Lädt die persistierten Einstellungen; liefert Defaults, falls noch keine
/// Profildatei existiert (z.B. beim allerersten Programmstart).
#[tauri::command]
fn load_settings(app: tauri::AppHandle) -> Result<Profile, String> {
    let path = settings_path(&app)?;
    if !path.exists() {
        return Ok(Profile::default());
    }
    let raw = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&raw).map_err(|e| e.to_string())
}

/// Persistiert die Einstellungen aus dem Einstellungen-Reiter als JSON-Profil
/// (engine/profile_loader.py-kompatibel).
#[tauri::command]
fn save_settings(app: tauri::AppHandle, normalize_whitespace: bool) -> Result<(), String> {
    let path = settings_path(&app)?;
    let profile = Profile {
        version: "1.0".to_string(),
        normalize_whitespace,
    };
    let json = serde_json::to_string_pretty(&profile).map_err(|e| e.to_string())?;
    std::fs::write(&path, json).map_err(|e| e.to_string())
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
    let profile_path = settings_path(&app)?;
    if profile_path.exists() {
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
            load_settings,
            save_settings
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, _event| {});
}
