"""Deterministic metadata inference from URL, breadcrumbs, anchor text, and filenames."""

import re
from pathlib import Path
from typing import Any
from rapidfuzz import fuzz

MONTH_MAP = {
    "jan": "01",
    "january": "01",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

ATTEMPT_REGEX = re.compile(
    r"\b(jan(?:uary)?|may|june?|july?|sep(?:t(?:ember)?)?|nov(?:ember)?|dec(?:ember)?)[_\W\s]{0,3}(20\d\d)\b",
    re.IGNORECASE,
)
PAPER_REGEX = re.compile(r"\bpaper[_\W\s]{0,3}([1-6])\b", re.IGNORECASE)
SERIES_REGEX = re.compile(r"\bseries[_\W\s]{0,3}(I{1,3}|\d)\b", re.IGNORECASE)

PAPER_NAMES = {
    "P1": "Financial Reporting",
    "P2": "Advanced Financial Management",
    "P3": "Advanced Auditing, Assurance and Professional Ethics",
    "P4": "Direct Tax Laws & International Taxation",
    "P5": "Indirect Tax Laws",
    "P6": "Integrated Business Solutions",
}


def infer_metadata(
    url: str,
    anchor_text: str | None = None,
    breadcrumb: list[str] | None = None,
    scheme_hint: str = "s2023",
) -> dict[str, Any]:
    """Infer attempt_id, paper_id, doc_type_id, series, and catalog_status."""
    filename = Path(url.split("?")[0]).name
    crumbs = breadcrumb or []
    tokens = [c for c in crumbs if c] + ([anchor_text] if anchor_text else []) + [filename]
    # Replace underscores with spaces so regex word boundaries \b work seamlessly
    combined_text = " | ".join(tokens).replace("_", " ")

    # 1. Attempt inference
    attempt_id = None
    attempt_matches = ATTEMPT_REGEX.findall(combined_text)
    if attempt_matches:
        month_str, year_str = attempt_matches[-1]  # Prefer the most specific (anchor/filename)
        m_code = MONTH_MAP.get(month_str.lower()[:3]) or MONTH_MAP.get(month_str.lower())
        if m_code:
            attempt_id = f"{year_str}-{m_code}"

    # 2. Paper inference
    paper_code = None
    paper_match = PAPER_REGEX.search(combined_text)
    if paper_match:
        paper_code = f"P{paper_match.group(1)}"
    else:
        # Fuzzy match against paper names
        best_code = None
        best_score = 0.0
        for code, name in PAPER_NAMES.items():
            score = fuzz.partial_ratio(name.lower(), combined_text.lower())
            if score > best_score and score >= 80.0:
                best_score = score
                best_code = code
        if best_code:
            paper_code = best_code

    paper_id = f"{scheme_hint}.{paper_code}" if paper_code else None

    # 3. Doc type inference
    doc_type_id = None
    lower_text = combined_text.lower()
    if "suggested answer" in lower_text or "suggested_answer" in lower_text:
        doc_type_id = "suggested_answer"
    elif "question paper" in lower_text or "question_paper" in lower_text:
        doc_type_id = "question_paper"
    elif "revision test paper" in lower_text or re.search(r"\brtp\b", lower_text):
        doc_type_id = "rtp"
    elif "mock test paper" in lower_text or re.search(r"\bmtp\b", lower_text):
        if "answer" in lower_text or "solution" in lower_text:
            doc_type_id = "mtp_answer"
        else:
            doc_type_id = "mtp_question"
    elif "case scenario" in lower_text or "case study" in lower_text or "case_scenario" in lower_text:
        doc_type_id = "case_scenarios"
    elif "study material" in lower_text or "module" in lower_text:
        doc_type_id = "study_material"
    elif "guideline" in lower_text:
        doc_type_id = "study_guidelines"
    elif "weightage" in lower_text:
        doc_type_id = "weightage"
    elif "syllabus" in lower_text:
        doc_type_id = "syllabus"
    elif "saransh" in lower_text:
        doc_type_id = "saransh"

    # 4. Series inference
    series = None
    series_match = SERIES_REGEX.search(combined_text)
    if series_match:
        s_val = series_match.group(1).upper()
        if s_val in ["I", "1"]:
            series = "1"
        elif s_val in ["II", "2"]:
            series = "2"
        elif s_val in ["III", "3"]:
            series = "3"

    # 5. Catalog status resolution
    # All fields resolved uniquely -> 'inferred', otherwise 'needs_curation'
    is_complete = bool(attempt_id and paper_id and doc_type_id)
    catalog_status = "inferred" if is_complete else "needs_curation"

    return {
        "scheme_id": scheme_hint,
        "attempt_id": attempt_id,
        "paper_id": paper_id,
        "paper_code": paper_code,
        "doc_type_id": doc_type_id,
        "series": series,
        "catalog_status": catalog_status,
        "title": anchor_text or filename,
    }
