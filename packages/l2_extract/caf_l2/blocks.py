"""Positioned block extraction, cleaning, and text normalization."""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import re
import unicodedata
from uuid import uuid4
import pymupdf as fitz

LIGATURE_MAP = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

# Known PUA or variant codepoints for Rupee sign
RUPEE_MAP = {
    "\uf0b9": "₹",
    "\u20a8": "₹",
    "`": "`",  # Keep normal backtick
}

PAGE_NUM_REGEX = re.compile(
    r"^\s*(?:page\s*)?[-–—]?\s*\d{1,3}(?:\s*(?:of|/)\s*\d{1,3})?\s*[-–—]?\s*$",
    re.IGNORECASE,
)


@dataclass
class LineBlock:
    block_id: str
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    size: float
    bold: bool
    font: str
    raw_text: str = ""
    origin: str = "pdf"
    order: int = 0
    region: str = "question"
    fidelity_flags: tuple[str, ...] = ()
    numbering_scope: str = ""


def normalize_text(text: str) -> str:
    """Apply NFKC normalization, ligatures, rupee symbols, and whitespace cleanup."""
    # 1. NFKC
    res = unicodedata.normalize("NFKC", text)

    # 2. Ligatures
    for lig, repl in LIGATURE_MAP.items():
        res = res.replace(lig, repl)

    # 3. Rupee symbols
    for pua, repl in RUPEE_MAP.items():
        res = res.replace(pua, repl)

    # 4. Collapse runs of spaces/tabs (preserving line breaks if multi-line)
    res = re.sub(r"[ \t]+", " ", res)
    return res.strip()


@dataclass(frozen=True)
class OCRConfig:
    language: str = "eng"
    dpi: int = 300
    min_native_chars: int = 10
    tessdata: str | None = None


class OCRUnavailableError(RuntimeError):
    """A page requires OCR but no usable worker was configured."""


def _page_dictionary(page: fitz.Page, config: OCRConfig | None, source_hash: str | None, cache_dir: Path | None) -> tuple[dict, str]:
    native = page.get_text("dict", sort=True)
    native_chars = len(page.get_text("text").strip())
    needs_ocr = native_chars < (config.min_native_chars if config else 10) and bool(page.get_images())
    if not needs_ocr:
        return native, "pdf"
    if config is None:
        raise OCRUnavailableError(f"ocr_unavailable: page {page.number + 1} requires a configured OCR worker")
    digest = source_hash or hashlib.sha256(page.parent.tobytes()).hexdigest()
    key = hashlib.sha256(json.dumps({"source": digest, "page": page.number, "config": asdict(config), "worker": "pymupdf-" + fitz.VersionBind}, sort_keys=True).encode()).hexdigest()
    cache = cache_dir / f"{key}.json" if cache_dir else None
    if cache and cache.exists():
        return json.loads(cache.read_text()), "ocr"
    if not shutil.which("tesseract"):
        raise OCRUnavailableError(f"ocr_unavailable: Tesseract is missing (page {page.number + 1})")
    try:
        textpage = page.get_textpage_ocr(language=config.language, dpi=config.dpi, full=True, tessdata=config.tessdata)
        result = page.get_text("dict", textpage=textpage, sort=True, flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    except (RuntimeError, ValueError) as exc:
        raise OCRUnavailableError(f"ocr_unavailable: page {page.number + 1}: {exc}") from exc
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_name(f"{key}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(result))
        temporary.replace(cache)
    return result, "ocr"


def extract_raw_lines(doc: fitz.Document, *, ocr_config: OCRConfig | None = None, source_hash: str | None = None, cache_dir: Path | None = None, ignored_pages: set[int] | None = None) -> list[tuple[int, float, float, LineBlock]]:
    """Extract raw lines with page height and position info."""
    raw_lines: list[tuple[int, float, float, LineBlock]] = []

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        if ignored_pages and page_num in ignored_pages:
            continue
        page_rect = page.rect
        page_height = page_rect.height
        page_dict, origin = _page_dictionary(page, ocr_config, source_hash, cache_dir)

        # Preserve plain text rows while making uncertain table structure visible.
        row_columns: dict[int, set[int]] = defaultdict(set)
        for block in page_dict.get("blocks", []):
            for entry in block.get("lines", []):
                bounds = entry.get("bbox", (0, 0, 0, 0))
                row_columns[round(bounds[1] / 3)].add(round(bounds[0] / 20))
        paired_rows = {row for row, columns in row_columns.items() if len(columns) >= 2}
        possible_table_rows = paired_rows if len(paired_rows) >= 3 else set()
        line_counter = 0
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 is text
                continue
            for line in block.get("lines", []):
                line_counter += 1
                spans = line.get("spans", [])
                if not spans:
                    continue

                line_text = "".join(s.get("text", "") for s in spans)
                clean_text = normalize_text(line_text)
                if not clean_text:
                    continue

                max_size = max(s.get("size", 10.0) for s in spans)
                is_bold = any(
                    bool(s.get("flags", 0) & 16) or "bold" in s.get("font", "").lower()
                    for s in spans
                )
                font_name = spans[0].get("font", "")
                bbox = tuple(line.get("bbox", (0, 0, 0, 0)))

                block_id = f"p{page_num}-b{line_counter}"
                flags = []
                if origin == "ocr":
                    flags.append("OCR_REVIEW_REQUIRED")
                if round(bbox[1] / 3) in possible_table_rows:
                    flags.append("TABLE_STRUCTURE_REVIEW_REQUIRED")
                if any(symbol in line_text for symbol in ("√", "∑", "∫")) or "symbol" in font_name.lower():
                    flags.append("FORMULA_STRUCTURE_REVIEW_REQUIRED")
                lb = LineBlock(
                    block_id=block_id,
                    page=page_num,
                    bbox=bbox,  # type: ignore[arg-type]
                    text=clean_text,
                    size=max_size,
                    bold=is_bold,
                    font=font_name,
                    raw_text=line_text,
                    origin=origin,
                    order=len(raw_lines),
                    fidelity_flags=tuple(flags),
                )
                # Store (page_num, page_height, y_mid, LineBlock)
                y_mid = (bbox[1] + bbox[3]) / 2.0
                raw_lines.append((page_num, page_height, y_mid, lb))

    return raw_lines


PROTECTED_CONTENT_REGEX = re.compile(
    r"^\s*(?:question\s*(?:no\.?)?\s*\d+|case\s+scenario\b|\([a-hA-H]\))",
    re.IGNORECASE,
)


def build_block_stream(doc: fitz.Document, *, ocr_config: OCRConfig | None = None, source_hash: str | None = None, cache_dir: Path | None = None, ignored_pages: set[int] | None = None) -> list[LineBlock]:
    """Build cleaned, positioned block stream stripping repeating headers and footers."""
    raw = extract_raw_lines(doc, ocr_config=ocr_config, source_hash=source_hash, cache_dir=cache_dir, ignored_pages=ignored_pages)
    page_count = len(doc)
    if not raw or page_count <= 1:
        return [item[3] for item in raw]

    # Collect normalized patterns in top 8% and bottom 8%
    top_patterns: Counter[str] = Counter()
    bottom_patterns: Counter[str] = Counter()
    pattern_pages: dict[str, set[int]] = {}

    for page_num, height, y_mid, lb in raw:
        if PROTECTED_CONTENT_REGEX.search(lb.text):
            continue
        norm_key = re.sub(r"\d+", "#", lb.text.lower())
        if y_mid <= 0.08 * height:
            top_patterns[norm_key] += 1
            pattern_pages.setdefault(norm_key, set()).add(page_num)
        elif y_mid >= 0.92 * height:
            bottom_patterns[norm_key] += 1
            pattern_pages.setdefault(norm_key, set()).add(page_num)

    # Repeating threshold: occurring on >= 50% of pages
    min_pages = max(2, int(0.50 * page_count))
    strip_patterns = {
        pat for pat, pages in pattern_pages.items() if len(pages) >= min_pages
    }

    cleaned: list[LineBlock] = []
    for page_num, height, y_mid, lb in raw:
        if PROTECTED_CONTENT_REGEX.search(lb.text):
            cleaned.append(lb)
            continue

        # Check repeating headers / footers
        norm_key = re.sub(r"\d+", "#", lb.text.lower())
        if norm_key in strip_patterns:
            if y_mid <= 0.08 * height or y_mid >= 0.92 * height:
                continue

        # Check standalone page numbers in top 10% or bottom 10%
        if y_mid <= 0.10 * height or y_mid >= 0.90 * height:
            if PAGE_NUM_REGEX.match(lb.text):
                continue

        cleaned.append(lb)

    return cleaned
