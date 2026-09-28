"""Background Classification Worker with polite rate limiting and automated retry backoff."""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "db"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "l3_classify"))

from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit, UnitAnswer
from caf_db.models.ops import LLMCall
from caf_db.models.ref import Node
from caf_l3.anchors import extract_anchors, lookup_anchor_candidates
from caf_l3.llm import LLMClassificationOutput

# Configure Logging to file and console
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "classify_worker.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("classify_worker")

# Target models in priority order
MODELS = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
RATE_LIMIT_DELAY_SECONDS = 15.0  # 4 requests/min, safely under 5 RPM limit
RETRY_BACKOFF_SECONDS = 20.0     # Backoff on 429 or 503 spikes


def build_focused_candidates(session: Session, paper_id: str, question_text: str) -> tuple[str, dict[str, Node]]:
    """Build candidate subtopics for this paper, prioritizing anchor matches if present."""
    all_nodes = (
        session.query(Node)
        .filter(Node.paper_id == paper_id)
        .order_by(Node.seq.asc())
        .all()
    )
    node_map = {n.id: n for n in all_nodes}

    paper_code = paper_id.split(".")[-1]
    anchors = extract_anchors(question_text, paper_code)
    anchor_candidates = lookup_anchor_candidates(session, anchors)

    # Chapters and Subtopics
    chapters = [n for n in all_nodes if n.level == "chapter"]
    lines = []

    # If anchor candidates match, put those chapters first
    if anchor_candidates:
        lines.append("=== PRIORITY CANDIDATE CHAPTERS (DETECTED STATUTORY ANCHORS) ===")
        for aid in anchor_candidates:
            anode = node_map.get(aid)
            if anode:
                lines.append(f"  • {anode.id}: {anode.name}")
        lines.append("\n=== ALL SYLLABUS CHAPTERS & SUBTOPICS ===")

    for ch in chapters:
        lines.append(f"\n[Chapter: {ch.name}] ({ch.id})")
        # Direct subtopics under this chapter
        subtopics = [n for n in all_nodes if n.level == "subtopic" and n.parent_id == ch.id]
        if not subtopics:
            # Check 3-level hierarchy (chapter -> topic -> subtopic)
            topics = [n for n in all_nodes if n.level == "topic" and n.parent_id == ch.id]
            for tp in topics:
                subtopics.extend([n for n in all_nodes if n.level == "subtopic" and n.parent_id == tp.id])

        for st in subtopics[:8]:  # Limit per chapter to keep prompt concise
            lines.append(f"  - {st.id}: {st.name}")

    return "\n".join(lines), node_map


def classify_single_unit(
    client: genai.Client,
    session: Session,
    unit: Unit,
    doc: Document,
    answer_text: str,
) -> LLMClassificationOutput:
    """Classify a single unit with retry and exponential backoff across model candidates."""
    paper_code = (doc.paper_id or "s2023.P1").split(".")[-1]
    candidate_text, node_map = build_focused_candidates(session, doc.paper_id or "s2023.P1", unit.question_text)

    prompt = (
        f"You are a Senior ICAI Examination Reviewer for CA Final Paper {paper_code}.\n"
        f"Classify this exam question into the single most accurate syllabus subtopic.\n\n"
        f"EXAM QUESTION:\n{unit.question_text.strip()[:2000]}\n\n"
    )
    if answer_text:
        prompt += f"MODEL SOLUTION:\n{answer_text.strip()[:2000]}\n\n"

    prompt += (
        f"CANDIDATE SUBTOPICS FOR PAPER {paper_code}:\n{candidate_text}\n\n"
        f"Return JSON strictly with keys:\n"
        f"primary_node_id, secondary_node_ids, confidence, bucket (A/B/C/D), core_tested_concept, justification, gist, alternatives"
    )

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.0,
    )

    last_err = None
    for model_name in MODELS:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                raw_text = (resp.text or "").strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]

                parsed = LLMClassificationOutput.model_validate_json(raw_text.strip())
                # Validate node exists
                if parsed.primary_node_id not in node_map:
                    for alt in parsed.alternatives:
                        if alt in node_map:
                            parsed.primary_node_id = alt
                            break
                    else:
                        parsed.primary_node_id = list(node_map.keys())[0]

                return parsed

            except APIError as e:
                last_err = e
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning("503 spike on %s (attempt %d/3). Backing off %ds...", model_name, attempt + 1, RETRY_BACKOFF_SECONDS)
                    time.sleep(RETRY_BACKOFF_SECONDS)
                    continue
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning("Rate limit on %s (attempt %d/3). Backing off 25s...", model_name, attempt + 1)
                    time.sleep(25.0)
                    continue
                elif "404" in err_str:
                    logger.info("Model %s not available on key, trying next model...", model_name)
                    break
                else:
                    logger.error("API error on %s: %s", model_name, err_str[:150])
                    time.sleep(5.0)
                    break
            except Exception as e:
                last_err = e
                logger.error("Parse or network error on %s: %s", model_name, e)
                time.sleep(3.0)
                break

    raise RuntimeError(f"Could not classify unit {unit.id} after all model attempts: {last_err}")


def run_worker(limit: int | None = None) -> None:
    """Continuously classify pending units with rate limit pacing and per-unit persistence."""
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set in .env. Exiting worker.")
        return

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    session_factory = get_session_factory()

    logger.info("=" * 60)
    logger.info("Classify Worker Started (Rate Limit Delay: %.1fs per request)", RATE_LIMIT_DELAY_SECONDS)
    logger.info("Logging to: %s", LOG_FILE.resolve())
    logger.info("=" * 60)

    processed = 0

    while True:
        with session_factory() as session:
            # Query next pending unit that has no suggestion
            already_suggested = set(session.scalars(select(TagSuggestion.unit_id).distinct()).all())
            decided_fps = set(session.scalars(select(Decision.unit_fingerprint)).all())

            query = (
                select(Unit, Document, UnitAnswer.answer_text)
                .join(Document, Unit.document_id == Document.id)
                .outerjoin(UnitAnswer, Unit.id == UnitAnswer.unit_id)
                .filter(
                    Unit.current.is_(True),
                    Unit.is_gradable.is_(True),
                    Unit.classify_status.in_(["pending", "failed"]),
                )
                .order_by(Unit.id.asc())
            )

            candidates = session.execute(query).all()
            pending_candidates = [
                (u, doc, ans)
                for u, doc, ans in candidates
                if u.id not in already_suggested and u.fingerprint not in decided_fps
            ]

            if not pending_candidates:
                logger.info("✓ All units have been classified! Worker finished.")
                break

            unit, doc, answer_text = pending_candidates[0]
            logger.info(
                "[%d] Classifying Unit ID=%d | Paper=%s | Label=%s",
                processed + 1,
                unit.id,
                doc.paper_id,
                unit.display_label,
            )

            try:
                res = classify_single_unit(client, session, unit, doc, answer_text or "")

                # Persist Primary Suggestion
                prim_sugg = TagSuggestion(
                    unit_id=unit.id,
                    run_id=None,
                    node_id=res.primary_node_id,
                    role="primary",
                    method="llm",
                    bucket=res.bucket,
                    evidence={
                        "core_concept": res.core_tested_concept,
                        "confidence": res.confidence,
                        "justification": res.justification,
                        "gist": res.gist,
                        "alternatives": res.alternatives,
                    },
                )
                session.add(prim_sugg)
                unit.classify_status = "suggested"
                session.commit()

                logger.info(
                    "  ✓ SAVED: Node=%s | Bucket=%s | Conf=%.2f | Concept=%s",
                    res.primary_node_id,
                    res.bucket,
                    res.confidence,
                    res.core_tested_concept[:50],
                )
                processed += 1

                if limit and processed >= limit:
                    logger.info("Target limit of %d units reached. Stopping worker.", limit)
                    break

                # Sleep to stay comfortably under 5 requests/minute
                logger.info("  Sleeping %.1fs to respect API rate limits...", RATE_LIMIT_DELAY_SECONDS)
                time.sleep(RATE_LIMIT_DELAY_SECONDS)

            except Exception as e:
                logger.error("Failed unit %d: %s. Sleeping 20s before next attempt...", unit.id, e)
                session.rollback()
                time.sleep(20.0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CA Final Classification Background Worker")
    parser.add_argument("--limit", type=int, default=None, help="Maximum units to process")
    args = parser.parse_args()

    run_worker(limit=args.limit)
