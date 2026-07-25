#!/usr/bin/env bash
# Erzeugt den lokalen Dev-Sidecar-Wrapper unter
# src-tauri/binaries/papertrail-engine-<target-triple> - reproduzierbar
# statt einer handgepflegten, ungetrackten Datei (siehe Bugreport: genau
# das führte dazu, dass dieser Dev-Wrapper unbemerkt im Release-Bundle
# landete). Wird von packaging/prepare_sidecar.mjs vor `tauri dev`
# aufgerufen, nicht manuell.
#
# NIEMALS für Release-Builds verwenden - siehe packaging/build_sidecar.py
# für den echten PyInstaller-Sidecar. tauri.conf.json.beforeBuildCommand
# ruft ausschließlich build_sidecar.py auf und überschreibt diese Datei
# vor jedem `tauri build` bedingungslos.
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET_TRIPLE="$(rustc -vV | awk '/^host:/ {print $2}')"

if [ -z "$TARGET_TRIPLE" ]; then
  echo "dev_sidecar.sh: 'rustc -vV' lieferte kein Target-Triple - ist Rust installiert?" >&2
  exit 1
fi

OUT_PATH="$REPO_ROOT/src-tauri/binaries/papertrail-engine-$TARGET_TRIPLE"
mkdir -p "$(dirname "$OUT_PATH")"

cat > "$OUT_PATH" <<'WRAPPER_EOF'
#!/usr/bin/env bash
# PAPERTRAIL_DEV_SIDECAR_MARKER - siehe packaging/dev_sidecar.sh und
# packaging/build_sidecar.py (Selbst-Check verweigert einen Release-Build,
# falls diese Marker-Zeile in der finalen Sidecar-Datei gefunden wird).
#
# Interims-Wrapper für lokale Entwicklung – ruft die Python-Engine aus dem
# Projekt-.venv auf. NICHT für Release-Builds - siehe
# packaging/build_sidecar.py für den echten PyInstaller-Sidecar.
#
# Pfadauflösung bewusst unabhängig vom Skript-Standort UND ohne
# Git-Abhängigkeit: Tauri/Cargo kopiert dieses Skript beim Build in
# unterschiedliche Verzeichnistiefen (z.B. nach
# src-tauri/target/debug/papertrail-engine). Ausgehend vom aufgelösten
# (symlink-freien) Skriptpfad aufwärts nach dem Projekt-Wurzelverzeichnis
# suchen (erkennbar an pyproject.toml + .venv).
set -euo pipefail

resolve_script_dir() {
  local source="${BASH_SOURCE[0]}"
  while [ -h "$source" ]; do
    local dir
    dir="$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)"
    source="$(readlink "$source")"
    [[ $source != /* ]] && source="$dir/$source"
  done
  cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd
}

dir="$(resolve_script_dir)"
repo_root=""
while [ "$dir" != "/" ]; do
  if [ -f "$dir/pyproject.toml" ] && [ -d "$dir/.venv" ]; then
    repo_root="$dir"
    break
  fi
  dir="$(dirname "$dir")"
done

if [ -z "$repo_root" ]; then
  echo "papertrail-engine (Interims-Dev-Wrapper): kein Entwicklungs-Checkout mit .venv gefunden." >&2
  echo "Dies ist nur für lokale Entwicklung gedacht, kein Produktions-Build - siehe src-tauri/binaries/README.md." >&2
  echo "Für eine installierte App muss an dieser Stelle das PyInstaller-Artefakt stehen (Architekturentscheidung #2)." >&2
  exit 1
fi

# "python -m engine" verlässt sich auf cwd == repo_root, um das Paket über
# den regulären Datei-Import zu finden (kollidiert sonst mit dem
# Namespace-Package-Pfad des editierbaren venv-Installs).
cd "$repo_root"
exec "$repo_root/.venv/bin/python" -m engine "$@"
WRAPPER_EOF

chmod +x "$OUT_PATH"
echo "Dev-Sidecar-Wrapper geschrieben: $OUT_PATH"
