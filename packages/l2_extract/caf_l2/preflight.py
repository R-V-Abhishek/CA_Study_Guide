"""Preflight PDF checks: page count, text layer presence, character density."""

from dataclasses import dataclass
import pymupdf as fitz


@dataclass
class PreflightResult:
    page_count: int
    has_text_layer: bool
    char_counts: list[int]


def preflight_check(doc: fitz.Document, char_threshold: int = 200) -> PreflightResult:
    """Preflight check on open fitz document.
    
    A document is considered to have a text layer if >= 70% of its pages
    have at least `char_threshold` characters (or >= 50 characters for short docs).
    """
    page_count = len(doc)
    if page_count == 0:
        return PreflightResult(page_count=0, has_text_layer=False, char_counts=[])

    char_counts = [len(page.get_text("text").strip()) for page in doc]
    
    if page_count <= 2:
        # For very short or single-page test docs
        has_text = any(c >= min(50, char_threshold) for c in char_counts)
    else:
        text_pages = sum(1 for c in char_counts if c >= char_threshold)
        has_text = (text_pages / page_count) >= 0.70

    return PreflightResult(
        page_count=page_count,
        has_text_layer=has_text,
        char_counts=char_counts,
    )
