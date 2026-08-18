# file:    engine/log_config.py
# purpose: Zentrale Logging-Konfiguration für die Python Core Engine -
#          einheitliches Format, ausschließlich stderr (siehe unten).
# author:  Kim Sieber
# created: 2026-08-18
# changed: 2026-08-18

"""Zentrale Logging-Konfiguration für die PaperTrail-Engine.

Alle Log-Ausgaben gehen auf stderr — stdout ist exklusiv für die
JSON-IPC mit dem Tauri-Sidecar reserviert und darf nicht beschrieben
werden."""

import logging
import sys

# Eigene Handler-Referenz statt "if root.handlers: return" - Test-Runner
# (pytest) und andere Frameworks hängen selbst schon Handler an den
# Root-Logger, bevor configure_logging() je aufgerufen wird; ein Check auf
# "irgendein Handler vorhanden" würde unseren stderr-Handler dann nie
# anlegen. Über die Modul-Referenz bleibt die Idempotenz (kein doppelter
# eigener Handler bei wiederholten Aufrufen) erhalten, ohne von fremden
# Handlern beeinflusst zu werden.
_handler: logging.Handler | None = None


def configure_logging(level: int = logging.WARNING) -> None:
    """Konfiguriert das Root-Logging mit einheitlichem Format auf stderr.

    Wird einmal beim Engine-Start aufgerufen (engine/__main__.py, main()).
    Wiederholte Aufrufe sind harmlos (handler-Duplikate werden vermieden);
    dabei wird der Stream bei jedem Aufruf auf das aktuelle sys.stderr
    aktualisiert, damit z. B. Test-Frameworks, die sys.stderr pro Testfall
    ersetzen (capsys), die Ausgabe weiterhin zuverlässig abfangen."""
    global _handler
    root = logging.getLogger()
    if _handler is None:
        _handler = logging.StreamHandler(sys.stderr)
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(_handler)
    else:
        _handler.stream = sys.stderr
    root.setLevel(level)
