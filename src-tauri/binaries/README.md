# Sidecar-Binary: papertrail-engine

Dieses Verzeichnis nimmt die Python-Core-Engine als Tauri-Sidecar-Binary
auf (Architekturentscheidung #1: Sidecar-Prozess statt Netzwerk-Socket).
Die Datei(en) selbst sind **nicht versioniert** (siehe `.gitignore`),
da es sich um Build-Artefakte handelt.

## Namenskonvention

Tauri erwartet pro Zielplattform eine Datei mit Target-Triple-Suffix:

```
papertrail-engine-aarch64-apple-darwin      # macOS Apple Silicon (Entwicklungsrechner)
papertrail-engine-x86_64-apple-darwin       # macOS Intel
papertrail-engine-x86_64-pc-windows-msvc.exe  # Windows
```

`rustc -vV | grep host` zeigt das Target-Triple der aktuellen Maschine.

## Produktions-Build (noch offen)

Laut Architekturentscheidung #2 wird die Engine für die Auslieferung per
**PyInstaller** zu einer eigenständigen Executable gebündelt (kein
separates Python beim Kunden nötig). Dieser Build-Schritt ist noch nicht
umgesetzt. Sobald er existiert, erzeugt er die oben genannte(n) Datei(en)
in diesem Verzeichnis, z.B.:

```bash
pyinstaller --onefile --name papertrail-engine-aarch64-apple-darwin \
    -p . engine/__main__.py
```

## Lokale Entwicklung (Interims-Lösung)

Bis der PyInstaller-Build existiert, liegt hier ein einfaches Wrapper-
Skript (`papertrail-engine-aarch64-apple-darwin`), das direkt den
Projekt-`.venv`-Python-Interpreter mit `python -m engine` aufruft. Das
ist **nur für lokale Entwicklung auf diesem Rechner** gedacht (hardcodierter
Pfad zum `.venv`) und muss vor einem echten Build durch das PyInstaller-
Artefakt ersetzt werden.
