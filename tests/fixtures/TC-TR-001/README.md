# Fixture: TC-TR-001

**table_regions eliminiert False-Delta aus abweichender Blockstruktur**

ref.pdf schreibt die Fußzeile als einen breiten Block (eine Zeile über alle 'Spalten' hinweg), cnd.pdf als vier schmale, vertikal gestapelte Blöcke - PyMuPDF liefert dafür unterschiedliche Blockgrenzen, obwohl der Wortinhalt identisch ist. Ein sequenzieller Vergleich sähe hier reine Wortumstellungen als False-Deltas. Profil: table_region {page:1, x:0, y:650, width:400, height:250, condition:'SV SparkassenVersicherung'} → kein Delta erwartet.

## ref.pdf
Fließtext oben + Fußzeile als EIN breiter Block (eine Zeile).

## cnd.pdf
Identischer Fließtext + Fußzeile als VIER schmale Blöcke (vertikal gestapelt).
