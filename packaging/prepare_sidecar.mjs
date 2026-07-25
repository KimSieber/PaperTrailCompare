#!/usr/bin/env node
// Einziger Einstiegspunkt, über den tauri.conf.json den Sidecar-Slot
// (src-tauri/binaries/papertrail-engine-<target-triple>) befüllt - für
// Dev UND Release, damit nie wieder manuell zwischen Dev-Wrapper und
// echtem PyInstaller-Sidecar umgeschaltet werden muss (siehe Bugreport:
// genau das manuelle Umschalten wurde vergessen, der Dev-Wrapper landete
// im Release-Bundle).
//
// --dev   : schreibt packaging/dev_sidecar.sh (schnell, kein PyInstaller)
// --build : baut den echten PyInstaller-Sidecar (packaging/build_sidecar.py)
//
// Node statt direktem Python-Aufruf in tauri.conf.json, weil Node hier
// ohnehin Pflicht ist (npm/tauri-cli) und plattformunabhängig zwischen
// "python3" (macOS/Linux) und "python" (Windows, siehe actions/setup-python)
// wählen kann, ohne dass tauri.conf.json selbst Shell-spezifisch werden muss.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.dirname(__dirname);
const mode = process.argv[2];

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.error) {
    throw result.error;
  }
  return result.status ?? 1;
}

// Bevorzugt den Projekt-.venv-Python (dort ist PyInstaller installiert,
// siehe pyproject.toml [build]-Extra) statt eines bloßen "python3"/"python"
// aus dem PATH - sonst landet man je nach Aufrufkontext (z.B. `tauri build`
// ohne aktivierte venv) beim System-Python ohne PyInstaller, siehe
// Bugreport: genau das ließ den ersten lokalen Build-Versuch fehlschlagen.
function resolvePython() {
  const venvPython = process.platform === "win32"
    ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".venv", "bin", "python");
  if (existsSync(venvPython)) {
    return venvPython;
  }
  return process.platform === "win32" ? "python" : "python3";
}

let exitCode;
if (mode === "--dev") {
  const script = path.join(__dirname, "dev_sidecar.sh");
  exitCode = run("bash", [script]);
} else if (mode === "--build") {
  const pythonCmd = resolvePython();
  const script = path.join(__dirname, "build_sidecar.py");
  exitCode = run(pythonCmd, [script]);
} else {
  console.error(`prepare_sidecar.mjs: unbekannter Modus '${mode}' - erwartet --dev oder --build.`);
  exitCode = 1;
}

process.exit(exitCode);
