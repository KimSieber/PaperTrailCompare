# Fixture: TC-TR-002

**compare_regions erkennt echte inhaltliche Änderung weiterhin**

Wie TC-TR-001 (unterschiedliche Blockstruktur), aber die Telefonnummer in der Kandidaten-Fußzeile ist tatsächlich geändert ('Tel: 0800-1234' -> 'Tel: 0800-5678'). Der Multiset-Vergleich muss trotz ignorierter Wortreihenfolge ein Delta für die geänderten Wörter melden.

## ref.pdf
Fußzeile (1 breiter Block) mit 'Tel: 0800-1234'.

## cnd.pdf
Fußzeile (4 schmale Blöcke) mit 'Tel: 0800-5678' statt '...-1234'.
