# Task: Wire up the vendored German Tesseract language model

## Context

The Windows CI run reached the pytest gate with 4 failures, all sharing one
cause:

```
Error opening data file C:\Program Files\Tesseract-OCR/tessdata/deu.traineddata
Failed loading language 'deu'
```

The Chocolatey `tesseract` package ships the binary but **not** the German
language model. Previously these tests were skipped because no Tesseract binary
existed at all; now that the binary is found, they run and fail on the missing
language data.

This is not only a test problem: `_stage_tesseract_windows` in
`packaging/build_sidecar.py` is supposed to bundle the same file into the
PyInstaller sidecar. If it is absent on the build machine, bundling fails too.

**Decision taken:** vendor the model into the repository so the build no longer
depends on what Chocolatey or Homebrew happen to ship, and works identically on
macOS and Windows without network access.

The file has already been placed manually at:

```
vendor/tessdata/deu.traineddata
```

Source: https://github.com/tesseract-ocr/tessdata (main branch), standard
`tessdata` set, ~14.7 MB, Apache-2.0.

## Scope

### 1. Repository hygiene — do this FIRST

- Verify `vendor/tessdata/deu.traineddata` exists and report its size. If it is
  missing or implausibly small, stop and report instead of proceeding.
- Add `*.traineddata binary` to `.gitattributes`. This is critical: without it
  the file is exposed to the same Windows CRLF mangling that corrupted the
  fixture PDFs in the previous round.
- Confirm the file is not excluded by `.gitignore`.
- The file is ~15 MB, which is well within normal Git limits. Do **not**
  introduce Git LFS.

### 2. Build pipeline — `packaging/build_sidecar.py`

- `_find_tessdata_deu` must prefer the vendored file at
  `vendor/tessdata/deu.traineddata`, resolved relative to the repository root
  (derive it from `Path(__file__)`, never from the current working directory).
- Keep the existing system-path search as a fallback, but the vendored copy
  takes precedence on every platform.
- If neither is found, fail with an explicit, actionable error message rather
  than letting PyInstaller produce a sidecar with no language data.
- Do not otherwise modify `_stage_tesseract_windows` — the binary and DLL
  staging is a separate open issue and out of scope here.

### 3. Tests

- The OCR tests must pass on any machine that has a Tesseract binary,
  regardless of which languages that installation provides.
- Point `TESSDATA_PREFIX` at the vendored directory for the test session
  (a session-scoped fixture in `tests/conftest.py` is the natural place).
- Note the version-dependent semantics: Tesseract 5 expects `TESSDATA_PREFIX`
  to point at the `tessdata` directory itself, older versions expect its
  parent. The existing bundle code in `engine/ocr_extractor.py` already sets it
  to the directory itself — verify this and stay consistent with whatever that
  code does.
- The four currently failing tests are:
  - `tests/test_ocr_extractor.py::test_tc_o_001_gescannten_text_via_ocr_erkennen`
  - `tests/test_ocr_extractor.py::test_tc_o_002_gemischtes_pdf_nativer_und_gescannter_text`
  - `tests/test_pdf_extractor.py::test_extract_pages_for_profile_ocr_aktiviert_nutzt_fallback`
  - `tests/test_pdf_extractor.py::test_extract_pages_for_profile_mode_force_liest_auch_native_seiten_per_ocr`
- Do not weaken any assertion to make a test pass.

### 4. Licensing

The tessdata files are Apache-2.0. Add an attribution entry wherever the
project already records third-party licences. If no such file exists, create
`vendor/tessdata/README.md` recording the source URL, the licence, and the date
of retrieval. Report which option you chose.

### 5. Out of scope

- `.github/workflows/build.yml` — the Chocolatey step stays as it is; we still
  need the Tesseract **binary** from it, only the language data now comes from
  the repository
- `_stage_tesseract_windows` binary/DLL staging
- `tauri.conf.json`
- the macOS job failure
- the leftover absolute paths in the committed `tests/fixtures/*/filelist.csv`

## Verification

1. `python -m pytest` — expect 139 passed, 0 failed.
2. Temporarily rename the local system tessdata directory (or otherwise make the
   system `deu.traineddata` unreachable) and run pytest again — it must still
   pass, proving the vendored copy is genuinely the one being used. Restore
   afterwards.
3. Report the resolved path that `_find_tessdata_deu` returns.

Commit with a descriptive message. **Do not push.**
