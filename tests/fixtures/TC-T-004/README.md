# Fixture: TC-T-004

**Echter Textunterschied ergibt Delta**

ref.pdf und cnd.pdf unterscheiden sich in drei Zeilen (Betrag, MwSt, Gesamt). Der Comparator muss has_delta == True liefern und alle drei Deltas melden.

## ref.pdf
Rechnung mit Betrag 100 EUR.

## cnd.pdf
Rechnung mit Betrag 200 EUR (+ angepasste MwSt und Gesamt).
