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
"""

__version__ = "0.1.0"
