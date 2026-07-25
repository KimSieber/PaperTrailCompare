# PyInstaller-Spec für den Tauri-Sidecar "papertrail-engine" (siehe
# CLAUDE.md Architekturentscheidung #2). Wird nicht direkt aufgerufen,
# sondern über packaging/build_sidecar.py, das vorher die zwei
# Umgebungsvariablen unten setzt und danach PyInstaller mit dieser Datei
# startet - das Spec selbst bleibt plattform- und pfadunabhängig.
#
# PAPERTRAIL_SIDECAR_NAME: Ausgabename inkl. Target-Triple
#   (z.B. "papertrail-engine-aarch64-apple-darwin"), siehe
#   src-tauri/tauri.conf.json -> bundle.externalBin.
# PAPERTRAIL_TESSERACT_STAGING: Verzeichnis mit bereits vorbereiteter
#   (auf macOS: per dylibbundler relozierter) Tesseract-Binary +
#   deu.traineddata, siehe build_sidecar.py:_stage_tesseract. Wird 1:1
#   als "tesseract/" ins Bundle übernommen - PyInstallers eigene
#   Binäranalyse rührt diese Dateien nicht an (sie sind schon fertig
#   relozierbar), siehe engine/ocr_extractor.py:_configure_bundled_tesseract
#   für die Laufzeit-Gegenseite.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH = Verzeichnis des Spec (packaging/)

SIDECAR_NAME = os.environ.get("PAPERTRAIL_SIDECAR_NAME", "papertrail-engine")
TESSERACT_STAGING = os.environ.get("PAPERTRAIL_TESSERACT_STAGING")

datas = [
    (str(REPO_ROOT / "engine" / "assets"), "engine/assets"),
]
binaries = []
hiddenimports = []

if TESSERACT_STAGING:
    datas.append((TESSERACT_STAGING, "tesseract"))

# PyMuPDF und pypdfium2 (von pdfplumber gezogen) bringen native
# Bibliotheken mit, die PyInstallers automatische Binäranalyse laut
# bekannten Berichten nicht immer vollständig findet (siehe Plan) -
# deshalb hier vorsorglich explizit über collect_all einsammeln, statt
# sich auf die Default-Erkennung zu verlassen.
for _package in ("pymupdf", "pypdfium2"):
    _pkg_datas, _pkg_binaries, _pkg_hiddenimports = collect_all(_package)
    datas += _pkg_datas
    binaries += _pkg_binaries
    hiddenimports += _pkg_hiddenimports

a = Analysis(  # noqa: F821 - von PyInstaller zur Laufzeit des Spec injiziert
    [str(REPO_ROOT / "engine" / "__main__.py")],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=SIDECAR_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
