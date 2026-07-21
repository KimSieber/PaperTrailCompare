# Fixture: TC-B-003

**Batch per XMP-Metadaten (Document-ID)**

20 PDFs (10 ref + 10 cnd). Jedes Pärchen teilt dieselbe Document-ID, eingebettet als echtes XMP-Metadatenpaket (dc:identifier) via PyMuPDF (doc.set_xml_metadata). batch_compare_by_xmp() muss die 10 Paare korrekt zuordnen.

## ref.pdf
ref_01.pdf … ref_10.pdf, je mit Document-ID DOC-2026-0001 … 0010.

## cnd.pdf
cnd_01.pdf … cnd_10.pdf, gleiche Document-IDs.
