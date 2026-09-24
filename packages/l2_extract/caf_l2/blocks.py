"""Positioned block extraction, cleaning, and text normalization."""

from collections import Counter
from dataclasses import dataclass
import re
import unicodedata
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


def extract_raw_lines(doc: fitz.Document) -> list[tuple[int, float, float, LineBlock]]:
    """Extract raw lines with page height and position info."""
    raw_lines: list[tuple[int, float, float, LineBlock]] = []

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        page_rect = page.rect
        page_height = page_rect.height
        page_dict = page.get_text("dict", sort=True)

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
                lb = LineBlock(
                    block_id=block_id,
                    page=page_num,
                    bbox=bbox,  # type: ignore[arg-type]
                    text=clean_text,
                    size=max_size,
                    bold=is_bold,
                    font=font_name,
                )
                # Store (page_num, page_height, y_mid, LineBlock)
                y_mid = (bbox[1] + bbox[3]) / 2.0
                raw_lines.append((page_num, page_height, y_mid, lb))

    return raw_lines


PROTECTED_CONTENT_REGEX = re.compile(
    r"^\s*(?:question\s*(?:no\.?)?\s*\d+|case\s+scenario\b|\([a-hA-H]\))",
    re.IGNORECASE,
)


def build_block_stream(doc: fitz.Document) -> list[LineBlock]:
    """Build cleaned, positioned block stream stripping repeating headers and footers."""
    raw = extract_raw_lines(doc)
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
