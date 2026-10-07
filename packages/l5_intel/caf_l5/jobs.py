"""PostgreSQL-backed, leased recomputation with coalesced pending work."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from caf_db.models.intel import RecomputeJob
from caf_l5.config import ScoringConfig, load_scoring_config
from caf_l5.context import approved_binding, corpus_generation, snapshot_freshness


def enqueue_recompute(session: Session, target_attempt_id: str,
                      taxonomy_version_id: int | None = None,
                      config: ScoringConfig | None = None, *, commit: bool = True) -> RecomputeJob:
    from caf_db.models.ref import Attempt
    if session.get(Attempt, target_attempt_id) is None:
        raise ValueError(f"Unknown target attempt: {target_attempt_id}")
    binding = approved_binding(session, target_attempt_id, taxonomy_version_id)
    if binding:
        taxonomy_version_id = binding.taxonomy_version_id
        config = config or (ScoringConfig.model_validate(binding.scoring_config)
                           if binding.scoring_config else load_scoring_config())
    elif taxonomy_version_id is not None:
        raise ValueError("An approved target-attempt taxonomy binding is required")
    if binding is None:
        from caf_db.models.taxonomy import TaxonomyRelease
        if session.scalar(sa.select(TaxonomyRelease.taxonomy_version_id).where(
            TaxonomyRelease.status != "legacy").limit(1)) is not None:
            raise ValueError("An approved target-attempt taxonomy binding is required")
    config = config or load_scoring_config()
    generation = corpus_generation(session)
    statement = insert(RecomputeJob).values(target_attempt_id=target_attempt_id,
        taxonomy_version_id=taxonomy_version_id, config_hash=config.config_hash,
        config_snapshot=config.model_dump(mode="json"), corpus_generation=generation,
        status="pending", attempts=0).on_conflict_do_update(
            index_elements=[RecomputeJob.target_attempt_id, RecomputeJob.taxonomy_version_id,
                            RecomputeJob.config_hash], index_where=sa.text("status='pending'"),
            set_={"corpus_generation": sa.func.greatest(RecomputeJob.corpus_generation, generation),
                  "config_snapshot": config.model_dump(mode="json"), "last_error": None}).returning(RecomputeJob.id)
    job_id = session.scalar(statement)
    if commit:
        session.commit()
    return session.get(RecomputeJob, job_id)


def claim_job(session: Session, *, lease_seconds: int = 300) -> RecomputeJob | None:
    if lease_seconds <= 0:
        raise ValueError("Lease duration must be positive")
    now = datetime.now(timezone.utc)
    job = session.scalar(sa.select(RecomputeJob).where(sa.or_(
        RecomputeJob.status == "pending", sa.and_(RecomputeJob.status == "running",
        RecomputeJob.lease_until < now))).order_by(RecomputeJob.created_at, RecomputeJob.id).
        with_for_update(skip_locked=True).limit(1))
    if job is None:
        session.rollback()
        return None
    job.status = "running"
    job.lease_token = uuid4().hex
    job.lease_until = now + timedelta(seconds=lease_seconds)
    job.attempts += 1
    job.last_error = None
    session.commit()
    return job


def complete_job(session: Session, job_id: int, token: str, run_id: int | None,
                 error: str | None = None) -> bool:
    job = session.scalar(sa.select(RecomputeJob).where(RecomputeJob.id == job_id).with_for_update())
    if job is None or job.status != "running" or job.lease_token != token or (
            job.lease_until is None or job.lease_until <= datetime.now(timezone.utc)):
        session.rollback()
        return False
    if run_id is not None and not error:
        from caf_db.models.intel import ScoreRun
        from caf_l5.scoring import promote_score_run
        run = session.get(ScoreRun, run_id)
        if run is None or (run.target_attempt_id, run.taxonomy_version_id, run.config_hash) != (
                job.target_attempt_id, job.taxonomy_version_id, job.config_hash):
            raise ValueError("Worker output context differs from claimed job")
        promote_score_run(session, run)
    job.status = "failed" if error else "ok"
    job.last_error = error
    job.score_run_id = run_id
    job.lease_until = None
    job.lease_token = None
    latest = corpus_generation(session)
    if not error and latest > job.corpus_generation:
        enqueue_recompute(session, job.target_attempt_id, job.taxonomy_version_id,
                          ScoringConfig.model_validate(job.config_snapshot), commit=False)
    session.commit()
    return True


def run_worker_once(session_factory, *, lease_seconds: int = 300) -> int | None:
    from caf_l5.scoring import recompute_scores
    with session_factory() as session:
        enqueue_missing_contexts(session)
        job = claim_job(session, lease_seconds=lease_seconds)
        if not job:
            return None
        job_id, token = job.id, job.lease_token
        target, taxonomy = job.target_attempt_id, job.taxonomy_version_id
        config = ScoringConfig.model_validate(job.config_snapshot)
    try:
        with session_factory() as session:
            session.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            run = recompute_scores(session, target, taxonomy_version_id=taxonomy, config=config, promote=False)
            run_id = run.id
        with session_factory() as session:
            accepted = complete_job(session, job_id, token, run_id)
            if not accepted:
                return None
    except Exception as exc:
        with session_factory() as session:
            complete_job(session, job_id, token, None, f"{type(exc).__name__}: {exc}")
        raise
    return job_id


def job_status(session: Session, target_attempt_id: str, taxonomy_version_id: int | None = None,
               config: ScoringConfig | None = None) -> dict[str, Any]:
    from caf_l5.service import get_current_score_run
    binding = approved_binding(session, target_attempt_id, taxonomy_version_id)
    if binding:
        taxonomy_version_id = binding.taxonomy_version_id
        config = config or (ScoringConfig.model_validate(binding.scoring_config)
                           if binding.scoring_config else load_scoring_config())
    config = config or load_scoring_config()
    run = get_current_score_run(session, target_attempt_id, taxonomy_version_id, config.config_hash)
    return snapshot_freshness(session, target_attempt_id, taxonomy_version_id, run, config.config_hash)


def enqueue_missing_contexts(session: Session) -> int:
    """Discover newly approved bindings whose configuration has no queued input.

    SQL invalidation can reuse known snapshots' configurations. The worker
    supplies the configured initial snapshot for a newly bound context.
    """
    from caf_db.models.intel import AttemptTaxonomyBinding, ScoreRun
    from caf_db.models.taxonomy import TaxonomyRelease
    bindings = list(session.scalars(sa.select(AttemptTaxonomyBinding).where(
        AttemptTaxonomyBinding.status == "reviewed", AttemptTaxonomyBinding.reviewed_by.is_not(None),
        AttemptTaxonomyBinding.taxonomy_version_id.in_(sa.select(TaxonomyRelease.taxonomy_version_id).where(
            TaxonomyRelease.status.in_(["approved", "active", "archived"]),
            TaxonomyRelease.approved_by.is_not(None))))))
    generation = corpus_generation(session)
    count = 0
    for binding in bindings:
        config = ScoringConfig.model_validate(binding.scoring_config) if binding.scoring_config else load_scoring_config()
        latest_job = session.scalar(sa.select(RecomputeJob.id).where(
            RecomputeJob.target_attempt_id == binding.target_attempt_id,
            RecomputeJob.taxonomy_version_id == binding.taxonomy_version_id,
            RecomputeJob.config_hash == config.config_hash,
            RecomputeJob.corpus_generation >= generation).limit(1))
        latest_run = session.scalar(sa.select(ScoreRun.id).where(
            ScoreRun.target_attempt_id == binding.target_attempt_id,
            ScoreRun.taxonomy_version_id == binding.taxonomy_version_id,
            ScoreRun.config_hash == config.config_hash, ScoreRun.status == "ok",
            ScoreRun.shadow.is_(False), ScoreRun.is_current.is_(True),
            ScoreRun.corpus_generation >= generation).limit(1))
        if latest_job is None and latest_run is None:
            enqueue_recompute(session, binding.target_attempt_id, binding.taxonomy_version_id,
                              config, commit=False)
            count += 1
    session.commit()
    return count
