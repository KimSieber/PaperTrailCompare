# Fixture: TC-O-001

**Gescannten Text via OCR erkennen**

Beide PDFs bestehen aus einer eingebetteten Bitmap (Pillow-Rendering) ohne Textlayer. PyMuPDF liefert für diese Seite leeren Text; engine.ocr_extractor muss den Inhalt via Tesseract (deu) erkennen.

## ref.pdf
Gerenderte Scan-Seite mit Auftragsdaten.

## cnd.pdf
Identische gerenderte Scan-Seite.
