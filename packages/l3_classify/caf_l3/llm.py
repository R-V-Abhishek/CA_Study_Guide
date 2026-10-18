"""Google Gemini LLM Classification Engine with structured Pydantic outputs."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import time
import tomllib
from typing import Any
from typing import Literal

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from caf_common.settings import get_settings
from caf_db.models.ops import LLMCall
from caf_db.models.ref import Node

logger = logging.getLogger(__name__)


class LLMClassificationOutput(BaseModel):
    """Rigid JSON schema enforced for Gemini classification output."""

    primary_node_id: str | None = Field(
        description="Exact canonical node ID from candidate subtopics list, e.g. P1-BXTF71"
    )
    model_id: str | None = None
    outcome: Literal['matched', 'needs_review', 'none_fits'] = 'matched'
    label_evidence: dict[str, str] = Field(default_factory=dict)
    secondary_node_ids: list[str] = Field(
        default_factory=list,
        description="Secondary node IDs if the question tests multiple subtopics",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    bucket: str = Field(
        description="'A' for high (>=0.85), 'B' for medium (0.65-0.84), 'C' for low (<0.65), 'D' for multi-topic case study",
    )
    core_tested_concept: str = Field(
        description="The exact accounting standard, auditing standard, or tax section tested"
    )
    justification: str = Field(
        description="Step-by-step reasoning explaining why this node was chosen over alternative candidates"
    )
    gist: str = Field(
        description="Concise 1-sentence concept summary without monetary figures, dates, or party names"
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Alternative candidate node IDs that were considered",
    )


class QuotaExhaustedError(Exception):
    """Raised when Google Gemini daily quota or rate limit is reached."""
    pass


class BudgetExhaustedError(RuntimeError):
    """Estimated cumulative spend has reached the configured cutoff."""


class GeminiClassifier:
    """Manages LLM API calls with structured output and fallback cascades."""

    def __init__(self, session: Session, model_override: str | None = None,
                 taxonomy_version_id: int | None = None):
        self.session = session
        self.taxonomy_version_id = taxonomy_version_id
        settings = get_settings()
        self.api_key = settings.GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

        # Load models and pricing from config/models.toml
        self.models_config = self._load_models_config()
        if model_override:
            self.model_candidates = [model_override]
        else:
            primary = self.models_config.get("models", {}).get("primary", "gemini-2.5-flash")
            fallbacks = self.models_config.get("models", {}).get("fallbacks", ["gemini-2.0-flash", "gemini-1.5-flash"])
            self.model_candidates = [primary] + [f for f in fallbacks if f != primary]

        self.pricing = self.models_config.get("pricing", {})
        self.budget_cap = float(self.models_config.get("budget", {}).get("max_usd_per_run", 10.0))
        if not math.isfinite(self.budget_cap) or self.budget_cap <= 0:
            raise ValueError("max_usd_per_run must be finite and positive")
        self.total_cost_usd = 0.0

    def _load_models_config(self) -> dict[str, Any]:
        config_path = Path("config/models.toml")
        if config_path.exists():
            with open(config_path, "rb") as f:
                return tomllib.load(f)
        return {}

    def is_available(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.client and self.api_key)

    def build_candidate_prompt(self, paper_id: str) -> tuple[str, dict[str, Node]]:
        """Construct a scoped syllabus hierarchy string for the specific paper."""
        from caf_l0.hierarchy import ancestors, version_nodes
        from caf_l0.releases import eligible_candidates
        from caf_db.models.taxonomy import DescriptorRevision
        from sqlalchemy import select

        if self.taxonomy_version_id is None:
            raise ValueError("LLM classification requires a rebuilt taxonomy version")
        nodes = version_nodes(self.session, self.taxonomy_version_id)
        candidates = eligible_candidates(self.session, self.taxonomy_version_id,
                                         None if paper_id == "s2023.P6" else paper_id)
        by_id = {n.id: n for n in nodes}
        node_map = {member.node_id: by_id[member.node_id] for member in candidates}
        revisions = {}
        for revision in self.session.scalars(select(DescriptorRevision).where(
            DescriptorRevision.taxonomy_version_id == self.taxonomy_version_id,
            DescriptorRevision.node_id.in_(node_map),
        ).order_by(DescriptorRevision.revision)):
            revisions[revision.node_id] = revision
        lines = []
        for node in node_map.values():
            path = " → ".join(n.name for n in ancestors(node.id, by_id))
            descriptor = revisions[node.id].content
            lines.append(f"Paper {node.paper_id} | {path} | Subtopic ID: {node.id}\n"
                         f"Descriptor revision: {revisions[node.id].id}\n"
                         f"{json.dumps(descriptor, ensure_ascii=False)}")
        if not node_map:
            raise ValueError("needs taxonomy review: no eligible candidates")
        return "\n".join(lines), node_map

    def classify_unit(
        self,
        paper_id: str,
        question_text: str,
        answer_text: str = "",
        run_id: int | None = None,
        retries: int = 2,
    ) -> LLMClassificationOutput:
        """Execute structured LLM classification using the Gemini API."""
        from caf_l3.textbook import NeedsTaxonomyReview
        if not self.is_available():
            raise ValueError("GEMINI_API_KEY is not set or client unavailable.")

        paper_code = paper_id.split(".")[-1]
        candidate_tree, node_map = self.build_candidate_prompt(paper_id)

        system_instruction = (
            f"You are a Senior Examination Reviewer and Valuation Moderator for the Institute of Chartered "
            f"Accountants of India (ICAI) CA Final New Scheme.\n"
            f"Your task is to classify an ICAI exam question into the canonical syllabus hierarchy for Paper {paper_code}.\n\n"
            f"EXAMINATION MODERATION RULES:\n"
            f"1. FOCUS ON THE CORE TESTED OBJECTIVE:\n"
            f"   - Identify what the candidate is required to calculate, disclose, or advise.\n"
            f"   - Ignore background facts that do not drive marks. If a company leases machinery and later calculates "
            f"impairment under Ind AS 36, classify under Ind AS 36 (Impairment) unless lease measurement is evaluated.\n"
            f"2. STRICT PAPER BOUNDARY:\n"
            f"   - Select only provided Candidate Subtopics. IBS may use explicitly listed cross-paper concepts.\n"
            f"   - Return outcome matched, needs_review or none_fits explicitly. Unresolved outcomes require null primary_node_id and no secondary labels.\n"
            f"   - Provide label_evidence mapping each selected label ID to brief support in the tested task and descriptor.\n"
            f"3. USE OFFICIAL SOLUTION EVIDENCE:\n"
            f"   - Official solutions often state the governing Standard or Section in the opening paragraph.\n"
            f"4. CONFIDENCE BUCKETS:\n"
            f"   - Bucket A (>= 0.85): Clear, unambiguous match with standard syllabus subtopic.\n"
            f"   - Bucket B (0.65 - 0.84): Probable match with minor overlap across chapters.\n"
            f"   - Bucket C (< 0.65): Unclear or highly general question.\n"
            f"   - Bucket D: Multi-topic integrated case scenario testing 3+ distinct chapters.\n"
            f"5. CONCISE GIST:\n"
            f"   - 1-sentence concept summary without figures, dates, or party names.\n"
        )

        user_content = (
            f"--- OFFICIAL ICAI EXAM QUESTION ---\n"
            f"{question_text.strip()}\n\n"
        )
        if answer_text and answer_text.strip():
            user_content += (
                f"--- OFFICIAL MODEL SOLUTION ---\n"
                f"{answer_text.strip()}\n\n"
            )

        user_content += (
            f"--- CANONICAL SYLLABUS CANDIDATES (PAPER {paper_code}) ---\n"
            f"{candidate_tree}\n\n"
            f"Classify this question now and return strictly according to the JSON schema."
        )

        last_error = None
        for model_name in self.model_candidates:
            for attempt in range(retries + 1):
                # Usage is known after each response. This stops subsequent calls;
                # a single response can exceed the remaining estimated budget.
                if self.total_cost_usd >= self.budget_cap:
                    raise BudgetExhaustedError("Classification estimated spend reached max_usd_per_run")
                start_time = time.time()
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.0,
                    )

                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=user_content,
                        config=config,
                    )
                    latency_ms = int((time.time() - start_time) * 1000)

                    # Extract usage metadata
                    input_tokens = 0
                    output_tokens = 0
                    if response.usage_metadata:
                        input_tokens = response.usage_metadata.prompt_token_count or 0
                        output_tokens = response.usage_metadata.candidates_token_count or 0

                    cost_usd = self._compute_cost(model_name, input_tokens, output_tokens)
                    self.total_cost_usd += cost_usd

                    # Log to ops.llm_call
                    if run_id:
                        call_log = LLMCall(
                            run_id=run_id,
                            task="l3_classify",
                            model_id=model_name,
                            prompt_version="textbook-v1",
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost_usd=cost_usd,
                            latency_ms=latency_ms,
                            status="ok",
                        )
                        self.session.add(call_log)

                    raw_text = (response.text or "").strip()
                    if raw_text.startswith("```json"):
                        raw_text = raw_text[7:]
                    if raw_text.startswith("```"):
                        raw_text = raw_text[3:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]

                    result = LLMClassificationOutput.model_validate_json(raw_text.strip())
                    result.model_id = model_name
                    selected = ([result.primary_node_id] if result.primary_node_id else []) + result.secondary_node_ids
                    if result.outcome != 'matched' and selected:
                        raise NeedsTaxonomyReview("Unresolved outcome contains labels")
                    if result.outcome == 'matched' and not result.primary_node_id:
                        raise NeedsTaxonomyReview("needs taxonomy review: model returned unsupported candidate IDs")
                    # Validate that primary_node_id exists in the paper candidates
                    if any(node_id not in node_map for node_id in
                           [*selected, *result.alternatives]):
                        raise NeedsTaxonomyReview("needs taxonomy review: model returned unsupported candidate IDs")
                    if len(selected) != len(set(selected)):
                        raise NeedsTaxonomyReview("Duplicate model labels")
                    # Single-label historical provider fixtures carry their support
                    # in justification; multi-label outputs need individual evidence.
                    if selected and not result.label_evidence and len(selected) == 1:
                        result.label_evidence = {selected[0]: result.justification}
                    if set(result.label_evidence) != set(selected) or any(not text.strip() for text in result.label_evidence.values()):
                        raise NeedsTaxonomyReview("Each model label requires supporting evidence")

                    return result

                except APIError as api_err:
                    last_error = api_err
                    # 429 quota exhaustion or rate limit
                    if "429" in str(api_err) or "RESOURCE_EXHAUSTED" in str(api_err).upper():
                        logger.warning("Gemini API quota/rate limit encountered on %s", model_name)
                        if attempt < retries:
                            time.sleep(2 ** (attempt + 1))
                            continue
                        raise QuotaExhaustedError(f"Gemini API quota exhausted on {model_name}: {api_err}")
                    elif "404" in str(api_err) or "NOT_FOUND" in str(api_err).upper():
                        logger.warning("Model %s not found / deprecated. Trying fallback model...", model_name)
                        break  # try next model candidate in outer loop
                    else:
                        logger.error("API error calling %s: %s", model_name, api_err)
                        if attempt < retries:
                            time.sleep(2)
                            continue
                        break

                except NeedsTaxonomyReview:
                    raise
                except Exception as exc:
                    last_error = exc
                    logger.error("Unexpected error in classification call: %s", exc)
                    if attempt < retries:
                        time.sleep(1)
                        continue
                    break

        raise RuntimeError(f"All model candidates failed. Last error: {last_error}")

    def _compute_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        prices = self.pricing.get(model_name, {"input": 0.50, "output": 3.00})
        in_cost = (input_tokens / 1_000_000.0) * prices.get("input", 0.50)
        out_cost = (output_tokens / 1_000_000.0) * prices.get("output", 3.00)
        return round(in_cost + out_cost, 6)
