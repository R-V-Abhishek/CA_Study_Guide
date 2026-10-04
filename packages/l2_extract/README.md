# caf-l2
L2 Extraction: extraction profiles, regex anchors, validation, marks checking, and answer pairing.

Extraction writes immutable candidates. Current units, decisions and publication history change only through explicit administrator promotion; failed parses retain the old current revision. Ordered blocks retain native/OCR origin, raw text, normalized text, page and bounding box. Whole questions contain shared context, ordered parts, nested available answers, MCQ keys, choices and actual source spans. Analytical units remain available for classification.

Profiles must declare role, layout and answer expectations. Unknown roles return `unsupported_profile`. Practice collections may have no total-marks expectation. Combined PDFs require confirmed paper ranges; separate answer PDFs require a confirmed identity pair and matching paper scopes. Answer-only documents preserve source evidence without creating question duplicates.

```sh
uv run caf extract run --help
uv run caf extract run --doc 123 --dry-run
uv run caf extract run --doc 123 --ocr
uv run caf extract compare 45
uv run caf extract promote 45 --expected-current 40
```

OCR is opt-in through `--ocr` or `config/settings.toml`'s `[ocr]` settings. Install Tesseract on an extraction worker (`brew install tesseract` on macOS, or the distribution's `tesseract-ocr` package on Linux); PyMuPDF calls it selectively for raster pages. Missing dependencies produce an explicit failure. OCR cache entries include source hash, page, language, DPI and PyMuPDF version and live under the backed-up blob tree. Native extraction remains the first choice. Tables, calculations, images and OCR require source-page review; numerical answers are never rewritten by an LLM.

The curator **Extraction Review** workspace exposes source pages, content trees, ordered blocks, crops, pairing candidates, corrections, immutable revision comparisons and separate quality dimensions. Active accounts can review quality; metadata, document pairing, corrections and promotion require administrators. Source-page endpoints use document IDs and validated page bounds.

`uv run scripts/phase4_corpus.py --commit --ocr --limit 1000` prepares unpublished candidates from the verified source report, preserving metadata conflicts for review. `uv run scripts/phase4_inspect.py` validates runtime contracts and records coverage and original-data preservation. See `docs/Phase4_Verification.md` for the actual coverage and remaining gates.
