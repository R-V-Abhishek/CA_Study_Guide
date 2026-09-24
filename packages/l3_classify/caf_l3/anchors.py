"""Deterministic anchor extraction and lookup from text."""

from dataclasses import dataclass
import re
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from caf_db.models.ref import Anchor

IND_AS_REGEX = re.compile(r"\bInd\s*AS\s*(\d{1,3})\b", re.IGNORECASE)
AS_REGEX = re.compile(r"(?<!Ind\s)\bAS\s*(\d{1,2})\b", re.IGNORECASE)
SA_REGEX = re.compile(r"\bSA\s*(\d{3})\b", re.IGNORECASE)
SQC_SQM_REGEX = re.compile(r"\b(SQC|SQM)\s*(\d)\b", re.IGNORECASE)
SEC_REGEX = re.compile(
    r"\b(?:[Ss]ection|[Ss]ec\.|u/s)\s*(\d{1,3}[A-Z]{0,4})",
    re.IGNORECASE,
)


@dataclass
class AnchorMatch:
    instrument_id: str
    ref_key: str
    raw_match: str
    confidence: float = 1.0


def extract_anchors(
    text: str, paper_code: str, attempt_id: str | None = None
) -> list[AnchorMatch]:
    """Extract deterministic instrument and section anchors from question/answer text."""
    matches: list[AnchorMatch] = []
    paper_clean = paper_code.split(".")[-1].upper()

    # 1. Ind AS (P1, P6)
    if paper_clean in ("P1", "P6"):
        for m in IND_AS_REGEX.finditer(text):
            matches.append(
                AnchorMatch(
                    instrument_id="IndAS",
                    ref_key=m.group(1),
                    raw_match=m.group(0),
                )
            )

    # 2. Auditing Standards (P3, P6)
    if paper_clean in ("P3", "P6"):
        for m in SA_REGEX.finditer(text):
            matches.append(
                AnchorMatch(
                    instrument_id="SA",
                    ref_key=m.group(1),
                    raw_match=m.group(0),
                )
            )
        for m in SQC_SQM_REGEX.finditer(text):
            inst = m.group(1).upper()
            num = m.group(2)
            matches.append(
                AnchorMatch(
                    instrument_id=inst,
                    ref_key=num,
                    raw_match=m.group(0),
                )
            )

    # 3. Direct Tax (P4, P6)
    if paper_clean in ("P4", "P6"):
        for m in SEC_REGEX.finditer(text):
            sec_num = m.group(1).upper()
            matches.append(
                AnchorMatch(
                    instrument_id="ITA1961",
                    ref_key=sec_num,
                    raw_match=m.group(0),
                )
            )

    # 4. Indirect Tax (P5, P6)
    if paper_clean in ("P5", "P6"):
        for m in SEC_REGEX.finditer(text):
            sec_num = m.group(1).upper()
            start_pos = max(0, m.start() - 60)
            end_pos = min(len(text), m.end() + 60)
            window = text[start_pos:end_pos].lower()

            if "igst" in window:
                inst = "IGST"
            elif "customs" in window:
                inst = "CUSTOMS"
            else:
                inst = "CGST"

            matches.append(
                AnchorMatch(
                    instrument_id=inst,
                    ref_key=sec_num,
                    raw_match=m.group(0),
                )
            )

    return matches


def lookup_anchor_candidates(
    session: Session, matches: list[AnchorMatch]
) -> dict[str, float]:
    """Look up ref.anchor table and aggregate node weights."""
    if not matches:
        return {}

    candidate_weights: dict[str, float] = {}
    for m in matches:
        rows = (
            session.query(Anchor)
            .filter(
                Anchor.instrument_id == m.instrument_id,
                Anchor.ref_key == m.ref_key,
            )
            .all()
        )
        for r in rows:
            candidate_weights[r.node_id] = candidate_weights.get(r.node_id, 0.0) + r.weight

    return candidate_weights
