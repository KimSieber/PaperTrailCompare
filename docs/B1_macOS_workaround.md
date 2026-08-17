# B1 — macOS: „App ist beschädigt" nach Download

## Problem

Nach Download der `.dmg` zeigt macOS die Meldung:
> „PaperTrail Compare.app" ist beschädigt und kann nicht geöffnet werden.

## Ursache

macOS Gatekeeper setzt beim Download das `com.apple.quarantine`-Attribut.
Ohne gültige Apple-Code-Signatur + Notarization wird die App blockiert.
Aus dem Terminal gestartet (ohne Quarantine-Flag) funktioniert sie einwandfrei.

## Status

Strukturelles Problem — Lösung erfordert:
1. Gewerbeanmeldung (Spur A)
2. Apple Developer Account (99 $/Jahr)
3. Code-Signing-Zertifikat + Notarization in Build-Pipeline

Betrifft sowohl die Tauri-App als auch den PyInstaller-Sidecar
(`codesign_identity=None` in `papertrail-engine.spec`).

## Workaround für Kundentest

Nach dem Download im Terminal ausführen:

```bash
xattr -cr /Applications/PaperTrail\ Compare.app
```

Alternativ, falls die .app an einem anderen Ort liegt:

```bash
xattr -cr /pfad/zu/PaperTrail\ Compare.app
```

Danach startet die App normal per Doppelklick.

## Ergänzung in docs/manual-tests.md

Folgender Punkt sollte in die TC-S-003-Checkliste aufgenommen werden:

```
- [ ] (macOS, solange unsigniert) Nach Download/Kopie der .app:
      `xattr -cr /Applications/PaperTrail\ Compare.app` ausführen,
      um das Quarantine-Flag zu entfernen.
```
