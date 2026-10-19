"""Deterministic source selection and PDF heading evidence for textbook drafts.

These helpers never approve a descriptor or infer an examination attempt from retrieval time.
"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re

import pymupdf


@dataclass(frozen=True)
class TextbookSection:
    section_key: str
    edition: str
    applicable_attempts: tuple[str, ...]
    download_url: str
    verified: bool


@dataclass(frozen=True)
class SectionSelection:
    section_key: str
    section: TextbookSection | None
    fallback: bool
    gap: str | None


def select_sections(
    expected_sections: list[str],
    available_sections: list[TextbookSection],
    target_attempt: str = "2027-05",
) -> list[SectionSelection]:
    """Prefer verified target material; only January 2026 can fill a missing section."""
    selections = []
    for key in expected_sections:
        candidates = [s for s in available_sections if s.section_key == key and s.verified]
        target = [s for s in candidates if target_attempt in s.applicable_attempts]
        fallback = [s for s in candidates if "2026-01" in s.applicable_attempts]
        chosen = target or fallback
        if len(chosen) > 1:
            raise ValueError(f"Ambiguous verified edition for section {key}")
        selections.append(SectionSelection(
            key, chosen[0] if chosen else None, not target and bool(fallback),
            None if chosen else "No verified target or January 2026 section",
        ))
    return selections


@dataclass(frozen=True)
class HeadingEvidence:
    number: str
    title: str
    pdf_page: int
    instrument_context: str | None = None
    section_context: str | None = None


def pdf_evidence(path: Path, *, min_heading_size: float = 13, allow_lettered: bool = False, allow_unnumbered: bool = False) -> tuple[str, int, list[HeadingEvidence]]:
    """Extract candidate numbered display headings; reconciliation remains a human gate."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    headings = []
    seen: set[tuple[str, str, str | None, str | None]] = set()
    def display(span):
        return span["size"] >= 13 or span["size"] >= min_heading_size and "Bold" in span["font"]
    with pymupdf.open(path) as pdf:
        exercise_section = False
        instrument_context = None
        section_context = None
        for page_index, page in enumerate(pdf):
            blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
            for block_index, block in enumerate(blocks):
                if block["type"] != 0:
                    continue
                spans = [span for line in block["lines"] for span in line["spans"]]
                text = " ".join(span["text"].strip() for span in spans).strip()
                character_count = sum(len(s["text"].strip()) for s in spans)
                display_count = sum(len(s["text"].strip()) for s in spans if display(s))
                normalized = re.sub(r"\s+", " ", text).upper().strip()
                if block["bbox"][1] < 65 or block["bbox"][1] > page.rect.height - 45:
                    continue
                if normalized.startswith("UNIT ") and any(span["size"] >= 16 for span in spans):
                    exercise_section = False
                if any(normalized.startswith(prefix) for prefix in ("SECURITIES AND EXCHANGE BOARD OF INDIA", "THE SECURITIES AND EXCHANGE BOARD OF INDIA", "SEBI (")) and display_count / max(character_count, 1) >= 0.65 and any(s["size"] >= 15.5 for s in spans):
                    # One SEBI chapter has several separately numbered instruments,
                    # each followed by its own exercises. The next instrument is
                    # a substantive source boundary, not an answer heading.
                    instrument_context = normalized
                    previous_bottom = block["bbox"][3]
                    for following in blocks[block_index + 1:block_index + 3]:
                        following_spans = [s for line in following["lines"] for s in line["spans"]]
                        continuation = " ".join(s["text"].strip() for s in following_spans).strip()
                        if (not continuation or following["bbox"][1] - previous_bottom > 20 or
                            not all(s["size"] >= 15.5 for s in following_spans if s["text"].strip()) or
                            any(continuation.upper().startswith(prefix) for prefix in ("SEBI (", "SECURITIES AND", "THE SECURITIES AND", "INDEX", "TEST YOUR"))):
                            break
                        instrument_context += " " + continuation.upper()
                        previous_bottom = following["bbox"][3]
                    exercise_section = False
                if any(span["size"] >= 13 for span in spans) and (
                    "TEST YOUR KNOWLEDGE" in normalized or normalized in {"ANSWERS", "ANSWERS/SOLUTIONS", "PRACTICE QUESTIONS"}
                ):
                    exercise_section = True
                if exercise_section:
                    continue
                prefix = r"(?:\d+(?:\.\d+)*|[A-Z])" if allow_lettered else r"\d+(?:\.\d+)*"
                match = re.match(rf"^({prefix})(?:\.|\s)\s*([A-Za-z].+)$", text)
                if len(text) > 220 or not character_count or display_count / character_count < 0.65:
                    continue
                if match:
                    number, title = match.groups()
                elif (allow_unnumbered and page_index >= 3 and text.isupper() and len(text) <= 160 and
                      len(re.sub(r"[^A-Z]", "", text)) >= 5 and
                      all("Bold" in s["font"] for s in spans if s["text"].strip())):
                    number, title = f"unnumbered@{page_index + 1}/{block_index}", text
                else:
                    continue
                # ICAI PDFs often put a wrapped heading's final line in a second
                # text block. Join only adjacent display-font text, never body prose.
                previous_bottom = block["bbox"][3]
                original_heading_size = max(s["size"] for s in spans if s["text"].strip())
                for following in blocks[block_index + 1:block_index + 3]:
                    following_spans = [s for line in following["lines"] for s in line["spans"]]
                    continuation = " ".join(s["text"].strip() for s in following_spans).strip()
                    following_count = sum(len(s["text"].strip()) for s in following_spans)
                    following_display = sum(len(s["text"].strip()) for s in following_spans if display(s))
                    if (not continuation or following["bbox"][1] - previous_bottom > 20 or
                        abs(following["bbox"][0] - block["bbox"][0]) > 100 or
                        max(s["size"] for s in following_spans) < original_heading_size - 1 or
                        not following_count or following_display / following_count < 0.65 or
                        re.match(r"^(?:\d|[A-Z]\.)", continuation) or
                        any(term in continuation.upper() for term in ("LEARNING OUTCOMES", "ILLUSTRATION", "TEST YOUR", "ANSWER"))):
                        break
                    title += " " + continuation
                    previous_bottom = following["bbox"][3]
                title = re.sub(r"\s+", " ", title).strip()
                if any(term in title.upper() for term in (
                    "TEST YOUR", "ANSWER", "SUMMARY", "ILLUSTRATION", "EXERCISE", "QUESTION", "LEARNING OUTCOMES", "ANNEXURE",
                )):
                    continue
                if title.upper() in {"INDEX", "CHAPTER OVERVIEW", "PARTICULARS", "ITEMS"}:
                    continue
                if re.match(r"^(EXAMPLE\b|CASE STUDY\s*\d)", title.upper()):
                    continue
                if allow_lettered and number.isalpha():
                    section_context = title
                key = (number, title, instrument_context, section_context)
                if key not in seen:
                    headings.append(HeadingEvidence(number, title, page_index + 1, instrument_context, section_context))
                    seen.add(key)
        return digest, len(pdf), headings


def question_route(course_level: str, document_type: str, attempt: str | None) -> str:
    """Validate source family routing without confusing model papers with mock papers."""
    allowed = {
        "model_question", "model_answer", "mtp_question", "mtp_answer", "rtp",
        "question_paper", "suggested_answer", "case_scenarios", "ibs_case_study",
    }
    if course_level not in {"Foundation", "Intermediate", "Final"}:
        raise ValueError("Unknown course level")
    if document_type not in allowed:
        raise ValueError("Unknown document type")
    if attempt is None and document_type not in {"model_question", "model_answer", "case_scenarios", "ibs_case_study"}:
        raise ValueError("Dated source family requires its source attempt")
    return "final_queue" if course_level == "Final" else "outside_corpus"
