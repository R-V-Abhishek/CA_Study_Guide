"""Model Re-evaluation Engine: evaluates model suggestions against human curator decisions."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from sqlalchemy.orm import Session


def evaluation_taxonomy(session: Session, version_id: str | None = None) -> int | None:
    from caf_l0.releases import active_version, get_release
    release = get_release(session, version_id) if version_id else active_version(session)
    return release.taxonomy_version_id if release and release.status != "legacy" else None


@dataclass
class BucketMetric:
    bucket: str
    total: int
    matched: int
    precision: float


@dataclass
class ModelEvaluationReport:
    total_reviewed: int
    top1_matches: int
    top1_agreement: float
    bucket_metrics: dict[str, BucketMetric]
    bucket_a_threshold: float
    passed: bool
    status_note: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    multilabel_precision: float = 0.0
    multilabel_recall: float = 0.0
    unresolved_outcomes: dict[str, int] = field(default_factory=dict)
    candidate_retrieval_misses: int = 0
    strata: dict[str, int] = field(default_factory=dict)
    bucket_a_root_samples: int = 0
    provisional: bool = True
    primary_labeled_samples: int = 0
    outcome_agreement: float = 0.0


def evaluate_model_on_reviewed_decisions(
    session: Session,
    bucket_a_threshold: float = 0.80,
    min_samples: int = 30,
    version_id: str | None = None,
) -> ModelEvaluationReport:
    """Evaluate blind root reviews bound to frozen suggestion and content revisions."""
    taxonomy_version_id = evaluation_taxonomy(session, version_id)
    from caf_db.models.classification import ClassificationRevision, SuggestionRevision
    pairs = session.query(ClassificationRevision, SuggestionRevision).join(
        SuggestionRevision, ClassificationRevision.suggestion_revision_id == SuggestionRevision.id
    ).filter(ClassificationRevision.taxonomy_version_id == taxonomy_version_id,
             ClassificationRevision.blind.is_(True)).order_by(ClassificationRevision.id).all()
    if pairs:
        from caf_l4.revisions import readiness
        provisional = any(not readiness(session, suggestion)['eligible'] for _, suggestion in pairs)
        return evaluate_revision_pairs(pairs, bucket_a_threshold, max(30, min_samples), provisional=provisional)
    return ModelEvaluationReport(
        total_reviewed=0, top1_matches=0, top1_agreement=0.0,
        bucket_metrics={}, bucket_a_threshold=bucket_a_threshold, passed=False,
        status_note="No blind reviews bound to immutable root suggestions for this taxonomy; historical verification remains unknown.",
    )


def evaluate_revision_pairs(pairs: list[tuple], threshold: float = .80,
                            min_samples: int = 30, *, provisional: bool = False) -> ModelEvaluationReport:
    """Compare frozen suggestions to blind labels for identical pinned content."""
    counts = {b: {'total': 0, 'matched': 0} for b in ['A', 'B', 'C', 'D']}
    seen = set()
    total = primary_samples = primary_matches = outcome_matches = true_positive = predicted = actual = misses = a_roots = 0
    unresolved = {'needs_review': 0, 'none_fits': 0}
    strata = {}
    for reviewed, suggestion in pairs:
        if (not reviewed.blind or reviewed.taxonomy_version_id != suggestion.taxonomy_version_id
                or reviewed.input_hash != suggestion.input_hash or reviewed.context != suggestion.context):
            continue
        context = suggestion.context
        from caf_l3.sampling import duplicate_key
        group = duplicate_key(context)
        key = (group, suggestion.taxonomy_version_id)
        if key in seen:
            continue
        seen.add(key)
        provisional = provisional or suggestion.experimental
        by_part = {m['part_id']: m for m in reviewed.mappings}
        candidates = {c['node_id'] for c in suggestion.candidates}
        if set(by_part) != {m['part_id'] for m in suggestion.mappings}:
            continue
        if any(m.get('bucket') == 'A' and m['outcome'] == 'matched'
               and by_part[m['part_id']]['outcome'] != 'needs_review'
               and not by_part[m['part_id']].get('excluded') for m in suggestion.mappings):
            a_roots += 1
        for model in suggestion.mappings:
            human = by_part[model['part_id']]
            if human.get('excluded'):
                continue
            bucket = model.get('bucket') or 'D'
            total += 1
            outcome_matches += model['outcome'] == human['outcome']
            agreed = (model['primary_node_id'] == human['primary_node_id'] and model['outcome'] == human['outcome'])
            if human['outcome'] != 'needs_review' and (model['primary_node_id'] or human['primary_node_id']):
                counts[bucket]['total'] += 1
                counts[bucket]['matched'] += agreed
            if human['primary_node_id']:
                primary_samples += 1
                primary_matches += model['primary_node_id'] == human['primary_node_id']
            mlabels = set(filter(None, [model['primary_node_id'], *model['secondary_node_ids']]))
            hlabels = set(filter(None, [human['primary_node_id'], *human['secondary_node_ids']]))
            true_positive += len(mlabels & hlabels)
            predicted += len(mlabels)
            actual += len(hlabels)
            misses += len(hlabels - candidates)
            if model['outcome'] in unresolved:
                unresolved[model['outcome']] += 1
            stratum = f"{context['paper_id']}:{context['source_family']}:{bucket}"
            strata[stratum] = strata.get(stratum, 0) + 1
    metrics = {b: BucketMetric(b, c['total'], c['matched'], c['matched']/c['total'] if c['total'] else 0)
               for b, c in counts.items()}
    a = metrics['A']
    passed = not provisional and a_roots >= max(30, min_samples) and a.precision >= threshold
    return ModelEvaluationReport(total, primary_matches, primary_matches/primary_samples if primary_samples else 0, metrics,
        threshold, passed, f"{a_roots} independent Bucket A roots ({a.total} parts); minimum {max(30, min_samples)} roots. "
        "Model scores never authorize publication.", multilabel_precision=true_positive/predicted if predicted else 0,
        multilabel_recall=true_positive/actual if actual else 0, unresolved_outcomes=unresolved,
        candidate_retrieval_misses=misses, strata=strata, bucket_a_root_samples=a_roots,
        provisional=provisional, primary_labeled_samples=primary_samples,
        outcome_agreement=outcome_matches/total if total else 0)
