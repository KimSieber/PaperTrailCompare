# PaperTrail Compare — Profil-Konfiguration

## Was ist ein Vergleichsprofil?

Ein Vergleichsprofil ist eine JSON-Datei, die steuert, **wie** PaperTrail Compare zwei PDF-Dokumente miteinander vergleicht. Darin legen Sie fest, ob Groß-/Kleinschreibung relevant ist, wie mit Leerzeichen und Bindestrichen umgegangen wird, welche Seitenbereiche vom Vergleich ausgeschlossen oder gesondert verglichen werden sollen und vieles mehr.

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

| Feld                       | Typ      | Pflicht | Standardwert | Kurzbeschreibung                                        |
|----------------------------|----------|---------|--------------|----------------------------------------------------------|
| `version`                  | Text     | **Ja**  | —            | Profil-Versionsnummer                                    |
| `case_sensitive`           | Ja/Nein  | Nein    | `true`       | Groß-/Kleinschreibung beachten                           |
| `normalize_whitespace`     | Ja/Nein  | Nein    | `false`      | Leerzeichen-Unterschiede ignorieren                      |
| `compare_mode`             | Text     | Nein    | `"words"`    | Vergleichsmodus: `words`, `chars` oder `hybrid`          |
| `text_extraction`          | Text     | Nein    | `"native"`   | Textextraktionsmethode                                   |
| `merge_hyphenation`        | Ja/Nein  | Nein    | `false`      | Trennstriche am Zeilenende zusammenführen                |
| `normalize_orphan_hyphens` | Ja/Nein  | Nein    | `false`      | Verwaiste Bindestriche durch Umbruchänderung ignorieren  |
| `report_format`            | Text     | Nein    | `"pdf"`      | Format des Ergebnisberichts                              |
| `exclude_regions`          | Liste    | Nein    | `[]`         | Seitenbereiche, die komplett ignoriert werden             |
| `compare_regions`          | Liste    | Nein    | `[]`         | Seitenbereiche, die isoliert vom Rest der Seite verglichen werden |
| `page_groups`              | Liste    | Nein    | `[]`         | Muster zur logischen Seitengruppierung                   |
| `ocr`                      | Objekt   | Nein    | *(s. unten)* | OCR-Einstellungen für bildbasierte PDFs                  |


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

**Wichtig:** Diese Einstellung gilt auch innerhalb von Vergleichsbereichen (`compare_regions`), wenn deren `mode` auf `"sequential"` steht. Im Modus `"unordered"` spielt sie keine Rolle, da dort sämtlicher Whitespace bereits vor dem Vergleich entfernt wird.

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

**Hinweis:** Diese Einstellung gilt auch innerhalb von Vergleichsbereichen (`compare_regions`) im Modus `"sequential"`.

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

### `merge_hyphenation`

Steuert, ob Wörter, die durch einen Trennstrich am Zeilenende getrennt wurden, vor dem Vergleich wieder zusammengeführt werden.

- `false` (Standard): „Versiche-\nrung" bleibt als zwei separate Textfragmente erhalten. Ein Unterschied im Umbruch (z. B. „Versiche-rung" vs. „Versicherung") erzeugt ein Delta.
- `true`: „Versiche-\nrung" wird vor dem Vergleich zu „Versicherung" zusammengeführt. Wenn beide Seiten denselben Text haben, aber an unterschiedlichen Stellen umbrechen, wird kein Delta erzeugt.

**Wann `true` sinnvoll ist:** Wenn sich durch den Drucksystemwechsel die Zeilen- und Seitenumbrüche ändern und dadurch andere Trennstellen entstehen, die keine inhaltlichen Unterschiede darstellen.

**Wann `false` besser ist:** Bei Dokumenten mit zusammengesetzten Wörtern, die einen Bindestrich als Bestandteil haben (z. B. „Haftpflicht-Versicherung", „Arbeitgeber-Anteil"). Dort würde `merge_hyphenation: true` den Bindestrich fälschlicherweise als Trennstrich interpretieren und das Wort zusammenziehen. In solchen Fällen ist `normalize_orphan_hyphens` die bessere Alternative (siehe nächster Abschnitt).

**Zusammenspiel:** `merge_hyphenation` und `normalize_orphan_hyphens` können unabhängig voneinander oder gemeinsam aktiviert werden. Beide wirken in der Normalisierungsschicht vor dem eigentlichen Vergleich und greifen auch innerhalb von Vergleichsbereichen (`compare_regions`) im Modus `"sequential"`.

```json
{
  "version": "1.0",
  "merge_hyphenation": true
}
```

---

### `normalize_orphan_hyphens`

Steuert den Umgang mit „verwaisten" Bindestrichen, die entstehen, wenn ein Wort im einen Dokument am Zeilenende getrennt ist, im anderen aber nicht.

- `false` (Standard): Jeder Bindestrich-Unterschied erzeugt ein Delta.
- `true`: Verwaiste Bindestriche, die durch unterschiedliche Umbruchpositionen entstehen, werden vor dem Vergleich normalisiert und ignoriert.

**Beispiel:** Die Referenz enthält „Versicherungs-\nbedingungen" (über zwei Zeilen), der Kandidat enthält „Versicherungsbedingungen" (in einer Zeile). Mit `normalize_orphan_hyphens: true` wird dies als identisch behandelt — der Bindestrich am Zeilenende ist kein inhaltlicher Unterschied, sondern ein Umbruch-Artefakt.

**Wann `true` sinnvoll ist:** Bei Dokumentenmigrationen, bei denen sich die Seitenbreite oder Schriftgröße ändert und dadurch andere Umbrüche entstehen. Anders als `merge_hyphenation` ist diese Einstellung sicherer bei zusammengesetzten Wörtern, da sie gezielter auf „verwaiste" Trennstriche reagiert.

**Zusammenspiel mit `merge_hyphenation`:** Beide Einstellungen ergänzen sich. Wenn Sie unsicher sind, beginnen Sie mit `normalize_orphan_hyphens: true` allein. Fügen Sie `merge_hyphenation: true` nur hinzu, wenn dann noch störende Trennstrich-Deltas übrig bleiben, und prüfen Sie anschließend, ob dadurch echte Bindestrich-Komposita verfälscht werden.

```json
{
  "version": "1.0",
  "normalize_orphan_hyphens": true
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

### `exclude_regions` — Seitenbereiche ausschließen

Mit dieser Einstellung können Sie rechteckige Bereiche auf bestimmten Seiten **komplett vom Vergleich ausschließen**. Text innerhalb dieser Bereiche wird weder extrahiert noch verglichen — er existiert für den Vergleich nicht.

Das ist sinnvoll für Inhalte, die sich **planmäßig** zwischen Referenz- und Kandidaten-Dokument unterscheiden und deren Abweichung Sie nicht interessiert, z. B. Druckdatum, Seitenzahlen, Barcodes, Logos oder Marginalien (Randnotizen mit Druckkennzeichen).

Jeder Eintrag beschreibt ein Rechteck und den Seitenbereich, auf den es angewendet wird:

| Feld        | Typ   | Pflicht | Beschreibung                                                       |
|-------------|-------|---------|--------------------------------------------------------------------|
| `comment`   | Text  | Nein    | Freitextbeschreibung, was diese Region enthält (wird ignoriert, dient nur der Dokumentation im Profil) |
| `page`      | Zahl  | *       | Seitennummer (1 = erste Seite) oder `0` für **alle Seiten**       |
| `page_from` | Zahl  | *       | *(alternativ zu `page`)* Region gilt **ab dieser Seite** bis zum Dokumentende |
| `x`         | Zahl  | **Ja**  | Horizontale Position der linken oberen Ecke (in PDF-Punkten)       |
| `y`         | Zahl  | **Ja**  | Vertikale Position der linken oberen Ecke (in PDF-Punkten)         |
| `width`     | Zahl  | **Ja**  | Breite des Rechtecks (in PDF-Punkten)                              |
| `height`    | Zahl  | **Ja**  | Höhe des Rechtecks (in PDF-Punkten)                                |

> **Wichtig:** Verwenden Sie entweder `page` oder `page_from`, nicht beides gleichzeitig. Mindestens eines der beiden muss angegeben werden.

**Koordinatensystem:** PDF-Punkte entsprechen 1/72 Zoll. Eine DIN-A4-Seite ist ca. 595 × 842 Punkte groß. Der Ursprung (0, 0) liegt in der linken oberen Ecke der Seite.

#### Einzelne Seite

**Beispiel:** Sie möchten auf Seite 1 den Fußbereich ausschließen, in dem das Druckdatum steht (ein Rechteck am unteren linken Rand, 200 Punkte breit und 55 Punkte hoch):

```json
{
  "version": "1.0",
  "exclude_regions": [
    {
      "comment": "Druckdatum unten links auf Deckblatt",
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
  "comment": "Strichcode am rechten Rand (alle Seiten)",
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
  "comment": "Fußzeile ab Seite 2 (Deckblatt hat keine)",
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
  { "comment": "Logo oben rechts (nur Deckblatt)",
    "page": 1,  "x": 400, "y": 0,   "width": 195, "height": 60  },
  { "comment": "Strichcode am rechten Rand (alle Seiten)",
    "page": 0,  "x": 540, "y": 0,   "width": 55,  "height": 842 },
  { "comment": "Fußzeile ab Seite 2",
    "page_from": 2, "x": 0, "y": 800, "width": 595, "height": 42 }
]
```

Dieses Beispiel schließt aus:
1. Auf **Seite 1**: einen Bereich oben rechts (z. B. ein Logo, das sich ändern darf)
2. Auf **allen Seiten**: einen schmalen Streifen am rechten Rand (z. B. ein durchgehender Strichcode)
3. **Ab Seite 2**: den Fußbereich (z. B. eine Fußzeile, die auf dem Deckblatt fehlt)

---

### `compare_regions` — Seitenbereiche isoliert vergleichen

**Ehemals `table_regions`** — der alte Schlüsselname wird nicht mehr akzeptiert und erzeugt eine Fehlermeldung mit Verweis auf `compare_regions`.

Mit dieser Einstellung definieren Sie rechteckige Bereiche, die **vom restlichen Seitentext getrennt und für sich allein verglichen** werden. Im Gegensatz zu `exclude_regions` wird der Text nicht ignoriert — er wird nur nicht mit dem umgebenden Fließtext vermischt.

#### Wann brauche ich einen Vergleichsbereich?

Vergleichsbereiche lösen das Problem, dass PDF-Texte **keine natürliche Lesereihenfolge** haben. Wenn auf einer Seite links eine Empfängeradresse und rechts ein Absender-Infoblock stehen, kann die Textextraktion die Blöcke in beliebiger Reihenfolge liefern. Der sequenzielle Vergleich vergleicht dann Adressteile mit Absenderteilen — und erzeugt Dutzende falscher Deltas, obwohl sich nur das Datum geändert hat.

Ein Vergleichsbereich sagt: „Vergleiche diesen Bereich für sich, nicht mit dem Rest der Seite." Dadurch wird das Datum korrekt als eigenes Delta erkannt, ohne dass die Empfängeradresse hineinspielt.

**Typische Anwendungsfälle:**

- **Mehrspaltige Fußzeilen** mit Firmendaten (Registergericht, IBAN, Vorstand), die bei beiden Drucksystemen identisch sind, aber in unterschiedlicher Block-Reihenfolge extrahiert werden
- **Absender-Infoblöcke** rechts oben mit Sachbearbeiterdaten und Datum, die ohne Trennung mit der Empfängeradresse links vermischt werden
- **Briefkopfzeilen** die auf beiden Seiten inhaltsgleich sind, aber wegen Schriftfragmentierung unterschiedlich extrahiert werden

#### Aufbau eines Vergleichsbereichs

Jeder Eintrag hat die Koordinatenfelder wie `exclude_regions`, plus drei zusätzliche Felder:

| Feld        | Typ   | Pflicht | Standardwert    | Beschreibung                                              |
|-------------|-------|---------|-----------------|-----------------------------------------------------------|
| `comment`   | Text  | Nein    | —               | Freitextbeschreibung (nur Dokumentation)                  |
| `page`      | Zahl  | *       | —               | Seitennummer oder `0` für alle Seiten                     |
| `page_from` | Zahl  | *       | —               | Region gilt ab dieser Seite                               |
| `x`         | Zahl  | **Ja**  | —               | Horizontale Position (PDF-Punkte)                         |
| `y`         | Zahl  | **Ja**  | —               | Vertikale Position (PDF-Punkte)                           |
| `width`     | Zahl  | **Ja**  | —               | Breite (PDF-Punkte)                                       |
| `height`    | Zahl  | **Ja**  | —               | Höhe (PDF-Punkte)                                         |
| `condition` | Text  | **Ja**  | —               | Text, der im Bereich vorkommen muss, damit er aktiviert wird |
| `mode`      | Text  | Nein    | `"sequential"`  | Vergleichsmodus: `"sequential"` oder `"unordered"`        |

#### Das `condition`-Feld — wann wird der Bereich aktiviert?

Ein Vergleichsbereich wird **nur aktiviert**, wenn der in `condition` angegebene Text innerhalb des Bereichs gefunden wird. Das verhindert, dass die Region auf Seiten greift, wo sie nicht hingehört (z. B. auf reinen Textseiten ohne Fußzeile).

**Wie der Abgleich funktioniert:**

1. Alle Textblöcke, die den Bereich überlappen, werden zusammengefasst.
2. Aus dem zusammengefassten Text wird **sämtlicher Whitespace entfernt** (Leerzeichen, Zeilenumbrüche, Tabs).
3. Aus dem `condition`-Text wird ebenfalls sämtlicher Whitespace entfernt.
4. Es wird geprüft, ob der normalisierte `condition`-Text als **Teilzeichenkette** im normalisierten Bereichstext vorkommt.

Das bedeutet:
- Die Position innerhalb des Bereichs spielt keine Rolle — der Text kann am Anfang, in der Mitte oder am Ende stehen.
- Leerzeichen und Zeilenumbrüche im `condition`-Text werden ignoriert. `"SV SparkassenVersicherung"` matcht auch, wenn im PDF `"SV Spark assenVersicherung"` steht (Type3-Fragmentierung).
- Die Suche ist **case-sensitiv** — `"sparkassenversicherung"` würde nicht matchen.

**Wichtige Regeln für die Wahl der Condition:**

1. **Eindeutigkeit:** Die Condition muss **spezifisch genug** sein, dass sie nicht versehentlich auf Seiten matcht, wo der Bereich nicht gelten soll. Der Firmenname allein (`"SV SparkassenVersicherung"`) kommt z. B. im Fließtext vielfach vor. Besser: `"Registergericht Stuttgart"` (kommt nur in der Fußzeile vor) oder `"SV SparkassenVersicherung ·"` (der Mittepunkt nach dem Firmennamen kommt nur in der Absenderzeile vor).

2. **Zusammenhängend:** Die Condition muss **innerhalb eines einzigen Textblocks** zusammenhängend vorkommen. Zwar wird der gesamte Bereichstext nach der Whitespace-Entfernung durchsucht, aber Blockgrenzen können den Text in eine andere Reihenfolge bringen, sodass ein blockgrenzenübergreifender Match vom Zufall abhängt. Wählen Sie eine Phrase, die in einer Zeile steht.

3. **Beidseitig vorhanden:** Die Condition muss sowohl im Referenz- als auch im Kandidaten-Dokument im Bereich vorkommen. Matcht sie nur auf einer Seite, werden die Blöcke nur dort vom Seitentext getrennt — das erzeugt asymmetrische Deltas, die schwer zu interpretieren sind. Prüfen Sie eine neue Condition immer gegen beide Dokumente (siehe Abschnitt „Diagnose und Fehlerbehebung" am Ende dieses Dokuments).

**Beispiel — warum Eindeutigkeit wichtig ist:**

```
Condition: "SV SparkassenVersicherung"
→ Matcht auf 5 Seiten (Fußzeile, Fließtext, Briefkopf) — zu unspezifisch!

Condition: "Registergericht Stuttgart"
→ Matcht nur auf den Briefseiten mit Fußzeile — eindeutig und sicher.
```

#### Das `mode`-Feld — wie wird verglichen?

| Modus          | Verhalten                                                        | Typischer Einsatz |
|----------------|------------------------------------------------------------------|-------------------|
| `"sequential"` | Der Bereichstext wird **zeilenweise/wortweise** verglichen, genau wie normaler Seitentext — nur eben isoliert vom Rest der Seite. Jeder Einzelunterschied (geändertes Datum, fehlender Doppelpunkt) erzeugt sein eigenes Delta. | Blöcke, die von beiden Drucksystemen in derselben Reihenfolge extrahiert werden, aber nicht mit dem umgebenden Text vermischt werden sollen (z. B. Absender-Infoblock, Briefkopfzeile). |
| `"unordered"`  | Der gesamte Bereichstext wird als **Zeichenmenge** verglichen (unabhängig von Reihenfolge und Whitespace). Wenn beide Seiten dieselben Zeichen enthalten, gilt der Bereich als identisch — auch wenn die Blöcke in völlig anderer Reihenfolge stehen. Bei Unterschied wird **ein einziges** Delta mit dem vollständigen Text beider Seiten erzeugt. | Bereiche, bei denen die Blockreihenfolge zwischen den Drucksystemen abweicht: ein System liefert einen Block pro Zeile (zeilenweise), das andere einen Block pro Spalte (spaltenweise). Typisch für mehrspaltige Fußzeilen von Großrechner-Drucksystemen. |

**Wie wähle ich den richtigen Modus?**

1. Führen Sie den Vergleich **zuerst ohne Vergleichsbereiche** durch und sehen Sie sich die Deltas an.
2. Wenn Sie feststellen, dass ein Bereich (z. B. Absenderblock) **falsche Deltas mit Text von einer anderen Stelle** erzeugt (Vermischung) → definieren Sie eine Region mit `"mode": "sequential"`.
3. Wenn Sie feststellen, dass ein Bereich (z. B. Fußzeile) **selbst nach der Trennung ein großes, unsinniges Delta** erzeugt, obwohl die Inhalte offensichtlich identisch sind → die Blockreihenfolge weicht ab, wechseln Sie auf `"mode": "unordered"`.

**Faustregel:** Beginnen Sie immer mit `"sequential"` (ist auch der Standard, wenn Sie `mode` weglassen). Nur wenn der sequenzielle Vergleich trotz korrekter Region noch unsinnige Deltas liefert, weil die Blockreihenfolge abweicht, wechseln Sie auf `"unordered"`.

**Bekannte Einschränkung von `"unordered"`:** Da nur die Zeichenmenge verglichen wird, würden zwei Texte, die exakt dieselben Buchstaben in anderer Reihenfolge enthalten (Anagramme), als identisch gelten. In der Praxis ist das bei Geschäftsdokumenten irrelevant — jede geänderte Ziffer, jedes fehlende Wort verändert die Zeichenmenge sofort. Bei Tabellen mit vielen gleichartigen Zahlenwerten könnte es theoretisch zu einem übersehenen Delta kommen.

#### Praxisbeispiel — drei Vergleichsbereiche auf einer Briefseite

Das folgende Beispiel zeigt ein reales Profil für Versicherungsdokumente mit drei unterschiedlichen Problemzonen:

```json
"compare_regions": [
  {
    "comment": "Fußleiste mit Unternehmensdaten (4-spaltig, Blockreihenfolge divergiert)",
    "page": 0,
    "x": 0,
    "y": 735,
    "width": 600,
    "height": 120,
    "mode": "unordered",
    "condition": "Registergericht Stuttgart"
  },
  {
    "comment": "Info-Block rechts oben (Sachbearbeiter, Telefon, Datum)",
    "page": 0,
    "x": 330,
    "y": 105,
    "width": 225,
    "height": 130,
    "mode": "sequential",
    "condition": "Es betreut Sie"
  },
  {
    "comment": "Absenderzeile über Adressfenster (Postfach variiert je Standort)",
    "page": 0,
    "x": 65,
    "y": 126,
    "width": 190,
    "height": 20,
    "mode": "sequential",
    "condition": "SV SparkassenVersicherung ·"
  }
]
```

**Warum welcher Modus?**

1. **Fußleiste** → `"unordered"`: Die Referenz liefert einen breiten Block pro Zeile (zeilenweise: Firma, Registergericht, Vorstand, Bank nebeneinander), der Kandidat liefert einen schmalen Block pro Spalte (spaltenweise: erst die ganze Firma-Spalte, dann Registergericht usw.). Dieselben 659 Zeichen, aber völlig andere Reihenfolge. Nur der Zeichenmengen-Vergleich erkennt: identisch, kein Delta.

2. **Info-Block** → `"sequential"`: Beide Drucksysteme extrahieren diesen Block in derselben Reihenfolge. Ohne die Region würde der Text mit der Empfängeradresse links vermischt. Mit der Region werden „Tel.:" → „Tel." und das geänderte Datum als eigene, saubere Deltas erkannt.

3. **Absenderzeile** → `"sequential"`: Dieselbe Zeile in beiden Dokumenten, aber ohne Region würde sie mit dem Fließtext darunter vermischt. Die Condition enthält den Mittepunkt „·" als Unterscheidungsmerkmal, weil der Firmenname allein zu unspezifisch ist.

#### Zusammenspiel von `exclude_regions` und `compare_regions`

Die beiden Regionstypen arbeiten in dieser Reihenfolge zusammen:

1. **Zuerst** werden Blöcke entfernt, die in einer `exclude_region` liegen → dieser Text ist unwiderruflich weg.
2. **Dann** werden Blöcke geprüft, die in einer `compare_region` liegen → wenn die `condition` matcht, werden sie vom restlichen Seitentext getrennt und separat verglichen.
3. Der **übrige** Seitentext (außerhalb aller Regionen) wird normal sequenziell verglichen.

**Wichtig:** Wenn sich eine `exclude_region` und eine `compare_region` überlappen, gewinnt die `exclude_region` — der überlappende Block wird entfernt, bevor die `compare_region` ihn sehen kann. Vermeiden Sie daher Überlappungen, es sei denn, Sie wollen gezielt einen Teil des Bereichs ausschließen (z. B. eine Barcode-Spalte innerhalb einer Fußzeile).

#### Vergleichsparameter in Regionen

Im Modus `"sequential"` werden alle Vergleichsparameter aus dem Profil übernommen: `case_sensitive`, `compare_mode`, `normalize_whitespace`, `merge_hyphenation` und `normalize_orphan_hyphens` gelten innerhalb der Region genauso wie für den Fließtext.

Im Modus `"unordered"` spielen diese Parameter keine Rolle, da der Vergleich rein auf der Zeichenmenge basiert (sämtlicher Whitespace wird entfernt, die Reihenfolge spielt keine Rolle). `case_sensitive` wirkt dort allerdings weiterhin — bei `false` werden die Zeichen vor dem Multiset-Vergleich in Kleinbuchstaben konvertiert.

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


## Vollständiges Beispielprofil

Das folgende Profil zeigt ein reales Szenario für Versicherungsdokumente, bei dem ein älteres Großrechner-Drucksystem (Referenz, Type3-Schriften) mit einem modernen Drucksystem (Kandidat) verglichen wird:

```json
{
  "version": "1.0",

  "case_sensitive": true,
  "normalize_whitespace": true,
  "compare_mode": "hybrid",
  "text_extraction": "native",
  "merge_hyphenation": false,
  "normalize_orphan_hyphens": true,
  "report_format": "pdf",

  "ocr": {
    "enabled": true,
    "confidence_threshold": 0.85,
    "dpi": 300,
    "mode_reference": "fallback",
    "mode_candidate": "fallback"
  },

  "exclude_regions": [
    { "comment": "Linke Seitenleiste mit Druckdaten (RIEDEL-Kennzeichen)",
      "page": 0,  "x": 0,    "y": 0,   "width": 64,  "height": 840  },
    { "comment": "Rechte Seitenleiste (Recyclingpapier-Hinweis)",
      "page": 0,  "x": 565,  "y": 0,   "width": 30,  "height": 840  }
  ],

  "compare_regions": [
    { "comment": "Fußleiste mit Unternehmensdaten (4-spaltig, Blockreihenfolge divergiert)",
      "page": 0,  "x": 0,    "y": 735, "width": 600, "height": 120,
      "mode": "unordered",
      "condition": "Registergericht Stuttgart" },
    { "comment": "Info-Block rechts oben (Sachbearbeiter, Telefon, Datum)",
      "page": 0,  "x": 330,  "y": 105, "width": 225, "height": 130,
      "mode": "sequential",
      "condition": "Es betreut Sie" },
    { "comment": "Absenderzeile über Adressfenster (Postfach variiert je Standort)",
      "page": 0,  "x": 65,   "y": 126, "width": 190, "height": 20,
      "mode": "sequential",
      "condition": "SV SparkassenVersicherung ·" }
  ]
}
```

**Warum diese Einstellungen?**

- `case_sensitive: true` — Groß-/Kleinschreibung ist bei Versicherungsdokumenten relevant.
- `normalize_whitespace: true` — Zwischen den Drucksystemen ändern sich Abstände, die inhaltlich nicht relevant sind.
- `compare_mode: "hybrid"` — Die Type3-Schriften des Altsystems erzeugen unzuverlässige Wortgrenzen; `hybrid` reduziert das Rauschen erheblich.
- `merge_hyphenation: false` — Viele zusammengesetzte Versicherungsbegriffe enthalten echte Bindestriche (z. B. „Gebäudeversicherung-AG"), die nicht zusammengezogen werden dürfen.
- `normalize_orphan_hyphens: true` — Verwaiste Trennstriche durch unterschiedliche Umbrüche sollen ignoriert werden.
- `ocr.mode: "fallback"` — Beide Dokumente haben nativen Text; OCR springt nur ein, wenn eine Seite rein bildbasiert sein sollte.
- Die `exclude_regions` entfernen die RIEDEL-Druckkennzeichen am linken und rechten Rand, die sich planmäßig unterscheiden.
- Die `compare_regions` isolieren drei Bereiche, die ohne Trennung mit dem umgebenden Text vermischt werden würden (siehe Erläuterung im Abschnitt `compare_regions`).


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


## Diagnose und Fehlerbehebung

### Coordinates ermitteln

Öffnen Sie das PDF in Adobe Acrobat oder einem anderen PDF-Viewer, der Koordinaten anzeigt. In Acrobat können Sie unter *Bearbeiten → Voreinstellungen → Einheiten und Hilfslinien* auf „Punkte" umstellen und dann mit dem Cursor die gewünschten Positionen ablesen.

**Tipp:** Definieren Sie Regionen lieber etwas großzügiger als knapp bemessen. Ein paar Punkte Puffer nach allen Seiten stellen sicher, dass Textblöcke auch dann noch innerhalb der Region liegen, wenn die Blockgeometrie zwischen den Drucksystemen leicht variiert. Wenn die Region über den Seitenrand hinausragt (z. B. `y + height > 842`), ist das unschädlich — es wird einfach kein Text außerhalb der Seite gefunden.

### Condition einer neuen Region prüfen

Bevor Sie eine neue `compare_region` produktiv einsetzen, prüfen Sie die `condition` gegen **beide** Dokumente (Referenz und Kandidat). Der wichtigste Check: Matcht die Condition **auf genau denselben Seiten** in beiden Dokumenten?

**Warnsignale:**

- **Einseitiger Match** (Condition matcht nur im Referenz- oder nur im Kandidat-Dokument auf einer bestimmten Seite): Die Blöcke werden nur auf einer Seite separiert, auf der anderen bleiben sie im Fließtext. Das erzeugt große, asymmetrische Deltas, die schwer zu interpretieren sind.
- **Unerwartete Treffer** (Condition matcht auf Seiten, wo sie nicht soll): Die Region greift auf falschen Seiten, separiert dort Blöcke und verfälscht den Vergleich. Wählen Sie eine spezifischere Condition.
- **Kein Treffer** (Condition matcht auf keiner Seite): Die Region ist wirkungslos. Prüfen Sie, ob der Text im PDF tatsächlich so steht wie in der Condition — bei Type3-Schriften können Leerzeichen an unerwarteten Stellen stehen (z. B. „Spark assenVersicherung").

### Häufige Fehlerquellen

**„Meine Region hat keinen Effekt"** — Drei mögliche Ursachen:
1. Die `condition` matcht nicht (Tippfehler, case-Unterschied, Sonderzeichen).
2. Die Region-Koordinaten verfehlen die relevanten Textblöcke (zu eng bemessen, falsches `page`-Feld).
3. Eine `exclude_region` überlappt die `compare_region` und entfernt die Blöcke, bevor die `compare_region` sie sehen kann.

**„Ich bekomme mehr Deltas als erwartet"** — Mögliche Ursachen:
1. Die `condition` ist zu unspezifisch und aktiviert die Region auf falschen Seiten.
2. Der `mode` ist `"sequential"`, aber die Blockreihenfolge weicht ab → wechseln Sie auf `"unordered"`.
3. `normalize_whitespace` oder `normalize_orphan_hyphens` sind nicht aktiviert, obwohl Whitespace-/Bindestrich-Unterschiede ignoriert werden sollen.

**„Ich bekomme ein einziges riesiges Delta statt vieler kleiner"** — Der `mode` ist `"unordered"` und die Inhalte unterscheiden sich tatsächlich. Im `unordered`-Modus gibt es nur ein Delta pro Region. Wenn Sie Einzeldeltas brauchen, wechseln Sie auf `"sequential"` und prüfen Sie, ob die Blockreihenfolge das erlaubt.

---


## Hinweise und Tipps

**Dateiformat:** Die Profildatei muss gültiges JSON sein. Achten Sie besonders auf korrekte Kommasetzung — nach dem letzten Eintrag in einem Objekt oder einer Liste darf **kein** Komma stehen. Nutzen Sie bei Bedarf einen JSON-Validator (z. B. [jsonlint.com](https://jsonlint.com)), um Syntaxfehler zu finden.

**Zeichenkodierung:** Speichern Sie die Datei in UTF-8-Kodierung. Das stellt sicher, dass Umlaute und Sonderzeichen in Mustern und Namen korrekt verarbeitet werden.

**Profilwahl:** Erstellen Sie pro Dokumenttyp ein eigenes Profil. Ein Profil für Rechnungen hat andere Ausschlussbereiche und Vergleichsregeln als eines für Kontoauszüge. Benennen Sie die Dateien aussagekräftig, z. B. `profil_rechnung.json`, `profil_kontoauszug.json`.

**Schrittweise konfigurieren:** Beginnen Sie mit einem minimalen Profil und fügen Sie Einstellungen einzeln hinzu. So können Sie die Auswirkung jeder Änderung gezielt nachvollziehen. Insbesondere bei `compare_regions` ist es hilfreich, eine Region nach der anderen hinzuzufügen und nach jeder Änderung einen Testvergleich durchzuführen.

**Das `comment`-Feld nutzen:** Verwenden Sie das `comment`-Feld in jeder Region. Auch wenn es für die Verarbeitung irrelevant ist, hilft es enorm bei der Wartung — nach einigen Wochen ist sonst kaum noch nachvollziehbar, warum eine Region an Position (65, 126) mit Breite 190 definiert wurde.

**Fehlerbehandlung:** Wenn eine Profildatei ungültig ist (fehlende Pflichtfelder, ungültige Werte, JSON-Syntaxfehler), zeigt PaperTrail Compare eine sprechende Fehlermeldung mit dem genauen Problem an. Die häufigsten Fehlerquellen sind fehlende Anführungszeichen, vergessene Kommas und ungültige Werte bei Auswahlfeldern.
