# Fixture: TC-R-001-seitenumbruch

**Delta-Markierung bei unterschiedlichem Seitenumbruch**

ref.pdf verteilt den Text auf 2 Seiten, cnd.pdf hat denselben Text (mit einem Delta '100'->'200') auf nur 1 Seite. Die gemeldete Delta-Seite (Kandidat-Seite 1) stimmt nicht mit der tatsächlichen Fundstelle im Referenz-Dokument (Seite 2) überein – report_generator muss trotzdem korrekt markieren.

## ref.pdf
Seite 1: Einleitungstext. Seite 2: Betrag 100 EUR.

## cnd.pdf
Seite 1: Einleitungstext + Betrag 200 EUR (beides auf einer Seite).
