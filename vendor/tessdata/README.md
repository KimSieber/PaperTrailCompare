# Vendored Tesseract language data

`deu.traineddata` — German language model for Tesseract 5 OCR.

- Source: https://github.com/tesseract-ocr/tessdata (main branch, standard `tessdata` set)
- Licence: Apache License 2.0
- Retrieved: 2026-07-31

Vendored into the repository so the build and test suite depend on a fixed,
known-good language model instead of whatever a package manager (Chocolatey,
Homebrew) happens to ship at build time (see Architekturentscheidung #3 in
CLAUDE.md: only the German model is bundled).
