"""Resolve personal study scope without substituting another attempt or release."""
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.app import Settings
from caf_db.models.intel import AttemptTaxonomyBinding, ScoreRun, RecomputeJob
from caf_db.models.questions import CorpusGeneration
from caf_db.models.ref import ApplicabilityRule, Node
from caf_db.models.taxonomy import NodeSourceSpan, TaxonomyRelease, TextbookArtifact
from caf_l5.config import ScoringConfig, load_scoring_config


@dataclass
class StudyContext:
    target_attempt_id: str | None
    taxonomy_version_id: int | None
    run: ScoreRun | None
    readiness: str
    config: ScoringConfig
    freshness: dict[str, Any]
    unresolved_node_ids: list[str] = field(default_factory=list)

    @property
    def identity(self) -> dict[str, Any]:
        return {"target_attempt_id": self.target_attempt_id,
                "taxonomy_version_id": self.taxonomy_version_id, "readiness": self.readiness,
                "applicability_state": "unresolved" if self.unresolved_node_ids else "reviewed",
                "unresolved_node_ids": self.unresolved_node_ids}


def corpus_generation(session: Session) -> int:
    row = session.get(CorpusGeneration, 1)
    return row.generation if row else 0


def approved_binding(session: Session, target_attempt_id: str,
                     taxonomy_version_id: int | None = None) -> AttemptTaxonomyBinding | None:
    query = sa.select(AttemptTaxonomyBinding).where(
        AttemptTaxonomyBinding.target_attempt_id == target_attempt_id,
        AttemptTaxonomyBinding.status == "reviewed",
        AttemptTaxonomyBinding.reviewed_by.is_not(None),
        AttemptTaxonomyBinding.taxonomy_version_id.in_(sa.select(TaxonomyRelease.taxonomy_version_id).where(
            TaxonomyRelease.status.in_(["approved", "active", "archived"]),
            TaxonomyRelease.approved_by.is_not(None))))
    if taxonomy_version_id is not None:
        query = query.where(AttemptTaxonomyBinding.taxonomy_version_id == taxonomy_version_id)
    bindings = list(session.scalars(query))
    # Multiple approved releases require an explicit release, rather than silently
    # selecting whichever happens to be globally active.
    return bindings[0] if len(bindings) == 1 else None


def snapshot_freshness(session: Session, target: str | None, taxonomy: int | None,
                       run: ScoreRun | None, config_hash: str) -> dict[str, Any]:
    latest = corpus_generation(session)
    job = session.scalar(sa.select(RecomputeJob).where(
        RecomputeJob.target_attempt_id == target,
        RecomputeJob.taxonomy_version_id == taxonomy,
        RecomputeJob.config_hash == config_hash,
    ).order_by(RecomputeJob.corpus_generation.desc(), RecomputeJob.id.desc()).limit(1))
    status = "unavailable"
    if run:
        status = "ready" if run.corpus_generation == latest and not run.stale else "stale"
    if job and job.status in {"pending", "running", "failed"}:
        status = job.status
    return {"publication_generation": latest,
            "scored_generation": run.corpus_generation if run else None,
            "computed_at": run.finished_at.isoformat() if run and run.finished_at else None,
            "status": status, "job_id": job.id if job else None,
            "error": job.last_error if job and job.status == "failed" else None}


def _unresolved_applicability(session: Session, taxonomy: int) -> list[str]:
    # Only these flags determine applicability. Loading full artifact metadata
    # for every source span repeats large heading inventories thousands of times.
    rows = session.execute(sa.select(
        NodeSourceSpan.node_id,
        TextbookArtifact.metadata_json["fallback"],
        TextbookArtifact.metadata_json["target_applicability"],
    ).join(TextbookArtifact).where(NodeSourceSpan.taxonomy_version_id == taxonomy))
    return list(dict.fromkeys(node_id for node_id, fallback, applicability in rows
                              if fallback and applicability not in {"verified", "applicable"}))


def resolve_context(session: Session, user_id: int) -> StudyContext:
    if session.info.get("cache_study_context"):
        cache = session.info.setdefault("study_contexts", {})
        cached = cache.get(user_id)
        if cached is not None and cached[0] is session.get_transaction():
            return cached[1]
    context = _resolve_context(session, user_id)
    if session.info.get("cache_study_context"):
        cache[user_id] = (session.get_transaction(), context)
    return context


def _resolve_context(session: Session, user_id: int) -> StudyContext:
    settings = session.get(Settings, user_id)
    config = load_scoring_config()
    if settings is None:
        freshness = snapshot_freshness(session, None, None, None, config.config_hash)
        return StudyContext(None, None, None, "profile_settings_unavailable", config, freshness)
    target = settings.target_attempt_id
    taxonomy = None
    readiness = "ready"
    binding = approved_binding(session, target) if target else None
    rebuilt = session.scalar(sa.select(TaxonomyRelease.taxonomy_version_id).where(
        TaxonomyRelease.status != "legacy").limit(1))
    if not target:
        readiness = "target_attempt_unavailable"
    elif binding:
        taxonomy = binding.taxonomy_version_id
        if binding.scoring_config:
            config = ScoringConfig.model_validate(binding.scoring_config)
    elif rebuilt is not None:
        readiness = "taxonomy_binding_unavailable"
    run = None
    if readiness == "ready":
        run = session.scalar(sa.select(ScoreRun).where(
            ScoreRun.target_attempt_id == target, ScoreRun.taxonomy_version_id == taxonomy,
            ScoreRun.config_hash == config.config_hash, ScoreRun.status == "ok",
            ScoreRun.shadow.is_(False), ScoreRun.is_current.is_(True),
        ).order_by(ScoreRun.corpus_generation.desc(), ScoreRun.id.desc()).limit(1))
    unresolved = []
    if taxonomy is not None:
        unresolved = _unresolved_applicability(session, taxonomy)
    return StudyContext(target, taxonomy, run, readiness, config,
                        snapshot_freshness(session, target, taxonomy, run, config.config_hash), unresolved)


def context_nodes(session: Session, context: StudyContext, *, study: bool = False) -> list[Node]:
    if session.info.get("cache_study_context"):
        cache = session.info.setdefault("study_node_scopes", {})
        key = (context.target_attempt_id, context.taxonomy_version_id, context.readiness, study)
        cached = cache.get(key)
        if cached is not None and cached[0] is session.get_transaction():
            return cached[1]
    nodes = _context_nodes(session, context, study=study)
    if session.info.get("cache_study_context"):
        cache[key] = (session.get_transaction(), nodes)
    return nodes


def _context_nodes(session: Session, context: StudyContext, *, study: bool = False) -> list[Node]:
    if context.readiness != "ready":
        return []
    from caf_l0.hierarchy import version_nodes
    nodes = version_nodes(session, context.taxonomy_version_id)
    nodes_by_id = {node.id: node for node in nodes}
    excluded = set(session.scalars(sa.select(ApplicabilityRule.node_id).where(
        ApplicabilityRule.attempt_id == context.target_attempt_id,
        ApplicabilityRule.effect == "exclude")))
    if context.taxonomy_version_id is not None and not study:
        excluded.update(_unresolved_applicability(session, context.taxonomy_version_id))
    result = []
    for node in nodes:
        current = node
        applicable = node.status == "active"
        while current:
            if current.id in excluded:
                applicable = False
                break
            current = nodes_by_id.get(current.parent_id)
        if applicable:
            result.append(node)
    return result


def context_leaf_ids(session: Session, context: StudyContext, *, study: bool = False) -> set[str]:
    """Terminal structure is fixed before attempt applicability removes children."""
    if session.info.get("cache_study_context"):
        cache = session.info.setdefault("study_leaf_scopes", {})
        key = (context.target_attempt_id, context.taxonomy_version_id, context.readiness, study)
        cached = cache.get(key)
        if cached is not None and cached[0] is session.get_transaction():
            return cached[1]
    leaf_ids = _context_leaf_ids(session, context, study=study)
    if session.info.get("cache_study_context"):
        cache[key] = (session.get_transaction(), leaf_ids)
    return leaf_ids


def _context_leaf_ids(session: Session, context: StudyContext, *, study: bool = False) -> set[str]:
    if context.readiness != "ready":
        return set()
    from caf_l0.hierarchy import version_nodes
    full_nodes = version_nodes(session, context.taxonomy_version_id)
    structural_parents = {node.parent_id for node in full_nodes}
    return {node.id for node in context_nodes(session, context, study=study) if
            node.level == "subtopic" and node.id not in structural_parents}
