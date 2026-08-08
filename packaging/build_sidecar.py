# file:    packaging/build_sidecar.py
# purpose: Builds the PyInstaller sidecar executable for the Python Core
#          Engine, including Tesseract staging, target-triple naming, and
#          self-checks (version output, minimum file size).
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Baut den echten PyInstaller-Sidecar für die Engine (siehe CLAUDE.md
Architekturentscheidung #2) und legt ihn unter
src-tauri/binaries/papertrail-engine-<target-triple>[.exe] ab - exakt der
Pfad/Name, den tauri.conf.json (bundle.externalBin) erwartet.

Wird von packaging/prepare_sidecar.mjs vor jedem `tauri build`
aufgerufen (siehe tauri.conf.json: beforeBuildCommand) - nicht manuell,
damit ein Release-Build den lokalen Dev-Wrapper (packaging/dev_sidecar.sh)
nicht mehr versehentlich ausliefern kann: dieser Aufruf überschreibt den
Zielpfad bedingungslos, unabhängig davon, was vorher dort lag.

Direkter Aufruf zum Testen/Debuggen:
    .venv/bin/python packaging/build_sidecar.py
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "packaging" / "papertrail-engine.spec"
BINARIES_DIR = REPO_ROOT / "src-tauri" / "binaries"
BUILD_STAGING_DIR = REPO_ROOT / "packaging" / ".build"

_DEV_MARKER = "PAPERTRAIL_DEV_SIDECAR_MARKER"
_MIN_EXPECTED_SIZE_BYTES = 20 * 1024 * 1024  # PyMuPDF allein bringt ~45MB native Libs mit


class BuildError(Exception):
    """Bricht den Sidecar-Build mit einer für CI/Entwickler lesbaren Meldung ab."""


def _target_triple() -> str:
    result = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise BuildError("rustc -vV lieferte kein 'host:'-Feld - ist Rust installiert?")


def _find_system_tesseract() -> Path:
    found = shutil.which("tesseract")
    if not found:
        raise BuildError(
            "Keine Tesseract-Installation gefunden (PATH). Für den Build wird eine lokale "
            "Tesseract-Installation als Quelle benötigt (macOS: 'brew install tesseract "
            "tesseract-lang', Windows: offizieller Installer) - siehe README.md."
        )
    return Path(found)


def _find_tessdata_deu(tesseract_symlink: Path) -> Path:
    """tesseract_symlink ist bewusst NICHT aufgelöst (kein .resolve()):
    unter Homebrew liegt die Binary selbst in einem Cellar/<formula>/<version>/-
    Ordner, tessdata aber unter dem gemeinsamen <prefix>/share/tessdata/ -
    das über die aufgelöste Binary zu erraten würde in die falsche Cellar-
    Formula (tesseract statt tesseract-lang) zeigen. Der unaufgelöste
    PATH-Symlink (<prefix>/bin/tesseract) liegt dagegen zuverlässig direkt
    unter <prefix>.

    Die vendorte Kopie (vendor/tessdata/deu.traineddata) hat auf jeder
    Plattform Vorrang vor der Systemsuche, damit der Build nicht davon
    abhängt, was Chocolatey/Homebrew gerade mitliefern. Der Pfad wird über
    REPO_ROOT aufgelöst, nicht über das Arbeitsverzeichnis, damit das
    Skript unabhängig vom Aufrufort funktioniert."""
    vendored = REPO_ROOT / "vendor" / "tessdata" / "deu.traineddata"
    if vendored.is_file():
        return vendored.resolve()

    candidates = []
    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix:
        candidates.append(Path(env_prefix) / "tessdata" / "deu.traineddata")
        candidates.append(Path(env_prefix) / "deu.traineddata")
    # Homebrew-/Linux-Layout: <prefix>/bin/tesseract -> <prefix>/share/tessdata/
    candidates.append(tesseract_symlink.parent.parent / "share" / "tessdata" / "deu.traineddata")
    # Windows-Standardinstallation
    candidates.append(tesseract_symlink.resolve().parent / "tessdata" / "deu.traineddata")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise BuildError(
        f"deu.traineddata nicht gefunden (gesucht: {[str(c) for c in candidates]}). "
        "Architekturentscheidung #3 verlangt genau dieses Sprachmodell, nicht den vollen "
        "tessdata-Ordner."
    )


def _stage_tesseract_macos(tesseract_binary: Path, tessdata_deu: Path, staging_dir: Path) -> Path:
    """Kopiert Tesseract-Binary + deu.traineddata in ein Staging-Verzeichnis
    und macht die Binary per dylibbundler relozierbar (@executable_path-
    relative Ladepfade für alle Nicht-System-.dylibs) - ohne das würde die
    Binary beim Kunden absolute Homebrew-Pfade (/opt/homebrew/...) suchen,
    die dort nicht existieren. `brew install dylibbundler`, falls es noch
    fehlt."""
    if shutil.which("dylibbundler") is None:
        raise BuildError(
            "dylibbundler nicht gefunden (macOS-Build braucht es, um Tesseracts "
            "Homebrew-Abhängigkeiten relozierbar zu machen). Installieren: "
            "'brew install dylibbundler'."
        )

    bin_dir = staging_dir / "bin"
    lib_dir = staging_dir / "lib"
    tessdata_dir = staging_dir / "tessdata"
    for d in (bin_dir, lib_dir, tessdata_dir):
        d.mkdir(parents=True, exist_ok=True)

    staged_binary = bin_dir / "tesseract"
    shutil.copy2(tesseract_binary, staged_binary)
    staged_binary.chmod(0o755)
    shutil.copy2(tessdata_deu, tessdata_dir / "deu.traineddata")

    subprocess.run(
        [
            "dylibbundler",
            "--overwrite-dir",
            "--bundle-deps",
            "--fix-file", str(staged_binary),
            "--dest-dir", str(lib_dir),
            "--install-path", "@executable_path/../lib/",
        ],
        cwd=staging_dir, check=True,
    )
    return staging_dir


def _stage_tesseract_windows(tesseract_binary: Path, tessdata_deu: Path, staging_dir: Path) -> Path:
    """Windows-DLLs suchen im selben Verzeichnis wie die .exe (Standard-
    Suchreihenfolge) - deshalb reicht 'alles neben die .exe kopieren',
    kein dylibbundler-Äquivalent nötig. UNGETESTET (nur macOS lokal
    verifiziert, siehe Plan) - bei Abweichungen im echten Windows-CI-Lauf
    entsprechend nachbessern."""
    bin_dir = staging_dir / "bin"
    tessdata_dir = staging_dir / "tessdata"
    bin_dir.mkdir(parents=True, exist_ok=True)
    tessdata_dir.mkdir(parents=True, exist_ok=True)

    install_dir = tesseract_binary.parent
    for item in install_dir.iterdir():
        if item.is_file() and item.suffix.lower() in (".exe", ".dll"):
            shutil.copy2(item, bin_dir / item.name)
    shutil.copy2(tessdata_deu, tessdata_dir / "deu.traineddata")
    return staging_dir


def _stage_tesseract(staging_dir: Path) -> Path:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    tesseract_binary = _find_system_tesseract()
    tessdata_deu = _find_tessdata_deu(tesseract_binary)

    system = platform.system()
    if system == "Darwin":
        return _stage_tesseract_macos(tesseract_binary, tessdata_deu, staging_dir)
    if system == "Windows":
        return _stage_tesseract_windows(tesseract_binary, tessdata_deu, staging_dir)
    raise BuildError(f"Kein Tesseract-Staging für Betriebssystem '{system}' implementiert.")


def _run_pyinstaller(sidecar_name: str, tesseract_staging: Path) -> Path:
    work_dir = REPO_ROOT / "packaging" / ".pyinstaller-build"
    dist_dir = REPO_ROOT / "packaging" / ".dist"

    env = os.environ.copy()
    env["PAPERTRAIL_SIDECAR_NAME"] = sidecar_name
    env["PAPERTRAIL_TESSERACT_STAGING"] = str(tesseract_staging)

    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            str(SPEC_PATH),
            "--distpath", str(dist_dir),
            "--workpath", str(work_dir),
            "--noconfirm",
        ],
        cwd=REPO_ROOT, env=env, check=True,
    )

    suffix = ".exe" if platform.system() == "Windows" else ""
    built = dist_dir / f"{sidecar_name}{suffix}"
    if not built.is_file():
        raise BuildError(f"PyInstaller-Lauf hat keine Datei unter {built} erzeugt.")
    return built


def _self_check(sidecar_path: Path) -> None:
    """Verweigert die Auslieferung, falls am Ziel doch der Dev-Wrapper
    steht (Marker-String) oder die Datei verdächtig klein ist (z.B. weil
    PyInstaller früh abgebrochen ist, aber trotzdem eine Datei hinterlassen
    hat) - genau die Konstellation, die zum ursprünglichen Bugreport
    führte, darf nicht mehr unbemerkt durchrutschen."""
    content_sample = sidecar_path.read_bytes()[:4096]
    if _DEV_MARKER.encode() in content_sample:
        raise BuildError(
            f"{sidecar_path} enthält noch den Dev-Wrapper-Marker ({_DEV_MARKER}) - "
            "das darf für einen Release-Build niemals der Fall sein. Build abgebrochen."
        )
    size = sidecar_path.stat().st_size
    if size < _MIN_EXPECTED_SIZE_BYTES:
        raise BuildError(
            f"{sidecar_path} ist mit {size / 1024 / 1024:.1f} MB verdächtig klein "
            f"(erwartet mind. {_MIN_EXPECTED_SIZE_BYTES / 1024 / 1024:.0f} MB, PyMuPDF allein "
            "bringt schon ~45MB native Bibliotheken mit) - Build abgebrochen."
        )


def main() -> int:
    try:
        target_triple = _target_triple()
        sidecar_name = f"papertrail-engine-{target_triple}"
        print(f"[build_sidecar] Target-Triple: {target_triple}")

        tesseract_staging = _stage_tesseract(BUILD_STAGING_DIR / "tesseract")
        print(f"[build_sidecar] Tesseract vorbereitet unter {tesseract_staging}")

        built_path = _run_pyinstaller(sidecar_name, tesseract_staging)

        BINARIES_DIR.mkdir(parents=True, exist_ok=True)
        final_path = BINARIES_DIR / built_path.name
        shutil.copy2(built_path, final_path)
        if platform.system() != "Windows":
            final_path.chmod(0o755)

        _self_check(final_path)

        size_mb = final_path.stat().st_size / 1024 / 1024
        print(f"[build_sidecar] Fertig: {final_path} ({size_mb:.1f} MB)")
        return 0
    except BuildError as exc:
        print(f"[build_sidecar] FEHLER: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"[build_sidecar] FEHLER: Befehl fehlgeschlagen: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
