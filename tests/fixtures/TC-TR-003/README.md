# Fixture: TC-TR-003

**table_regions im OCR-Zweig (gemischte Bitmap-Referenz / native Kandidat)**

ref.pdf ist eine reine Bitmap-Seite ohne nativen Textlayer (0 Fonts, wie Kims echte Referenzdokumente aus Großrechner-Druckoutput) - durchläuft zwangsläufig den OCR-Zweig von extract_pages_with_ocr_fallback, nicht den nativen Block-Zweig (siehe TC-TR-001/002). cnd.pdf hat nativen Text mit identischer Fußzeile. Profil: table_region {page:1, x:0, y:650, width:400, height:250, condition:'SV SparkassenVersicherung'} -> kein Delta erwartet.

## ref.pdf
Bitmap-Seite (kein nativer Text) mit Fliesstext + Fußzeile.

## cnd.pdf
Native Seite mit identischem Fliesstext + Fußzeile.
