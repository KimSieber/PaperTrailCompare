# PaperTrailCompare
Programm zum Abgleich von PDF-Dateien (auch Batch) im Rahmen einer Drucksystem-Migration

## Entwicklungs-Setup

### Python-Umgebung

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
```

Dependencies sind in `pyproject.toml` gepflegt (siehe CLAUDE.md Abschnitt 5).

### Tesseract OCR (für `ocr_extractor`)

`pytesseract` ist nur ein Python-Wrapper — die Tesseract-Engine selbst ist eine
native Binary und muss separat auf dem System installiert sein (nicht per pip).

**macOS (Entwicklungsrechner):**

```bash
brew install tesseract tesseract-lang
```

- `tesseract` installiert die Engine (nur `eng`, `osd`, `snum` Sprachdaten).
- `tesseract-lang` installiert zusätzlich **alle** verfügbaren Sprachpakete
  (inkl. `deu`) — praktisch für lokale Entwicklung/Tests.

Prüfen:

```bash
tesseract --version
tesseract --list-langs   # muss "deu" enthalten
```

**Wichtig für Auslieferung/Packaging:** Laut Architekturentscheidung #3
(CLAUDE.md Abschnitt 6) wird im fertigen Produkt **nur das deutsche
Sprachmodell (`deu`)** gebündelt, nicht der volle `tesseract-lang`-Umfang.
Beim PyInstaller-Build ist daher gezielt nur `deu.traineddata` aus
`/opt/homebrew/share/tessdata/` einzubinden, nicht das gesamte
`tessdata`-Verzeichnis.

**Windows (Kunden-Auslieferung):** Tesseract-Binary + `deu`-Sprachmodell werden
mit dem PyInstaller-Bundle mitgeliefert (kein separater Installationsschritt
beim Kunden), siehe CLAUDE.md Abschnitt 6, Entscheidung #2.
