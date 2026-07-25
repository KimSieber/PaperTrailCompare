# Fixture: TC-T-009

**Wortrekonstruktion bei Sperrsatz ohne Leerzeichen-Glyph**

ref.pdf setzt 'SparkassenVersicherung' Buchstabe für Buchstabe mit erhöhter, aber gleichmäßiger Laufweite (kein echtes Leerzeichen-Zeichen). Da alle Glyphenlücken gleich groß sind, findet die Space-Breiten-Kalibrierung keinen klaren Sprung zwischen Intra-Wort- und Wortgrenzen-Abstand und muss auf die native Extraktion zurückfallen (Sicherheits-Fallback statt Rateverfahren).

## ref.pdf
'SparkassenVersicherung' mit gleichmäßiger Laufweite, kein Space-Glyph.

## cnd.pdf
Normaler Fließtext mit echten Leerzeichen (Gegenprobe, unverändert).
