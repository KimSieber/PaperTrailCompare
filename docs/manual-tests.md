# Manuelle Systemtests

Diese Checkliste deckt Testfälle ab, die laut Testspezifikation
(`doc/PaperTrailCompare_Testspezifikation.docx`, Abschnitt 9) **manuell**
auf einer echten Zielmaschine durchzuführen sind, nicht per Unit-/
Integrationstest automatisierbar. Voraussetzung: der PyInstaller-Build
(Architekturentscheidung #2, siehe `CLAUDE.md` Abschnitt 6) existiert.

## TC-S-003 — Betrieb ohne Serverinstallation (Standalone)

**Vorbedingung:** Frische Maschine (Windows oder macOS) ohne Admin-Rechte,
ohne vorherige Installation von PaperTrail Compare, ohne Internetverbindung.

**Ziel:** Verifizieren, dass die Anwendung ohne Serverdienst, ohne
separate Python-Installation und ohne Admin-Rechte startet und
funktioniert.

### Checkliste

- [ ] Zielmaschine ist frisch (kein vorheriger PaperTrail-Compare-Build,
      kein system-weites Python mit den Projekt-Dependencies installiert).
- [ ] Internetverbindung der Maschine ist deaktiviert (WLAN aus / Kabel
      gezogen) — bleibt für den gesamten Testlauf deaktiviert.
- [ ] Installer (`.msi`/`.exe` unter Windows, `.dmg`/`.app` unter macOS)
      wird ausschließlich mit einem **Standard-Benutzerkonto ohne
      Admin-/Root-Rechte** ausgeführt.
- [ ] Installation läuft ohne Rückfrage nach Admin-Freigabe/UAC-Prompt
      durch, die ein Standard-Benutzerkonto nicht bestätigen könnte.
- [ ] Nach der Installation ist **kein zusätzlicher Dienst/Prozess** im
      Hintergrund aktiv, der einen Netzwerk-Port öffnet (prüfen z.B. via
      `netstat -an` / Aktivitätsanzeige — es darf kein von PaperTrail
      Compare geöffneter horchender Port erscheinen).
- [ ] Anwendung startet über den regulären Programm-Eintrag (Startmenü /
      Programme-Ordner) ohne Fehlermeldung.
- [ ] `papertrail-compare --version` (bzw. Äquivalent über die GUI, falls
      keine CLI exponiert ist) liefert eine Versionsangabe ohne Fehler.
- [ ] Ein einfacher Einzelvergleich (zwei Beispiel-PDFs) lässt sich über
      die GUI durchführen und liefert ein Ergebnis — ganz ohne
      Internetverbindung.
- [ ] Deinstallation (falls getestet) entfernt die Anwendung vollständig,
      ohne Admin-Rechte zu benötigen.

**Erwartetes Ergebnis:** Anwendung installiert, startet und führt einen
Vergleich durch — vollständig lokal, ohne Serverdienst, ohne Admin-Rechte,
ohne Internetverbindung.

---

## Hinweis zu verwandten, bereits automatisierten Testfällen

- **TC-S-001** (keine Netzwerkverbindung während der Verarbeitung) und
  **TC-S-002** (temporäre Dateien werden bereinigt) sind als pytest-Tests
  automatisiert, siehe `tests/test_privacy_compliance.py`. Sie decken die
  Python-Code-Ebene ab (kein `socket`-Aufruf im eigenen Code, keine
  Temp-Dateien im Dateisystem), **nicht** das fertige Installer-Artefakt.
  Ein zusätzlicher manueller Lauf mit einem echten Netzwerk-Monitor
  (z.B. Little Snitch/Wireshark) auf dem PyInstaller-Build ist sinnvoll,
  sobald dieser existiert, um auch native Bibliotheksaufrufe (PyMuPDF,
  Tesseract) abzudecken, die pytest nicht instrumentieren kann.
