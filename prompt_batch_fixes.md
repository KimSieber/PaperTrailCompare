# Claude Code Prompt: Batch-Verarbeitung — Korrekturen nach manuellem Test

## Kontext

Die Batch-Verarbeitung (BatchView, `start_batch_compare`, NDJSON-Streaming,
`batch-progress`-Events, `generate_batch_report`) wurde in der letzten Session
implementiert; 131/131 Python-Tests grün. Der manuelle Test hat vier Punkte
ergeben, die jetzt behoben werden sollen.

Alle Änderungen unterliegen weiterhin den Projektgrundsätzen: alles lokal,
keine Netzwerkzugriffe, TDD (Test zuerst), synthetische Fixture-PDFs statt
echter Kundendokumente.

---

## Punkt 1 — Einzel-Reports werden nicht im Ausgabeverzeichnis abgelegt

**Beobachtung:** Nach einem Batch-Lauf liegt im gewählten Ausgabeverzeichnis
nur der Batch-Report. Die erwarteten Einzel-Reports pro Dateipaar fehlen.

**Bitte zuerst diagnostizieren, bevor implementiert wird:**
- Werden pro Paar überhaupt Einzel-Reports erzeugt (ruft der Batch-Pfad
  `generate_report` bzw. das Äquivalent des Einzelvergleichs auf)?
- Falls ja: Landen sie am falschen Ort, z.B. unter
  `~/Documents/PaperTrailCompare/YYYY-MM-DD/` wie beim Einzelvergleich,
  statt im gewählten Ausgabeverzeichnis? → Pfad-Bug.
- Falls nein: Feature fehlt und muss ergänzt werden.

Bitte das Diagnoseergebnis kurz berichten, **bevor** die Änderung umgesetzt wird.

**Soll-Verhalten:**
- Für **jedes** Dateipaar wird ein Einzel-Report erzeugt — auch bei 0 Deltas.
- Ablage **flach** direkt im vom Benutzer gewählten Ausgabeverzeichnis
  (kein Unterordner, nicht `~/Documents/...`).
- Namensmuster wie beim Einzelvergleich (`{RefStem}_{CndStem}_...`).
  Kollisionen sind der Normalfall nicht; **falls** ein Zielname bereits
  existiert, wird ein Zähler bzw. die CSV-Zeilennummer angehängt, sodass
  keine Datei überschrieben wird.
- Paare mit `status="error"` (fehlende Datei) erzeugen naturgemäß keinen
  Einzel-Report — das ist kein Fehler, aber im Batch-Report als solches
  erkennbar (siehe Punkt 4).

---

## Punkt 2 — GUI-Ergebnisliste läuft horizontal aus dem Fenster

**Beobachtung:** Lange Dateinamen verbreitern die Tabelle so stark, dass
horizontal gescrollt werden muss.

**Soll-Verhalten:**
- Die Tabelle passt **immer** in die verfügbare Fensterbreite; **kein**
  horizontales Scrollen. Vertikales Scrollen der Liste bleibt wie bisher.
- Vier Spalten: Referenz-Dateiname, Kandidat-Dateiname, Anzahl Deltas,
  Übereinstimmung in %. Die beiden Zahlenspalten bekommen eine feste,
  schmale Breite; die beiden Namensspalten teilen sich den Rest flexibel.
- Dateinamen werden **in der Mitte gekürzt** (z.B. `langer…name.pdf`), sodass
  Anfang und die Endung/das Ende des Namens sichtbar bleiben.
- Der **vollständige** Pfad/Dateiname erscheint als Tooltip
  (`title`-Attribut bzw. projektübliches Tooltip-Pattern) beim Hovern.
- Auch die Fehlerzeilen (rot) müssen in dieses Layout passen; der
  Fehlertext darf die Spaltenbreiten nicht sprengen (ggf. ebenfalls kürzen
  mit vollem Text im Tooltip).

---

## Punkt 3 — Batch-Report-PDF druckt über den rechten Seitenrand hinaus

**Beobachtung:** Lange Dateinamen laufen im PDF rechts aus dem Satzspiegel.

**Soll-Verhalten:**
- Im PDF-Report werden die Dateinamen **umgebrochen, nicht gekürzt**
  (im Report soll der vollständige Name lesbar sein — anders als in der GUI).
- Alle Spalten bleiben innerhalb des Satzspiegels; Zeilenhöhe passt sich
  dem Umbruch an. Tabellenkopf und Spaltenausrichtung bleiben über
  Seitenumbrüche hinweg korrekt (Kopfzeile auf Folgeseiten wiederholen).

---

## Punkt 4 — Batch-Report soll professionell wie die Einzel-Reports aussehen

**Soll-Verhalten:** Der Batch-Report übernimmt das Layout-Vokabular der
bestehenden Einzel-Reports (bitte den vorhandenen Einzel-Report-Code als
Vorlage nehmen und gemeinsame Layout-Bausteine wo sinnvoll extrahieren
statt zu duplizieren):

- Logo und Titel im Kopfbereich, gleiche Typografie/Farbgebung wie Einzelreport
- Kennzahlen-Kästchen im Kopfbereich mit u. a.:
  - Anzahl Dateipaare gesamt
  - Anzahl erfolgreich verarbeitet
  - Anzahl Fehler
  - **Erfolgs-/Fehlerquote in %**
  - Gesamtzahl verarbeiteter Seiten
  - Gesamtlaufzeit
  - Zeitstempel des Laufs
  - ggf. verwendetes Profil / relevante Vergleichsoptionen, sofern der
    Einzelreport das ebenfalls ausweist
- Danach die Haupttabelle aller Paare (Ref, Cnd, Deltas, Übereinstimmung %).
- Fehlerpaare werden **nur in der Haupttabelle** markiert (z. B. farblich
  und mit Fehlerhinweis statt Zahlenwerten) — **keine** eigene Fehlersektion.

---

## Arbeitsweise (bitte einhalten)

- **Schritt für Schritt, nach max. 2 Schritten pausieren** und auf Rückmeldung
  warten.
- Vorgeschlagene Reihenfolge:
  1. Punkt 1 diagnostizieren und Ergebnis berichten (**hier pausieren**)
  2. Punkt 1 beheben (Test zuerst: Einzel-Reports landen im gewählten
     Ausgabeverzeichnis, auch bei 0 Deltas; Kollisionsfall)
  3. Punkt 2 (GUI-Layout, Mitte-Kürzung, Tooltip)
  4. Punkt 3 (PDF-Umbruch, Satzspiegel, Kopfzeilenwiederholung)
  5. Punkt 4 (Kopfbereich mit Kennzahlen + Layoutangleichung an Einzelreport)
  6. Manueller End-to-End-Test mit der bestehenden Fixture-CSV
     (inkl. TC-B-002-Fall mit fehlender Datei) und einer Test-CSV mit
     bewusst sehr langen Dateinamen zur Layout-Prüfung
- **TDD**, wo automatisiert testbar (Punkt 1, Kollisionslogik, Kennzahlen-
  Berechnung inkl. Quoten). Reine Layout-Aspekte (Punkt 2/3/4) werden manuell
  verifiziert — dafür bitte am Ende einen erzeugten Beispiel-Report bereitstellen
  bzw. den Pfad nennen, damit ich ihn ansehen kann.
- Vor dem Start bitte kurz prüfen, ob der Stand seit der letzten Session
  unverändert ist, und ob die noch nicht committeten Änderungen der letzten
  Session vorliegen.
- Commit an sinnvollen Meilensteinen nach grünem `pytest`.
