# file:    engine/__init__.py
# purpose: Package marker and single source of truth for the engine version
#          string (__version__), used by CLI --version and report metadata.
# author:  Kim Sieber
# created: YYYY-MM-DD
# changed: 2026-08-09

"""Python Core Engine (siehe CLAUDE.md, Abschnitt 4).

__version__ ist die einzige Quelle für die Tool-Version - fest im
Quelltext eingebettet statt zur Laufzeit über
importlib.metadata.version() oder einen Git-Aufruf ermittelt. Beides
setzt voraus, dass Distributions-Metadaten bzw. ein .git-Verzeichnis zur
Laufzeit erreichbar sind - im PyInstaller-gebündelten Zustand
(Architekturentscheidung #2) ist das nicht garantiert. engine.__main__
(--version) und engine.report_generator (Report-Metadatenzeile
"Tool-Version") importieren beide von hier, damit es nur eine Stelle
gibt, die bei einem Release aktualisiert werden muss.

Der Versionsstring muss bei jedem Release an vier Stellen synchron
gehalten werden: engine/__init__.py (hier), package.json,
src-tauri/tauri.conf.json und src-tauri/Cargo.toml. Die letzten drei
sind JSON/TOML und tragen den Hinweis daher nur hier bzw. (TOML) direkt
neben dem Feld.

__expiry__ ist das Ablaufdatum der aktuellen Testversion (ISO-Format
YYYY-MM-DD). engine.__main__ prüft es bei jedem Aufruf und bricht mit
Exit-Code 2 ab, wenn das Datum überschritten ist; die GUI prüft es beim
Start über den engine_version-Command.
"""

__version__ = "0.2.0"
__expiry__ = "2026-12-31"
