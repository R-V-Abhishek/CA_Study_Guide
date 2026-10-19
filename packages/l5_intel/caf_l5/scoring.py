"""Core scoring engine for L5 Intelligence.

Implements exponential decay, recency weighting, weightage priors,
importance score calculation, ingestion coverage, and atomic score run swapping.
"""

from datetime import datetime, timezone
import logging
from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.settings import get_settings
from caf_db.models.core import Appearance, AppearanceTag
from caf_db.models.intel import DepthGateReport, IngestionCoverage, ScoreRun, SubtopicScore
from caf_db.models.ref import (
    ApplicabilityRule,
    Attempt,
    Node,
    Paper,
    WeightageMember,
    WeightageSection,
)
from caf_l5.config import ScoringConfig, load_scoring_config

logger = logging.getLogger(__name__)


def compute_age_months(
    attempt_year: int,
    attempt_month: int,
    target_year: int,
    target_month: int,
) -> int:
    """Calculate whole months between appearance attempt and target attempt."""
    return (target_year - attempt_year) * 12 + (target_month - attempt_month)


def compute_decay(age_months: int, half_life_months: float) -> float:
    """Calculate exponential decay factor 2^(-age / half_life)."""
    if half_life_months <= 0:
        return 1.0
    return 2.0 ** (-float(age_months) / float(half_life_months))


def calculate_attributed_marks(
    marks: int | None,
    share: float,
    source_paper_id: str,
    target_node_paper_id: str,
    law_stale: bool,
    config: ScoringConfig,
) -> tuple[float, float, float]:
    """Calculate attributed marks m(a,s) = marks(a) * share(a,s) * kappa * lambda.
    
    Returns (m, kappa, lambda_val).
    """
    raw_marks = float(marks) if marks is not None else 0.0
    
    # κ: p6_cross_paper_factor if source paper is P6 and target subtopic is in P1–P5
    is_p6_source = source_paper_id.endswith(".P6") or source_paper_id == "P6"
    is_p1_p5_target = not (target_node_paper_id.endswith(".P6") or target_node_paper_id == "P6")
    kappa = config.p6_cross_paper_factor if (is_p6_source and is_p1_p5_target) else 1.0
    
    # λ: law_stale_factor if a.law_stale else 1.0
    lambda_val = config.law_stale_factor if law_stale else 1.0
    
    m = raw_marks * share * kappa * lambda_val
    return m, kappa, lambda_val


def recompute_legacy_scores(
    session: Session,
    target_attempt_id: str | None = None,
    shadow: bool = False,
    config: ScoringConfig | None = None,
    provisional_items: list[tuple[Any, Any]] | None = None,
    taxonomy_version_id: int | None = None,
) -> ScoreRun:
    """Recompute all subtopic scores and ingestion coverage, atomically swapping the current run.
    
    Args:
        session: SQLAlchemy DB session
        target_attempt_id: Target attempt (e.g. '2024-11'). Required explicitly for administrative recomputation
        shadow: If True, this is a shadow score run (does not become is_current)
        config: ScoringConfig override. If None, loaded from config/scoring.toml
        provisional_items: Optional list of provisional (Appearance, AppearanceTag) for shadow runs
        
    Returns:
        The newly created ScoreRun
    """
    if config is None:
        config = load_scoring_config()
    from caf_l0.releases import active_version
    from caf_l0.hierarchy import ancestor_at, descendant_leaves, version_nodes
    release = active_version(session)
    if taxonomy_version_id is None and release:
        taxonomy_version_id = release.taxonomy_version_id
    if taxonomy_version_id is not None:
        from caf_db.models.taxonomy import TaxonomyRelease
        scoped_release = session.scalar(sa.select(TaxonomyRelease).where(
            TaxonomyRelease.taxonomy_version_id == taxonomy_version_id
        ))
        if scoped_release is None or scoped_release.status not in {"active", "archived"}:
            raise ValueError("Scoring requires an activated textbook taxonomy version")

    # Administrative recomputation must identify its target explicitly.
    if not target_attempt_id:
        raise ValueError("An explicit target_attempt_id is required")
    target_attempt = session.get(Attempt, target_attempt_id)
    if not target_attempt:
        raise ValueError(f"Unknown target attempt: {target_attempt_id}")

    t_year = target_attempt.exam_year
    t_month = target_attempt.exam_month

    # 2. Insert new ScoreRun (status='running')
    now = datetime.now(timezone.utc)
    new_run = ScoreRun(
        scoring_version=config.version,
        config_hash=config.config_hash,
        config_snapshot=config.model_dump(mode="json"),
        target_attempt_id=target_attempt_id,
        taxonomy_version_id=taxonomy_version_id,
        shadow=shadow,
        is_current=False,
        status="running",
        started_at=now,
    )
    session.add(new_run)
    session.flush()

    try:
        # 3. Load all attempts for age calculations
        all_attempts = {
            att.id: att
            for att in session.query(Attempt).all()
        }

        # 4. Load applicability rules for target attempt
        app_rules = session.query(ApplicabilityRule).where(
            ApplicabilityRule.attempt_id == target_attempt_id
        ).all()
        excluded_nodes = {r.node_id for r in app_rules if r.effect == "exclude"}
        if taxonomy_version_id is not None and target_attempt_id >= "2027-05":
            from caf_l0.releases import source_contexts
            # P4 fallback structure is useful; unresolved historical provisions
            # cannot enter target-attempt scores until applicability is reviewed.
            for node_id, sources in source_contexts(session, taxonomy_version_id).items():
                if any(source.get("paper_id") == "s2023.P4" and source.get("fallback") and
                       source.get("target_applicability") not in {"verified", "applicable"}
                       for source in sources):
                    excluded_nodes.add(node_id)

        # 5. Fetch all active nodes and build hierarchy
        all_nodes = version_nodes(session, taxonomy_version_id)
        nodes_by_id = {n.id: n for n in all_nodes}

        def is_node_applicable(n: Node) -> bool:
            if n.status != "active":
                return False
            # Check node and its ancestors
            curr_id = n.id
            while curr_id:
                if curr_id in excluded_nodes:
                    return False
                curr = nodes_by_id.get(curr_id)
                curr_id = curr.parent_id if curr else None
            return True

        # Active current papers
        current_papers = session.query(Paper).where(Paper.is_current.is_(True)).all()
        current_paper_ids = {p.id for p in current_papers}
        paper_max_marks = {p.id: p.max_marks for p in current_papers}

        # Map subtopics
        subtopics = [
            n for n in all_nodes
            if n.level == "subtopic" and n.paper_id in current_paper_ids
            and not any(child.parent_id == n.id for child in all_nodes)
        ]
        subtopics_by_paper: dict[str, list[Node]] = {}
        for s in subtopics:
            subtopics_by_paper.setdefault(s.paper_id, []).append(s)

        # 6. Compute Weightage Prior W(s)
        # Weightage section midpoint marks: ((min_pct + max_pct) / 2) / 100 * paper_max
        # Generated legacy priors never become official priors for a new release.
        weightage_sections = session.query(WeightageSection).all() if taxonomy_version_id is None else []
        weightage_members = session.query(WeightageMember).all() if taxonomy_version_id is None else []
        
        # chapter_id -> section_id
        ch_to_section = {m.chapter_id: m.section_id for m in weightage_members}
        section_by_id = {s.id: s for s in weightage_sections}

        # Count applicable subtopics per section
        section_applicable_subtopics: dict[str, list[str]] = {}
        for s in subtopics:
            if not is_node_applicable(s):
                continue
            ch = ancestor_at(s.id, nodes_by_id, "chapter")
            if ch and ch.id in ch_to_section:
                sec_id = ch_to_section[ch.id]
                section_applicable_subtopics.setdefault(sec_id, []).append(s.id)

        subtopic_prior_w: dict[str, float] = {}
        for s in subtopics:
            if not is_node_applicable(s):
                subtopic_prior_w[s.id] = 0.0
                continue
            ch = ancestor_at(s.id, nodes_by_id, "chapter")
            sec_id = ch_to_section.get(ch.id) if ch else None
            if sec_id and sec_id in section_by_id:
                sec = section_by_id[sec_id]
                p_max = paper_max_marks.get(sec.paper_id, 100)
                sec_midpoint_pct = float(sec.min_pct + sec.max_pct) / 2.0
                sec_marks = (sec_midpoint_pct / 100.0) * p_max
                applicable_count = len(section_applicable_subtopics.get(sec_id, []))
                subtopic_prior_w[s.id] = sec_marks / applicable_count if applicable_count > 0 else 0.0
            else:
                subtopic_prior_w[s.id] = 0.0

        # 7. Ingestion coverage
        # Query distinct (paper_id, attempt_id, signal_class) with published appearances
        coverage_query = (
            session.query(
                Appearance.source_paper_id,
                Appearance.attempt_id,
                Appearance.signal_class,
            )
            .where(Appearance.status == "published")
        )
        if taxonomy_version_id is not None:
            from caf_db.models.ingest import Document
            coverage_query = coverage_query.join(AppearanceTag, AppearanceTag.appearance_id == Appearance.id).join(
                Document, Document.sha256 == Appearance.doc_sha256
            ).where(AppearanceTag.node_id.in_(nodes_by_id),
                    Document.course_level == "final", Document.provenance_status == "verified")
        pub_appearances_query = coverage_query.distinct().all()

        published_coverage: dict[tuple[str, str], dict[str, bool]] = {}
        for row in pub_appearances_query:
            key = (row.source_paper_id, row.attempt_id)
            if key not in published_coverage:
                published_coverage[key] = {"exam": False, "practice": False}
            if row.signal_class == "exam":
                published_coverage[key]["exam"] = True
            elif row.signal_class == "practice":
                published_coverage[key]["practice"] = True

        if provisional_items:
            for p_app, p_tag in provisional_items:
                if p_tag.node_id not in nodes_by_id:
                    continue
                p_key = (p_app.source_paper_id, p_app.attempt_id)
                if p_key not in published_coverage:
                    published_coverage[p_key] = {"exam": False, "practice": False}
                if p_app.signal_class == "exam":
                    published_coverage[p_key]["exam"] = True
                elif p_app.signal_class == "practice":
                    published_coverage[p_key]["practice"] = True

        # IngestionCoverage records across all current papers and all known attempts
        ingestion_coverage_rows = []
        for paper_id in current_paper_ids:
            for att_id in all_attempts:
                cov = published_coverage.get((paper_id, att_id), {"exam": False, "practice": False})
                ingestion_coverage_rows.append(
                    IngestionCoverage(
                        score_run_id=new_run.id,
                        paper_id=paper_id,
                        attempt_id=att_id,
                        exam_published=cov["exam"],
                        practice_published=cov["practice"],
                    )
                )

        # 8. Compute window(p) for Frequency
        # window(p) = last N attempts <= T for which paper p has any published exam appearance
        paper_exam_attempts: dict[str, list[Attempt]] = {}
        for (p_id, att_id), cov in published_coverage.items():
            if cov["exam"] and att_id in all_attempts:
                att = all_attempts[att_id]
                age = compute_age_months(att.exam_year, att.exam_month, t_year, t_month)
                if age >= 0:  # <= T
                    paper_exam_attempts.setdefault(p_id, []).append(att)

        paper_windows: dict[str, list[str]] = {}
        for p_id in current_paper_ids:
            att_list = paper_exam_attempts.get(p_id, [])
            # Sort descending by exam_year, exam_month
            att_list.sort(key=lambda a: (a.exam_year, a.exam_month), reverse=True)
            top_n = att_list[: config.freq_window_attempts]
            paper_windows[p_id] = [a.id for a in top_n]

        # 9. Load all published appearances with their tags
        appearances_query = (
            session.query(Appearance, AppearanceTag)
            .join(AppearanceTag, AppearanceTag.appearance_id == Appearance.id)
            .where(Appearance.status == "published")
        )
        if taxonomy_version_id is not None:
            appearances_query = appearances_query.join(Document, Document.sha256 == Appearance.doc_sha256).where(
                AppearanceTag.node_id.in_(nodes_by_id),
                Document.course_level == "final", Document.provenance_status == "verified",
            )
        apps_with_tags = appearances_query.all()
        if provisional_items:
            apps_with_tags = list(apps_with_tags) + list(provisional_items)

        # Subtopic appearance metrics
        # subtopic_id -> metrics dict
        subtopic_stats: dict[str, dict[str, Any]] = {}
        for s in subtopics:
            subtopic_stats[s.id] = {
                "exam_score": 0.0,
                "practice_score": 0.0,
                "exam_marks_total": 0.0,
                "exam_count": 0,
                "practice_count": 0,
                "exam_attempts": set(),
                "all_exam_attempts": [],
            }

        def resolve_subtopic_targets(node_id: str, tag_share: float) -> list[tuple[str, float]]:
            subs = [leaf for leaf in descendant_leaves(node_id, nodes_by_id)
                    if is_node_applicable(nodes_by_id[leaf])]
            if not subs:
                return []
            return [(leaf, tag_share / len(subs)) for leaf in subs]

        for app, tag in apps_with_tags:
            att = all_attempts.get(app.attempt_id)
            if not att:
                continue

            age_months = compute_age_months(att.exam_year, att.exam_month, t_year, t_month)
            if age_months < 0:
                # Appearance from attempt strictly after target T is ignored
                continue

            target_subs = resolve_subtopic_targets(tag.node_id, tag.share)
            for s_id, s_share in target_subs:
                if s_id not in subtopic_stats:
                    continue

                s_node = nodes_by_id[s_id]
                m, kappa, lambda_val = calculate_attributed_marks(
                    marks=app.marks,
                    share=s_share,
                    source_paper_id=app.source_paper_id,
                    target_node_paper_id=s_node.paper_id,
                    law_stale=app.law_stale,
                    config=config,
                )

                stats = subtopic_stats[s_id]
                if app.signal_class == "exam":
                    decay_e = compute_decay(age_months, config.half_life_exam_months)
                    stats["exam_score"] += m * decay_e
                    stats["exam_marks_total"] += (float(app.marks) if app.marks else 0.0) * s_share
                    stats["exam_count"] += 1
                    stats["exam_attempts"].add(app.attempt_id)
                    stats["all_exam_attempts"].append(att)
                elif app.signal_class == "practice":
                    decay_p = compute_decay(age_months, config.half_life_practice_months)
                    stats["practice_score"] += m * decay_p
                    stats["practice_count"] += 1

        # 10. Normalization and Importance per paper
        subtopic_score_rows = []
        for paper_id, p_subtopics in subtopics_by_paper.items():
            win = paper_windows.get(paper_id, [])
            freq_window_len = len(win)
            win_set = set(win)

            # Applicable subtopics in this paper
            app_subs = [s for s in p_subtopics if is_node_applicable(s)]

            # Find maxima over applicable subtopics
            max_e = max([subtopic_stats[s.id]["exam_score"] for s in app_subs], default=0.0)
            max_p = max([subtopic_stats[s.id]["practice_score"] for s in app_subs], default=0.0)
            max_w = max([subtopic_prior_w[s.id] for s in app_subs], default=0.0)

            for s in p_subtopics:
                applicable = is_node_applicable(s)
                stats = subtopic_stats[s.id]
                prior_w = subtopic_prior_w.get(s.id, 0.0)
                e_score = stats["exam_score"]
                p_score = stats["practice_score"]

                if applicable:
                    e_norm = (e_score / max_e) if max_e > 0 else 0.0
                    p_norm = (p_score / max_p) if max_p > 0 else 0.0
                    w_norm = (prior_w / max_w) if max_w > 0 else 0.0
                    importance = (
                        config.weights.exam * e_norm
                        + config.weights.practice * p_norm
                        + config.weights.prior * w_norm
                    )
                else:
                    importance = 0.0

                # Frequency hits in window(p)
                hits_in_window = len(stats["exam_attempts"].intersection(win_set))

                # First and last exam attempt
                first_att_label = None
                last_att_label = None
                if stats["all_exam_attempts"]:
                    sorted_atts = sorted(
                        stats["all_exam_attempts"],
                        key=lambda a: (a.exam_year, a.exam_month),
                    )
                    first_att_label = sorted_atts[0].id
                    last_att_label = sorted_atts[-1].id

                subtopic_score_rows.append(
                    SubtopicScore(
                        score_run_id=new_run.id,
                        node_id=s.id,
                        applicable=applicable,
                        exam_score=round(e_score, 4),
                        practice_score=round(p_score, 4),
                        weight_prior=round(prior_w, 4),
                        importance=round(importance, 4),
                        freq_hits=hits_in_window,
                        freq_window=freq_window_len,
                        exam_marks_total=int(round(stats["exam_marks_total"])),
                        exam_count=stats["exam_count"],
                        practice_count=stats["practice_count"],
                        first_exam_attempt=first_att_label,
                        last_exam_attempt=last_att_label,
                    )
                )

        # 11. Bulk insert scores and coverage
        session.bulk_save_objects(subtopic_score_rows)
        session.bulk_save_objects(ingestion_coverage_rows)
        session.flush()

        # 12. Atomic Swap: if not shadow, set old runs is_current=False and this run is_current=True
        if not shadow:
            session.execute(
                sa.update(ScoreRun)
                .where(ScoreRun.is_current.is_(True), ScoreRun.id != new_run.id,
                       ScoreRun.target_attempt_id == target_attempt_id,
                       ScoreRun.taxonomy_version_id == taxonomy_version_id,
                       ScoreRun.config_hash == config.config_hash)
                .values(is_current=False)
            )
            new_run.is_current = True

        new_run.status = "ok"
        new_run.finished_at = datetime.now(timezone.utc)
        session.flush()

        # Preserve historical score runs across attempt and taxonomy changes.
        session.commit()
        logger.info(
            f"L5 score recompute complete: run_id={new_run.id}, "
            f"subtopics={len(subtopic_score_rows)}, "
            f"target_attempt={target_attempt_id}, shadow={shadow}"
        )
        return new_run

    except Exception as exc:
        session.rollback()
        # Mark as failed in separate transaction
        try:
            with session.begin_nested():
                failed_run = session.get(ScoreRun, new_run.id)
                if failed_run:
                    failed_run.status = "failed"
                    failed_run.finished_at = datetime.now(timezone.utc)
                    session.commit()
        except Exception:
            pass
        logger.exception(f"L5 score recompute failed: {exc}")
        raise


def coverage_eligibility(row) -> tuple[bool, list[str]]:
    """Reviewed official scope, not publication count or optional-mark totals."""
    requirements = {
        "inventory_unreviewed": row.inventory_reviewed,
        "expected_inventory_unknown": row.expected_slots is not None,
        "sources_not_acquired": row.expected_slots is not None and row.acquired_count >= row.expected_slots,
        "metadata_unreviewed": row.metadata_reviewed,
        "extraction_unreviewed": row.extraction_reviewed,
        "pairing_unreviewed": row.pairing_reviewed,
        "official_scope_unconfirmed": row.official_scope_confirmed,
        "gradable_regions_unaccounted": row.gradable_regions_accounted,
        "labels_incomplete": row.labels_complete,
        "occurrence_identity_unresolved": row.occurrence_resolved,
        "unpublished_roots": row.published_roots >= row.reviewed_roots > 0,
    }
    blockers = [name for name, satisfied in requirements.items() if not satisfied]
    blockers.extend(row.blockers or [])
    return not blockers, list(dict.fromkeys(blockers))


def normalized_component(raw: float, denominator: float, available: bool,
                         weight: float) -> dict[str, Any]:
    normalized = (raw / denominator if denominator > 0 else 0.0) if available else None
    return {"available": available, "raw": raw if available else None,
            "denominator": denominator if available else None, "normalized": normalized,
            "weight": weight, "weighted_contribution": weight * normalized if available else None}


def publication_exclusions(publication) -> list[str]:
    blockers = []
    if publication.content["question_status"] != "complete":
        blockers.append("question_scope_incomplete")
    if any(mapping["outcome"] != "matched" and not mapping["excluded"] for mapping in publication.mappings):
        blockers.append("labels_unresolved_without_explicit_exclusion")
    allocations = publication.marks["allocations"]
    if not allocations or publication.marks["issues"] or any(
            allocation["allocation_status"] != "reviewed" or allocation["marks"] is None for allocation in allocations):
        blockers.append("marks_allocation_unresolved")
    return blockers


def promote_score_run(session: Session, run: ScoreRun) -> bool:
    """Lock the generation and prevent late workers from replacing newer results."""
    from caf_db.models.questions import CorpusGeneration
    generation = session.scalar(sa.select(CorpusGeneration).where(
        CorpusGeneration.id == 1).with_for_update())
    latest = generation.generation if generation else 0
    current = session.scalar(sa.select(ScoreRun).where(
        ScoreRun.target_attempt_id == run.target_attempt_id,
        ScoreRun.taxonomy_version_id == run.taxonomy_version_id,
        ScoreRun.config_hash == run.config_hash, ScoreRun.is_current.is_(True),
        ScoreRun.shadow.is_(False), ScoreRun.id != run.id).with_for_update())
    run.stale = run.corpus_generation != latest
    eligible = not run.shadow and not run.stale and (
        current is None or (run.corpus_generation, run.id) > (current.corpus_generation, current.id))
    if eligible:
        if current:
            current.is_current = False
            session.flush()
        run.is_current = True
    session.flush()
    return eligible


def recompute_scores(session: Session, target_attempt_id: str | None = None,
                     shadow: bool = False, config: ScoringConfig | None = None,
                     provisional_items: list[tuple[Any, Any]] | None = None,
                     taxonomy_version_id: int | None = None, *, promote: bool = True) -> ScoreRun:
    """Persist complete inputs and nullable components for one approved context."""
    from caf_l5.context import approved_binding, corpus_generation, context_nodes, context_leaf_ids, StudyContext
    from caf_db.models.intel import CorpusCoverage, ReviewedPrior
    from caf_db.models.questions import PublishedQuestion, QuestionOccurrence
    from caf_db.models.classification import QuestionPublication
    if not target_attempt_id:
        raise ValueError("An explicit target_attempt_id is required")
    binding = approved_binding(session, target_attempt_id, taxonomy_version_id)
    if binding:
        taxonomy_version_id = binding.taxonomy_version_id
        config = config or (ScoringConfig.model_validate(binding.scoring_config)
                           if binding.scoring_config else load_scoring_config())
    elif taxonomy_version_id is not None:
        raise ValueError("Scoring requires an approved target-attempt taxonomy binding")
    else:
        from caf_db.models.taxonomy import TaxonomyRelease
        if session.scalar(sa.select(TaxonomyRelease.taxonomy_version_id).where(
            TaxonomyRelease.status != "legacy").limit(1)) is not None:
            raise ValueError("Scoring requires an approved target-attempt taxonomy binding")
        return recompute_legacy_scores(session, target_attempt_id, shadow, config,
                                       provisional_items, taxonomy_version_id=None)
    if provisional_items:
        raise ValueError("Experimental classifications cannot enter reviewed scoring")
    config = config or load_scoring_config()
    target = session.get(Attempt, target_attempt_id)
    if target is None:
        raise ValueError(f"Unknown target attempt: {target_attempt_id}")
    generation = corpus_generation(session)
    context = StudyContext(target_attempt_id, taxonomy_version_id, None, "ready", config, {})
    nodes = context_nodes(session, context)
    terminal_ids = context_leaf_ids(session, context)
    leaves = [node for node in nodes if node.id in terminal_ids]
    attempts = {row.id: row for row in session.scalars(sa.select(Attempt))}
    coverage_rows = list(session.scalars(sa.select(CorpusCoverage).where(
        CorpusCoverage.taxonomy_version_id == taxonomy_version_id)))
    usable: dict[str, set[str]] = {}
    exclusions = []
    coverage_manifest = []
    for row in coverage_rows:
        eligible, blockers = coverage_eligibility(row)
        entry = {column.name: row.__dict__[column.name] for column in CorpusCoverage.__table__.columns}
        entry.update(eligible=eligible, exclusions=blockers)
        coverage_manifest.append(entry)
        att = attempts[row.attempt_id]
        before_target = compute_age_months(att.exam_year, att.exam_month,
                                          target.exam_year, target.exam_month) > 0
        if eligible and row.source_family in {"QP", "question_paper", "exam", "past_exam"} and before_target:
            usable.setdefault(row.paper_id, set()).add(row.attempt_id)
        elif row.source_family in {"QP", "question_paper", "exam", "past_exam"}:
            exclusions.append({"paper_id": row.paper_id, "attempt_id": row.attempt_id,
                               "reasons": blockers or ["not_before_target"]})
    publications = session.execute(sa.select(PublishedQuestion, QuestionOccurrence).join(
        QuestionPublication, QuestionPublication.current_snapshot_id == PublishedQuestion.id).join(
        QuestionOccurrence, QuestionOccurrence.id == PublishedQuestion.occurrence_id).where(
        PublishedQuestion.taxonomy_version_id == taxonomy_version_id)).all()
    # Canonical identity can have several source-backed publications. A question
    # paper and confirmed answer counterpart contribute one occurrence only.
    canonical = {}
    ambiguous_groups = set()
    publication_documents = {row.current_snapshot_id: row.document_id for row in session.scalars(
        sa.select(QuestionPublication).where(QuestionPublication.current_snapshot_id.is_not(None)))}
    identities = {row.id: row for row in session.scalars(sa.select(QuestionOccurrence))}
    for publication, occurrence in publications:
        identity = identities.get(occurrence.canonical_occurrence_id) if occurrence.canonical_occurrence_id else occurrence
        if identity is None or identity.canonical_occurrence_id is not None:
            raise ValueError("Canonical occurrence must resolve to one confirmed root identity")
        if occurrence.identity_status != "confirmed":
            ambiguous_groups.add(identity.id)
        existing = canonical.get(identity.id)
        # Prefer the canonical question paper over its answer projection.
        prefer = publication_documents.get(publication.id) == identity.pairing_evidence.get("canonical_document_id")
        if existing is None or (prefer and not existing[2]) or (prefer == existing[2] and publication.id > existing[0].id):
            canonical[identity.id] = (publication, identity, prefer)
    canonical = {key: (value[0], value[1]) for key, value in canonical.items()}
    # A ledger cannot override contradictory publication evidence: unresolved
    # identity or gradable allocations invalidate the entire exam denominator.
    for publication, occurrence in canonical.values():
        blockers = publication_exclusions(publication)
        if occurrence.identity_status != "confirmed" or occurrence.id in ambiguous_groups:
            blockers.append("occurrence_identity_unresolved")
        if occurrence.signal_class == "exam" and blockers:
            usable.get(occurrence.paper_id, set()).discard(occurrence.attempt_id)
            exclusions.append({"paper_id": occurrence.paper_id, "attempt_id": occurrence.attempt_id,
                               "reasons": ["published_occurrence_or_allocation_unresolved", *blockers]})
    from caf_db.models.ingest import Document
    from urllib.parse import urlparse
    official_hashes = set(session.scalars(sa.select(Document.sha256).where(
        Document.doc_type_id == "weightage", Document.provenance_status == "verified",
        Document.course_level == "final", Document.catalog_status == "confirmed")))
    prior_rows = list(session.scalars(sa.select(ReviewedPrior).where(
        ReviewedPrior.taxonomy_version_id == taxonomy_version_id,
        ReviewedPrior.reviewed_by.is_not(None))))
    priors = {}
    for row in prior_rows:
        source = row.source
        url = urlparse(source.get("official_url", ""))
        if (source.get("kind") == "official_weightage" and
                source.get("taxonomy_version_id") == taxonomy_version_id and
                source.get("document_sha256") in official_hashes and url.scheme == "https" and
                url.hostname in {"www.icai.org", "icai.org", "resource.cdn.icai.org"}):
            priors[row.node_id] = row
    stats = {node.id: {"exam": 0.0, "practice": 0.0, "exam_marks": 0.0,
             "exam_ids": set(), "practice_ids": set(), "hit_attempts": set(), "contributions": []}
             for node in leaves}
    practice_papers = set()
    occurrence_manifest = []
    for publication, occurrence in canonical.values():
        entry = {"occurrence_id": occurrence.id, "snapshot_id": publication.id,
                 "identity_status": occurrence.identity_status, "attempt_id": occurrence.attempt_id,
                 "paper_id": occurrence.paper_id, "source_family": occurrence.source_family,
                 "signal_class": occurrence.signal_class, "marks": publication.marks,
                 "mappings": publication.mappings, "question_status": publication.content["question_status"]}
        occurrence_manifest.append(entry)
        att = attempts.get(occurrence.attempt_id)
        if occurrence.identity_status != "confirmed" or occurrence.id in ambiguous_groups or att is None:
            entry["exclusion"] = "identity_unresolved" if occurrence.identity_status != "confirmed" else "undated"
            continue
        age = compute_age_months(att.exam_year, att.exam_month, target.exam_year, target.exam_month)
        if age < 0 or (age == 0 and occurrence.signal_class == "exam"):
            entry["exclusion"] = "not_before_target"
            continue
        if occurrence.signal_class == "exam" and occurrence.attempt_id not in usable.get(occurrence.paper_id, set()):
            entry["exclusion"] = "incomplete_attempt"
            continue
        if occurrence.signal_class not in {"exam", "practice"}:
            entry["exclusion"] = "unsupported_signal"
            continue
        blockers = publication_exclusions(publication)
        if blockers:
            entry["exclusion"] = blockers[0]
            entry["exclusion_reasons"] = blockers
            continue
        valid_allocations = publication.marks["allocations"]
        if occurrence.signal_class == "practice":
            practice_papers.add(occurrence.paper_id)
        half_life = config.half_life_exam_months if occurrence.signal_class == "exam" else config.half_life_practice_months
        decay = compute_decay(age, half_life)
        for allocation in valid_allocations:
            for share in allocation["node_shares"]:
                node_id = share["node_id"]
                if node_id not in stats or share["attributed_marks"] is None:
                    continue
                node = next(node for node in leaves if node.id == node_id)
                marks, kappa, stale_factor = calculate_attributed_marks(allocation["marks"], share["share"],
                    occurrence.paper_id, node.paper_id, False, config)
                item = stats[node_id]
                signal = occurrence.signal_class
                item[signal] += marks * decay
                item[f"{signal}_ids"].add(occurrence.id)
                if signal == "exam":
                    item["exam_marks"] += allocation["marks"] * share["share"]
                    item["hit_attempts"].add(occurrence.attempt_id)
                item["contributions"].append({"occurrence_id": occurrence.id,
                    "snapshot_id": publication.id, "part_id": allocation["part_id"],
                    "attempt_id": occurrence.attempt_id, "signal_class": signal,
                    "marks": allocation["marks"], "share": share["share"],
                    "attributed_marks_m": marks, "kappa": kappa, "lambda_val": stale_factor,
                    "age_months": age, "half_life_months": half_life, "decay": decay,
                    "contribution": marks * decay})
    for entry in coverage_manifest:
        extra = [reason for exclusion in exclusions if exclusion["paper_id"] == entry["paper_id"] and
                 exclusion["attempt_id"] == entry["attempt_id"] for reason in exclusion["reasons"]]
        if extra:
            entry["eligible"] = False
            entry["exclusions"] = list(dict.fromkeys([*entry["exclusions"], *extra]))
    manifest = {"semantics_version": "phase6-v1", "target_attempt_id": target_attempt_id,
                "taxonomy_version_id": taxonomy_version_id, "corpus_generation": generation,
                "node_ids": [node.id for node in leaves], "coverage": coverage_manifest,
                "occurrences": occurrence_manifest, "priors": {node_id: {"value": row.value,
                    "source": row.source, "reviewed_by": row.reviewed_by} for node_id, row in priors.items()},
                "configuration": config.model_dump(mode="json")}
    run = ScoreRun(scoring_version="phase6-v1", config_hash=config.config_hash,
                   config_snapshot=config.model_dump(mode="json"), target_attempt_id=target_attempt_id,
                   taxonomy_version_id=taxonomy_version_id, shadow=shadow, is_current=False,
                   status="running", started_at=datetime.now(timezone.utc), corpus_generation=generation,
                   input_manifest=manifest, stale=False)
    session.add(run)
    session.flush()
    for paper_id in {node.paper_id for node in leaves}:
        paper_nodes = [node for node in leaves if node.paper_id == paper_id]
        window = sorted(usable.get(paper_id, set()), key=lambda aid:
            (attempts[aid].exam_year, attempts[aid].exam_month), reverse=True)[:config.freq_window_attempts]
        available = {"exam": bool(usable.get(paper_id)), "practice": paper_id in practice_papers,
                     "prior": all(node.id in priors for node in paper_nodes)}
        denominators = {"exam": max((stats[node.id]["exam"] for node in paper_nodes), default=0),
                        "practice": max((stats[node.id]["practice"] for node in paper_nodes), default=0),
                        "prior": max((priors[node.id].value for node in paper_nodes if node.id in priors), default=0)}
        for node in paper_nodes:
            item = stats[node.id]
            components = {signal: normalized_component(
                priors[node.id].value if signal == "prior" and node.id in priors else
                (0.0 if signal == "prior" else item[signal]), denominators[signal], available[signal],
                config.weights.model_dump()[signal]) for signal in ("exam", "practice", "prior")}
            subtotal = sum(component["weighted_contribution"] or 0.0 for component in components.values())
            full = all(component["available"] for component in components.values())
            hits = sorted(item["hit_attempts"].intersection(window), reverse=True)
            evidence = {"semantics_version": "phase6-v1", "components": components,
                        "known_weighted_subtotal": subtotal, "importance_available": full,
                        "frequency": {"available": bool(window), "window_attempts": window,
                                      "hit_attempts": hits, "numerator": len(hits), "denominator": len(window)},
                        "contributions": item["contributions"],
                        "included_occurrence_ids": sorted(item["exam_ids"] | item["practice_ids"]),
                        "coverage_exclusions": [row for row in exclusions if row["paper_id"] == paper_id],
                        "prior_source": priors[node.id].source if node.id in priors else None}
            session.add(SubtopicScore(score_run_id=run.id, node_id=node.id, applicable=True,
                exam_score=components["exam"]["raw"], practice_score=components["practice"]["raw"],
                weight_prior=components["prior"]["raw"], importance=round(subtotal, 8) if full else None,
                freq_hits=len(hits), freq_window=len(window), exam_marks_total=round(item["exam_marks"]),
                exam_count=len(item["exam_ids"]), practice_count=len(item["practice_ids"]),
                first_exam_attempt=min(item["hit_attempts"], default=None),
                last_exam_attempt=max(item["hit_attempts"], default=None), evidence=evidence))
        for attempt_id in attempts:
            session.add(IngestionCoverage(score_run_id=run.id, paper_id=paper_id, attempt_id=attempt_id,
                exam_published=attempt_id in usable.get(paper_id, set()),
                practice_published=any(entry["paper_id"] == paper_id and entry["attempt_id"] == attempt_id
                    and entry["signal_class"] == "practice" and "exclusion" not in entry for entry in occurrence_manifest)))
    run.status = "ok"
    run.finished_at = datetime.now(timezone.utc)
    session.commit()
    # A fresh transaction sees publications that committed while computation ran.
    if promote:
        promote_score_run(session, run)
        session.commit()
    return run
