# PaperTrail Compare — Profil-Konfiguration

## Was ist ein Vergleichsprofil?

Ein Vergleichsprofil ist eine JSON-Datei, die steuert, **wie** PaperTrail Compare zwei PDF-Dokumente miteinander vergleicht. Darin legen Sie fest, ob Groß-/Kleinschreibung relevant ist, wie mit Leerzeichen umgegangen wird, welche Seitenbereiche vom Vergleich ausgeschlossen werden sollen und vieles mehr.

Profile ermöglichen es, für unterschiedliche Dokumenttypen (z. B. Rechnungen, Policen, Kontoauszüge) jeweils eigene Vergleichsregeln zu definieren und wiederzuverwenden. So müssen Sie die Einstellungen nicht bei jedem Vergleich erneut vornehmen.


## Minimales Profil

Ein gültiges Profil benötigt mindestens das Pflichtfeld `version`:

```json
{
  "version": "1.0"
}
```

Alle weiteren Felder sind optional und werden mit sinnvollen Standardwerten belegt, wenn Sie sie weglassen. In der Praxis werden Sie aber fast immer weitere Einstellungen vornehmen wollen.


## Alle Felder im Überblick

| Feld                  | Typ      | Pflicht | Standardwert | Kurzbeschreibung                                |
|-----------------------|----------|---------|--------------|--------------------------------------------------|
| `version`             | Text     | **Ja**  | —            | Profil-Versionsnummer                            |
| `case_sensitive`      | Ja/Nein  | Nein    | `true`       | Groß-/Kleinschreibung beachten                   |
| `normalize_whitespace`| Ja/Nein  | Nein    | `false`      | Leerzeichen-Unterschiede ignorieren              |
| `compare_mode`        | Text     | Nein    | `"words"`    | Vergleichsmodus: `words`, `chars` oder `hybrid`  |
| `text_extraction`     | Text     | Nein    | `"native"`   | Textextraktionsmethode                           |
| `report_format`       | Text     | Nein    | `"pdf"`      | Format des Ergebnisberichts                      |
| `exclude_regions`     | Liste    | Nein    | `[]`         | Seitenbereiche, die ignoriert werden             |
| `page_groups`         | Liste    | Nein    | `[]`         | Muster zur logischen Seitengruppierung           |
| `ocr`                 | Objekt   | Nein    | *(s. unten)* | OCR-Einstellungen für bildbasierte PDFs          |


## Felder im Detail

### `version` (Pflichtfeld)

Die Versionsnummer des Profilformats. Wird für zukünftige Abwärtskompatibilität benötigt.

**Erlaubter Wert:** `"1.0"`

```json
{
  "version": "1.0"
}
```

---

### `case_sensitive`

Legt fest, ob Groß- und Kleinschreibung beim Vergleich eine Rolle spielt.

- `true` (Standard): „Rechnung" und „rechnung" gelten als **unterschiedlich** und erzeugen einen Delta-Eintrag.
- `false`: „Rechnung" und „rechnung" gelten als **identisch**.

**Wann `false` sinnvoll ist:** Wenn das Quellsystem Texte grundsätzlich in Großbuchstaben erzeugt, das Zielsystem aber Groß-/Kleinschreibung verwendet — und Sie nur inhaltliche Abweichungen finden möchten.

```json
{
  "version": "1.0",
  "case_sensitive": false
}
```

---

### `normalize_whitespace`

Steuert, ob Unterschiede bei Leerzeichen, Tabulatoren und Zeilenumbrüchen ignoriert werden.

- `false` (Standard): Jeder Leerzeichen-Unterschied wird als Delta gemeldet. „Max  Mustermann" und „Max Mustermann" gelten als unterschiedlich.
- `true`: Mehrfache Leerzeichen, Tabulatoren und Zeilenumbrüche werden vor dem Vergleich auf ein einzelnes Leerzeichen normalisiert. „Max  Mustermann" und „Max Mustermann" gelten dann als identisch.

**Wann `true` sinnvoll ist:** Beim Wechsel zwischen Drucksystemen ändern sich häufig Zeilenumbrüche und Abstände, obwohl der eigentliche Textinhalt identisch ist. Mit `normalize_whitespace: true` werden diese rein layoutbedingten Unterschiede herausgefiltert und Sie sehen nur echte Textabweichungen.

```json
{
  "version": "1.0",
  "normalize_whitespace": true
}
```

---

### `compare_mode`

Bestimmt die Vergleichsstrategie auf Textebene. Je nach Dokumenttyp liefert der eine oder andere Modus bessere Ergebnisse.

**Erlaubte Werte:**

- **`"words"`** (Standard): Der Text wird in einzelne Wörter zerlegt und wortweise verglichen. Gut geeignet für die meisten Geschäftsdokumente mit sauberer Textstruktur. Liefert in der Regel übersichtliche, leicht nachvollziehbare Deltas.

- **`"chars"`**: Der Text wird zeichenweise verglichen; Leerzeichen werden dabei komplett ignoriert. Gedacht für Dokumente, bei denen die Wortgrenzen bei der Textextraktion unzuverlässig sind — etwa bei älteren Großrechner-Drucksystemen mit Type3-Schriften ohne Unicode-Tabellen. **Achtung:** Auf normalen Dokumenten kann dieser Modus zu einer großen Anzahl kleiner, verstreuter Deltas führen (in Tests: 388 Deltas im Wortmodus vs. 1024 im Zeichenmodus auf denselben Dateien).

- **`"hybrid"`**: Kombiniert beide Ansätze — zunächst grobe Ausrichtung auf Wortebene, dann Zeichenvergleich innerhalb der gefundenen Abweichungen. Das liefert bei problematischen Dokumenten (z. B. Type3-Schriften) deutlich weniger Rauschen als `"chars"` allein (in Tests: von 1024 auf 217 Deltas reduziert), ohne die Genauigkeit zu verlieren.

**Empfehlung:** Verwenden Sie `"words"` als Ausgangspunkt. Nur wenn Sie bei bestimmten Dokumenten auffällig viele falsche Deltas an Wortgrenzen sehen, wechseln Sie auf `"hybrid"`.

```json
{
  "version": "1.0",
  "compare_mode": "hybrid"
}
```

---

### `text_extraction`

Bestimmt, mit welcher Methode der Text aus den PDF-Dateien extrahiert wird.

**Erlaubte Werte:**

- **`"native"`** (Standard): Verwendet die im PDF eingebetteten Textinformationen direkt. Das ist der schnellste und zuverlässigste Weg für die meisten PDFs.

- **`"reconstruct"`**: Rekonstruiert den Text anhand der Rendering-Informationen im PDF. Kann bei bestimmten PDF-Generatoren bessere Ergebnisse liefern, wenn die native Textextraktion fehlerhafte Zeichenfolgen zurückgibt.

```json
{
  "version": "1.0",
  "text_extraction": "reconstruct"
}
```

---

### `report_format`

Legt das Dateiformat des Ergebnisberichts fest, der nach dem Vergleich erzeugt wird.

**Erlaubte Werte:**

- **`"pdf"`** (Standard): Der Bericht wird als PDF-Datei erzeugt, inklusive Seite-an-Seite-Darstellung mit farblich markierten Unterschieden. Ideal zum Archivieren und Weiterleiten.

- **`"html"`**: Der Bericht wird als HTML-Datei erzeugt und kann im Browser geöffnet werden.

```json
{
  "version": "1.0",
  "report_format": "pdf"
}
```

---

### `exclude_regions` — Seitenbereiche ausschließen *(in Arbeit)*

Mit dieser Einstellung können Sie rechteckige Bereiche auf bestimmten Seiten vom Vergleich ausschließen. Das ist nützlich für Inhalte, die sich **planmäßig** zwischen Referenz- und Kandidaten-Dokument unterscheiden, z. B. Druckdatum, Seitenzahlen, Barcodes oder Logos.

Jeder Eintrag beschreibt ein Rechteck und den Seitenbereich, auf den es angewendet wird:

| Feld        | Typ   | Beschreibung                                                       |
|-------------|-------|--------------------------------------------------------------------|
| `page`      | Zahl  | Seitennummer (1 = erste Seite) oder `0` für **alle Seiten**       |
| `page_from` | Zahl  | *(alternativ zu `page`)* Region gilt **ab dieser Seite** bis zum Dokumentende |
| `x`         | Zahl  | Horizontale Position der linken oberen Ecke (in PDF-Punkten)       |
| `y`         | Zahl  | Vertikale Position der linken oberen Ecke (in PDF-Punkten)         |
| `width`     | Zahl  | Breite des Rechtecks (in PDF-Punkten)                              |
| `height`    | Zahl  | Höhe des Rechtecks (in PDF-Punkten)                                |

> **Wichtig:** Verwenden Sie entweder `page` oder `page_from`, nicht beides gleichzeitig.

**Koordinatensystem:** PDF-Punkte entsprechen 1/72 Zoll. Eine DIN-A4-Seite ist ca. 595 × 842 Punkte groß. Der Ursprung (0, 0) liegt in der linken oberen Ecke der Seite.

#### Einzelne Seite

**Beispiel:** Sie möchten auf Seite 1 den Fußbereich ausschließen, in dem das Druckdatum steht (ein Rechteck am unteren linken Rand, 200 Punkte breit und 55 Punkte hoch):

```json
{
  "version": "1.0",
  "exclude_regions": [
    {
      "page": 1,
      "x": 0,
      "y": 770,
      "width": 200,
      "height": 55
    }
  ]
}
```

#### Alle Seiten (`page: 0`)

Verwenden Sie `"page": 0`, wenn eine Region auf **jeder Seite** des Dokuments ausgeschlossen werden soll. Das ist typisch für Strichcodes am Seitenrand oder wiederkehrende Fußzeilen.

**Beispiel:** Ein Strichcode am rechten Rand, der auf jeder Seite gedruckt wird:

```json
{
  "page": 0,
  "x": 540,
  "y": 0,
  "width": 55,
  "height": 842
}
```

#### Ab einer bestimmten Seite (`page_from`)

Verwenden Sie `"page_from"` statt `"page"`, wenn eine Region erst **ab einer bestimmten Seite** gelten soll. Das ist nützlich, wenn z. B. Seite 1 ein Deckblatt ohne Fußzeile ist, die Fußzeile aber ab Seite 2 auf allen Folgeseiten erscheint.

**Beispiel:** Fußzeile ab Seite 2 ausschließen:

```json
{
  "page_from": 2,
  "x": 0,
  "y": 800,
  "width": 595,
  "height": 42
}
```

#### Kombiniertes Beispiel

In der Praxis werden Sie häufig mehrere Regionen mit unterschiedlichen Seitenbereichen kombinieren:

```json
"exclude_regions": [
  { "page": 1,  "x": 400, "y": 0,   "width": 195, "height": 60  },
  { "page": 0,  "x": 540, "y": 0,   "width": 55,  "height": 842 },
  { "page_from": 2, "x": 0, "y": 800, "width": 595, "height": 42 }
]
```

Dieses Beispiel schließt aus:
1. Auf **Seite 1**: einen Bereich oben rechts (z. B. ein Logo, das sich ändern darf)
2. Auf **allen Seiten**: einen schmalen Streifen am rechten Rand (z. B. ein durchgehender Strichcode)
3. **Ab Seite 2**: den Fußbereich (z. B. eine Fußzeile, die auf dem Deckblatt fehlt)

**Tipp zum Ermitteln der Koordinaten:** Öffnen Sie das PDF in Adobe Acrobat oder einem anderen PDF-Viewer, der Koordinaten anzeigt. In Acrobat können Sie unter *Bearbeiten → Voreinstellungen → Einheiten und Hilfslinien* auf „Punkte" umstellen und dann mit dem Cursor die gewünschten Positionen ablesen.

---

### `page_groups` — Logische Seitengruppierung

Mit Seitengruppen können Sie zusammengehörige Seiten innerhalb eines mehrseitigen Dokuments erkennen und gruppieren. Das ist besonders nützlich bei Sammeldokumenten, die mehrere logische Einheiten enthalten (z. B. ein PDF mit 50 Seiten, das 10 Rechnungen à 5 Seiten enthält).

Jeder Eintrag besteht aus einem regulären Ausdruck (`pattern`) und einem Namen (`name`):

| Feld      | Typ  | Beschreibung                                                    |
|-----------|------|-----------------------------------------------------------------|
| `pattern` | Text | Regulärer Ausdruck (Regex), der die erste Seite einer Gruppe erkennt |
| `name`    | Text | Bezeichnung für diese Gruppe (erscheint im Bericht)            |

**Wie es funktioniert:** PaperTrail Compare durchsucht den Text jeder Seite. Sobald der Text einer Seite zum angegebenen Muster passt, beginnt dort eine neue Gruppe. Alle folgenden Seiten gehören zu dieser Gruppe, bis das Muster erneut gefunden wird.

**Beispiel:** Ein Sammeldruck enthält mehrere Rechnungen. Jede Rechnung beginnt mit einer Zeile wie „Rechnung Nr. 2024-0815". Das folgende Muster erkennt den Beginn jeder Rechnung:

```json
{
  "version": "1.0",
  "page_groups": [
    {
      "pattern": "Rechnung Nr\\..*",
      "name": "Rechnung"
    }
  ]
}
```

> **Hinweis zu regulären Ausdrücken:** Der Punkt (`.`) hat in regulären Ausdrücken eine Sonderbedeutung („beliebiges Zeichen"). Um einen echten Punkt zu suchen, muss er mit einem Backslash maskiert werden: `\\.` Beachten Sie, dass in JSON der Backslash selbst ebenfalls maskiert werden muss, daher die doppelte Schreibweise `\\.` in der Datei.

---

### `ocr` — Optische Zeichenerkennung

Die OCR-Einstellungen steuern, ob und wie PaperTrail Compare eine Texterkennung auf bildbasierten PDF-Seiten durchführt. Das ist relevant für eingescannte Dokumente oder PDFs, die als Bilder gespeichert wurden und keinen extrahierbaren Text enthalten.

Das `ocr`-Objekt hat folgende Felder:

| Feld                    | Typ    | Standard  | Beschreibung                                      |
|-------------------------|--------|-----------|---------------------------------------------------|
| `enabled`               | Ja/Nein| `false`   | OCR grundsätzlich aktivieren                       |
| `confidence_threshold`  | Zahl   | `0.85`    | Mindestsicherheit für erkannte Zeichen (0.0–1.0)  |
| `dpi`                   | Zahl   | `200`     | Auflösung für die Rasterung (höher = genauer, aber langsamer) |
| `mode_reference`        | Text   | —         | OCR-Modus speziell für die Referenz-Datei          |
| `mode_candidate`        | Text   | —         | OCR-Modus speziell für die Kandidaten-Datei        |

#### `enabled`

- `false` (Standard): Keine OCR. Wenn das PDF keinen extrahierbaren Text enthält, wird die Seite als „kein Text verfügbar" behandelt.
- `true`: OCR wird je nach Bedarf eingesetzt (siehe `mode_reference`/`mode_candidate`).

#### `confidence_threshold`

Legt fest, ab welcher Erkennungssicherheit ein OCR-Ergebnis akzeptiert wird. Werte zwischen 0.0 (alles akzeptieren) und 1.0 (nur bei absoluter Sicherheit). Der Standardwert `0.85` ist ein guter Kompromiss für die meisten Geschäftsdokumente.

#### `dpi`

Die Auflösung, mit der PDF-Seiten für die OCR gerastert werden. Höhere Werte verbessern die Erkennungsqualität, erhöhen aber die Verarbeitungszeit und den Speicherbedarf. Muss ein positiver ganzzahliger Wert sein.

- `150`: Schnell, ausreichend für große, klare Schriften
- `200` (Standard): Guter Kompromiss
- `300`: Hohe Qualität, empfehlenswert bei kleinen Schriftgrößen

#### `mode_reference` und `mode_candidate`

Diese optionalen Felder erlauben es, die OCR-Strategie **getrennt** für Referenz- und Kandidaten-Datei einzustellen. Das ist nützlich, wenn z. B. die Referenz-Datei aus einem alten Drucksystem stammt und problematische Schriften enthält, der Kandidat aber sauberen nativen Text hat.

**Erlaubte Werte:**

- **`"off"`**: Keine OCR für diese Datei, auch wenn `enabled: true` gesetzt ist.
- **`"fallback"`**: OCR wird nur eingesetzt, wenn die native Textextraktion keinen oder zu wenig Text liefert.
- **`"force"`**: OCR wird immer verwendet, auch wenn nativer Text vorhanden ist. Sinnvoll, wenn der eingebettete Text fehlerhaft ist (z. B. bei Type3-Schriften).

Wenn `mode_reference` bzw. `mode_candidate` nicht gesetzt sind, gilt das alte Verhalten: `enabled: true` entspricht `"fallback"`, `enabled: false` entspricht `"off"`.

**Beispiel:** Referenz mit erzwungener OCR, Kandidat nutzt nativen Text:

```json
{
  "version": "1.0",
  "ocr": {
    "enabled": true,
    "confidence_threshold": 0.85,
    "dpi": 300,
    "mode_reference": "force",
    "mode_candidate": "off"
  }
}
```

---

## Vollständiges Beispielsprofil

Das folgende Profil zeigt alle verfügbaren Einstellungen in Kombination. Es eignet sich als Ausgangspunkt, den Sie an Ihre Anforderungen anpassen können:

```json
{
  "version": "1.0",

  "case_sensitive": false,
  "normalize_whitespace": true,
  "compare_mode": "words",
  "text_extraction": "native",
  "report_format": "pdf",

  "exclude_regions": [
    {
      "page": 1,
      "x": 0,
      "y": 770,
      "width": 200,
      "height": 55
    }
  ],

  "page_groups": [
    {
      "pattern": "Rechnung Nr\\..*",
      "name": "Rechnung"
    }
  ],

  "ocr": {
    "enabled": false,
    "confidence_threshold": 0.85,
    "dpi": 200
  }
}
```


## Profilauswahl in der Anwendung

### Profilverzeichnis einrichten

Bevor Sie Profile nutzen können, legen Sie in den **Einstellungen** fest, in welchem Verzeichnis Ihre Profildateien liegen. Dieses Verzeichnis wird gespeichert und bleibt auch nach einem Neustart der Anwendung hinterlegt.

Legen Sie Ihre Profildateien (z. B. `rechnung_inland.json`, `kontoauszug.json`, `police_leben.json`) in diesem Verzeichnis ab. Neue Dateien erscheinen automatisch in der Auswahl — Sie müssen die Anwendung dafür nicht neu starten.

**Tipp für Teams:** Verwenden Sie ein gemeinsames Abteilungslaufwerk als Profilverzeichnis (z. B. `\\server\abteilung\papertrail-profile\`). So pflegt ein Kollege die Profile zentral, und alle Teammitglieder arbeiten automatisch mit dem aktuellen Stand. Alternativ kann jeder DVK ein lokales Verzeichnis für eigene Profile verwenden.

### Profil auswählen und wechseln

Sowohl im **Einzelvergleich** als auch im **Batch-Vergleich** finden Sie ein Auswahlmenü, in dem alle Profildateien aus dem hinterlegten Verzeichnis aufgelistet werden. Der Dateiname wird dabei vollständig angezeigt (z. B. `rechnung_inland.json`), damit Sie die Datei eindeutig wiedererkennen.

Wählen Sie das passende Profil für Ihren Dokumenttyp aus. Wenn Sie mehrere Läufe hintereinander mit unterschiedlichen Dokumenttypen durchführen, wechseln Sie das Profil einfach über das Auswahlmenü — ohne Umweg über die Einstellungen.

### Empfohlene Namenskonvention

Damit die Auswahl übersichtlich bleibt, empfehlen wir eine einheitliche Benennung:

- `rechnung_inland.json` — Inlandsrechnungen
- `rechnung_ausland.json` — Auslandsrechnungen
- `kontoauszug_giro.json` — Girokontoauszüge
- `police_leben.json` — Lebensversicherungspolicen
- `test_standard.json` — Standard-Testprofil für erste Gehversuche

Vermeiden Sie Leerzeichen und Umlaute im Dateinamen, auch wenn dies technisch möglich ist. Unterstriche sorgen für eine zuverlässige Darstellung auf allen Betriebssystemen.


## Hinweise und Tipps

**Dateiformat:** Die Profildatei muss gültiges JSON sein. Achten Sie besonders auf korrekte Kommasetzung — nach dem letzten Eintrag in einem Objekt oder einer Liste darf **kein** Komma stehen. Nutzen Sie bei Bedarf einen JSON-Validator (z. B. [jsonlint.com](https://jsonlint.com)), um Syntaxfehler zu finden.

**Zeichenkodierung:** Speichern Sie die Datei in UTF-8-Kodierung. Das stellt sicher, dass Umlaute und Sonderzeichen in Mustern und Namen korrekt verarbeitet werden.

**Profilwahl:** Erstellen Sie pro Dokumenttyp ein eigenes Profil. Ein Profil für Rechnungen hat andere Ausschlussbereiche und Vergleichsregeln als eines für Kontoauszüge. Benennen Sie die Dateien aussagekräftig, z. B. `profil_rechnung.json`, `profil_kontoauszug.json`.

**Schrittweise konfigurieren:** Beginnen Sie mit einem minimalen Profil und fügen Sie Einstellungen einzeln hinzu. So können Sie die Auswirkung jeder Änderung gezielt nachvollziehen.

**Fehlerbehandlung:** Wenn eine Profildatei ungültig ist (fehlende Pflichtfelder, ungültige Werte, JSON-Syntaxfehler), zeigt PaperTrail Compare eine sprechende Fehlermeldung mit dem genauen Problem an. Die häufigsten Fehlerquellen sind fehlende Anführungszeichen, vergessene Kommas und ungültige Werte bei Auswahlfeldern.
