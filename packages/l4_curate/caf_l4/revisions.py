"""Transactional whole-question publication; suggestions never authorize publication."""

from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import json
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
from caf_contracts.classification import PartMapping
from caf_db.models.app import UserAccount
from caf_db.models.classification import (SuggestionRevision, ClassificationRevision,
    QuestionPublication, ClassificationEvent, ClassificationVerification, ClassificationDispute)
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document, Unit
from caf_db.models.core import Appearance, AppearanceTag, ChangeLog, Decision
from caf_db.models.ref import DocType, Paper, Node
from caf_db.models.taxonomy import DescriptorRevision, TaxonomyMember, TaxonomyRelease
from caf_l0.hierarchy import ancestors, version_nodes
from caf_l0.releases import eligible_candidates, source_contexts
from caf_l2.revisions import flatten_snapshots, reviewed_quality
from caf_l4.catalogs import suggestion_candidates


class RevisionConflict(ValueError):
    def __init__(self, message: str, current_revision_id: int | None = None):
        super().__init__(message)
        self.current_revision_id = current_revision_id


class ReadinessError(ValueError):
    def __init__(self, blockers: list[str]):
        super().__init__('Classification is not ready: ' + ', '.join(blockers))
        self.blockers = blockers


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _actor(session: Session, actor_id: int, administrator: bool = False):
    actor = session.execute(select(UserAccount.id, UserAccount.status, UserAccount.role).where(UserAccount.id == actor_id)).first()
    if actor is None or actor.status != 'active' or (administrator and actor.role != 'administrator'):
        raise ValueError('An active authenticated administrator is required' if administrator else 'An active authenticated account is required')
    return actor


def _snapshot_part_ids(revision: ExtractionRevision, question_id: str) -> list[str]:
    root = next((snapshot for snapshot in revision.parsed_units if snapshot['stable_question_id'] == question_id), None)
    if root is None:
        return []
    return [question_id if part is root else question_id + ':' + part['label_path']
        for part in flatten_snapshots([root]) if part['is_gradable']]


@dataclass
class TaxonomyReadinessEvidence:
    release: TaxonomyRelease | None
    latest: dict[str, DescriptorRevision]
    eligible: set[str]
    nodes: dict[str, Node]
    sources: dict[str, list[dict]]
    baseline_state: dict | None = None


def taxonomy_readiness_evidence(session: Session, taxonomy_version_id: int) -> TaxonomyReadinessEvidence:
    from caf_db.models.classification import BaselineAdoption
    release = session.scalar(select(TaxonomyRelease).where(TaxonomyRelease.taxonomy_version_id == taxonomy_version_id))
    if release and session.get(BaselineAdoption, release.version_id):
        from caf_l4.baseline import baseline_evidence
        return TaxonomyReadinessEvidence(release, {}, set(), {}, {}, baseline_evidence(session,session.get(BaselineAdoption,release.version_id),taxonomy_version_id))
    return TaxonomyReadinessEvidence(
        release=session.scalar(select(TaxonomyRelease).where(TaxonomyRelease.taxonomy_version_id == taxonomy_version_id)),
        latest={row.node_id: row for row in session.scalars(select(DescriptorRevision).where(
            DescriptorRevision.taxonomy_version_id == taxonomy_version_id).order_by(DescriptorRevision.revision))},
        eligible={node.node_id for node in eligible_candidates(session, taxonomy_version_id)},
        nodes={node.id: node for node in version_nodes(session, taxonomy_version_id)},
        sources=source_contexts(session, taxonomy_version_id),
    )


def readiness(session: Session, suggestion: SuggestionRevision,
              taxonomy_evidence: TaxonomyReadinessEvidence | None = None) -> dict:
    """Recompute gates from pinned evidence and present state; do not rewrite evidence."""
    if suggestion.provenance.get('baseline_release_id'):
        from caf_l4.baseline import baseline_readiness
        return baseline_readiness(session,suggestion,taxonomy_evidence.baseline_state if taxonomy_evidence else None)
    blockers = []
    stale = False
    if suggestion.experimental:
        blockers.append('experimental_suggestion')
    revision = session.get(ExtractionRevision, suggestion.extraction_revision_id)
    document = session.get(Document, suggestion.document_id)
    if revision is None or document is None or revision.document_id != suggestion.document_id:
        blockers.append('extraction_missing')
        stale = True
    else:
        if (document.catalog_status != 'confirmed' or document.course_level != 'final'
                or document.scheme_id != 's2023' or document.provenance_status != 'verified'):
            blockers.append('source_identity_or_provenance')
        paper = session.get(Paper, suggestion.context['paper_id'])
        source_papers = {span['paper_id'] for span in document.paper_page_ranges} if document.paper_page_ranges else {document.paper_id}
        if paper is None or paper.scheme_id != 's2023' or not paper.is_current or paper.id not in source_papers:
            blockers.append('source_paper_scope')
        for source_id in set(suggestion.context['source_document_ids']) - {suggestion.document_id}:
            source = session.get(Document, source_id)
            if (source is None or source.catalog_status != 'confirmed' or source.course_level != 'final'
                    or source.scheme_id != 's2023' or source.provenance_status != 'verified'):
                blockers.append('answer_source_identity_or_provenance')
        question = next((q for q in revision.questions if q['question_id'] == suggestion.question_id), None)
        snapshot_context = {k: v for k, v in suggestion.context.items() if k != 'classification_part_ids'}
        if _snapshot_part_ids(revision, suggestion.question_id) != suggestion.context.get('classification_part_ids'):
            blockers.append('stale_part_mapping')
            stale = True
        if question != snapshot_context or revision.status in {'superseded', 'failed'} or document.superseded or (document.current_revision_id not in {None, revision.id, revision.base_revision_id}):
            blockers.append('stale_extraction')
            stale = True
        if revision.status != 'current' or document.current_revision_id != revision.id:
            blockers.append('extraction_not_current')
        if suggestion.provenance.get('extraction_digest') != revision.content_digest:
            blockers.append('stale_extraction_digest')
            stale = True
        record = dict(question_id=suggestion.question_id, document_id=document.id, document_sha256=document.sha256,
            extraction_revision_id=revision.id, extraction_digest=revision.content_digest,
            context=suggestion.context, candidates=suggestion_candidates(session,suggestion))
        if _hash(record) != suggestion.input_hash:
            blockers.append('stale_input_hash')
            stale = True
        quality = reviewed_quality(session, revision)
        for dimension in ('metadata','questions','answers','pairing','ordering','marks_choices','readability','human_review'):
            if quality.get(dimension) not in {'passed', 'not_applicable'}:
                blockers.append('extraction_' + dimension)
    evidence = taxonomy_evidence or taxonomy_readiness_evidence(session, suggestion.taxonomy_version_id)
    release = evidence.release
    if release is None or release.status not in {'approved', 'active'} or not release.approved_by:
        blockers.append('taxonomy_review')
    if release is not None and suggestion.provenance.get('taxonomy_manifest_hash') != release.manifest_hash:
        blockers.append('stale_taxonomy')
        stale = True
    latest, eligible, nodes, sources = evidence.latest, evidence.eligible, evidence.nodes, evidence.sources
    for candidate in suggestion_candidates(session,suggestion):
        node_id = candidate['node_id']
        descriptor = latest.get(node_id)
        pinned_id = candidate.get('descriptor_revision_id')
        pinned_hash = candidate.get('descriptor_hash', candidate.get('descriptor_content_hash'))
        if descriptor is None or pinned_id != descriptor.id or pinned_hash != descriptor.content_hash:
            blockers.append('stale_descriptor:' + node_id)
            stale = True
        if node_id not in eligible:
            blockers.append('descriptor_or_source_review:' + node_id)
        source_hash = _hash([ref for node in ancestors(node_id, nodes) for ref in sources.get(node.id, [])])
        if candidate.get('source_evidence_hash') != source_hash:
            blockers.append('stale_source_evidence:' + node_id)
            stale = True
    return dict(eligible=not blockers, experimental=suggestion.experimental, stale=stale, blockers=sorted(set(blockers)))


def validate_mappings(session: Session, suggestion: SuggestionRevision, mappings: list[dict], *,
                      members: dict | None = None, candidate_ids: set | None = None) -> list[dict]:
    values = [PartMapping.model_validate(mapping).model_dump(mode='json') for mapping in mappings]
    revision = session.get(ExtractionRevision, suggestion.extraction_revision_id)
    expected_parts = _snapshot_part_ids(revision, suggestion.question_id)
    if not expected_parts or len(values) != len({mapping['part_id'] for mapping in values}) or {m['part_id'] for m in values} != set(expected_parts):
        raise ValueError('Complete root mapping must contain each gradable part exactly once')
    if members is None:
        members = {member.node_id: member for member in session.scalars(select(TaxonomyMember).where(
            TaxonomyMember.taxonomy_version_id == suggestion.taxonomy_version_id))}
    paper = suggestion.context['paper_id']
    if candidate_ids is None:
        candidate_ids = {candidate['node_id'] for candidate in suggestion_candidates(session,suggestion)}
    for mapping in values:
        ids = [mapping['primary_node_id'], *mapping['secondary_node_ids']]
        for node_id in filter(None, ids):
            node = members.get(node_id)
            if node is None or node.level != 'subtopic':
                raise ValueError('Unsupported taxonomy label: ' + node_id)
            if paper.split('.')[-1] != 'P6' and node.paper_id != paper:
                raise ValueError('Out-of-paper taxonomy label: ' + node_id)
            # Review edits may select any eligible member, but must pin its evidence
            # by producing a new suggestion if it was outside this candidate set.
            if node_id not in candidate_ids:
                raise ValueError('Label has no pinned candidate evidence: ' + node_id)
    return values


def _locked(session: Session, suggestion: SuggestionRevision):
    _source_locks(session, suggestion)
    publication = session.scalar(select(QuestionPublication).where(QuestionPublication.question_id == suggestion.question_id)
        .with_for_update().execution_options(populate_existing=True))
    if publication is None:
        publication = QuestionPublication(question_id=suggestion.question_id, document_id=suggestion.document_id)
        session.add(publication)
        session.flush()
    return publication


def _source_locks(session, suggestion):
    session.execute(text('SELECT pg_advisory_xact_lock(731306)'))
    revision = session.get(ExtractionRevision, suggestion.extraction_revision_id, populate_existing=True)
    source_ids = {suggestion.document_id, *suggestion.context['source_document_ids']}
    if revision and revision.configuration.get('predecessor_document_id'):
        source_ids.add(revision.configuration['predecessor_document_id'])
    for document_id in sorted(source_ids):
        session.execute(text('SELECT pg_advisory_xact_lock(:document_id)'), {'document_id': document_id})
    for document_id in source_ids:
        session.get(Document, document_id, populate_existing=True)
    session.get(ExtractionRevision, suggestion.extraction_revision_id, populate_existing=True)


def _expect(session, suggestion, publication, expected_suggestion_revision_id, expected_publication_revision_id):
    latest = session.scalar(select(SuggestionRevision.id).where(
        SuggestionRevision.question_id == suggestion.question_id,
        SuggestionRevision.taxonomy_version_id == suggestion.taxonomy_version_id,
    ).order_by(SuggestionRevision.id.desc()).limit(1))
    if expected_suggestion_revision_id != suggestion.id or latest != suggestion.id or publication.current_revision_id != expected_publication_revision_id:
        raise RevisionConflict('Suggestion or publication changed; compare the current revision before submitting', publication.current_revision_id)


def _retry(session, actor_id, key, kind, request):
    if not key or len(key) > 200:
        raise ValueError('A bounded idempotency key is required')
    previous = session.scalar(select(ClassificationEvent).where(ClassificationEvent.actor_id == actor_id, ClassificationEvent.idempotency_key == key))
    if previous is not None:
        if previous.kind != kind or previous.request_hash != _hash(request):
            raise RevisionConflict('Idempotency key already belongs to a different request')
        return {key: value for key, value in previous.payload.items() if key != 'request'}
    return None


def _event(session, suggestion, actor_id, key, kind, request, result):
    session.add(ClassificationEvent(question_id=suggestion.question_id, revision_id=result.get('revision_id'), actor_id=actor_id,
        idempotency_key=key, kind=kind, request_hash=_hash(request), payload={**result, 'request': request}))
    session.flush()
    return result


def verification_count(session: Session, revision_id: int | None) -> int:
    if revision_id is None:
        return 0
    return session.scalar(select(func.count()).select_from(ClassificationVerification).where(
        ClassificationVerification.revision_id == revision_id, ClassificationVerification.active.is_(True))) or 0


def _verify(session, revision, actor_id, active=True):
    row = session.scalar(select(ClassificationVerification).where(ClassificationVerification.revision_id == revision.id,
        ClassificationVerification.actor_id == actor_id))
    if row is None:
        row = ClassificationVerification(revision_id=revision.id, actor_id=actor_id, active=active)
        session.add(row)
    else:
        row.active = active
    session.flush()


def _revision(session, suggestion, publication, actor_id, mappings, blind=False):
    row = ClassificationRevision(question_id=suggestion.question_id, suggestion_revision_id=suggestion.id,
        extraction_revision_id=suggestion.extraction_revision_id, taxonomy_version_id=suggestion.taxonomy_version_id,
        previous_revision_id=publication.current_revision_id, mappings=mappings, context=suggestion.context,
        input_hash=suggestion.input_hash, actor_id=actor_id, blind=blind)
    session.add(row)
    session.flush()
    return row


def _project_appearances(session, suggestion, revision, snapshot):
    """Keep the existing question-index projection linked to revision evidence."""
    from caf_l4.publish import compute_law_stale
    document = session.get(Document, suggestion.document_id)
    doc_type = session.get(DocType, document.doc_type_id) if document.doc_type_id else None
    unit_scope = Unit.revision_id == suggestion.extraction_revision_id if suggestion.provenance.get('baseline_release_id') else Unit.current.is_(True)
    units = list(session.scalars(select(Unit).where(Unit.document_id == suggestion.document_id,
        Unit.stable_question_id == suggestion.question_id, unit_scope, Unit.is_gradable.is_(True))))
    old_appearances = session.scalars(select(Appearance).join(Unit, Appearance.source_unit_id == Unit.id).where(
        Unit.stable_question_id == suggestion.question_id, Unit.current.is_(False), Appearance.status == 'published'))
    for old in old_appearances:
        old.status = 'withdrawn'
    by_part = {suggestion.question_id if unit.parent_unit_id is None else suggestion.question_id + ':' + unit.label_path: unit for unit in units}
    for mapping in revision.mappings:
        unit = by_part.get(mapping['part_id'])
        if unit is None:
            raise ReadinessError(['current_part_missing:' + mapping['part_id']])
        excluded = mapping['excluded']
        matched = mapping['outcome'] == 'matched' and not excluded
        action = 'exclude' if excluded else 'edit' if matched else 'none_fits'
        decision = Decision(unit_fingerprint=unit.fingerprint, actor_id=revision.actor_id, action=action,
            payload={**mapping, 'classification_revision_id': revision.id}, suggestion_run_id=suggestion.run_id,
            blind=revision.blind)
        session.add(decision)
        session.flush()
        appearance = session.scalar(select(Appearance).where(Appearance.unit_fingerprint == unit.fingerprint))
        if not matched:
            if appearance:
                appearance.status = 'withdrawn'
                session.execute(delete(AppearanceTag).where(AppearanceTag.appearance_id == appearance.id))
            unit.classify_status = 'excluded' if excluded else 'needs_review'
            continue
        unit.classify_status = 'decided'
        # The legacy intelligence projection requires an actual attempt. Undated
        # collections retain their authoritative root publication without an
        # invented attempt or document type.
        if not document.attempt_id or doc_type is None:
            session.add(ChangeLog(entity='classification', entity_id=str(revision.id), change='projection_deferred',
                after={'part_id': mapping['part_id']}, reason='Legacy appearance requires a dated source and confirmed document type'))
            continue
        nodes = [mapping['primary_node_id'], *mapping['secondary_node_ids']]
        source_paper = suggestion.context['paper_id']
        values = dict(question_id=suggestion.question_id, part_id=mapping['part_id'], occurrence_id=snapshot.occurrence_id, source_unit_id=unit.id, doc_sha256=document.sha256, attempt_id=document.attempt_id,
            source_paper_id=source_paper, doc_type_id=document.doc_type_id, signal_class=doc_type.signal_class,
            series=document.series, display_label=unit.display_label, marks=unit.marks,
            gist=unit.question_text[:500] or unit.display_label, page_start=unit.page_start, page_end=unit.page_end,
            law_stale=compute_law_stale(session, document.attempt_id, source_paper, nodes), status='published')
        if appearance is None:
            appearance = Appearance(unit_fingerprint=unit.fingerprint, **values)
            session.add(appearance)
            session.flush()
        else:
            appearance.question_id, appearance.part_id, appearance.occurrence_id = suggestion.question_id, mapping['part_id'], snapshot.occurrence_id
            appearance.source_unit_id = unit.id
            appearance.doc_sha256 = document.sha256
            appearance.attempt_id = document.attempt_id
            appearance.source_paper_id = source_paper
            appearance.doc_type_id = document.doc_type_id
            appearance.signal_class = doc_type.signal_class
            appearance.series = document.series
            appearance.display_label = unit.display_label
            appearance.marks = unit.marks
            appearance.gist = values['gist']
            appearance.page_start, appearance.page_end = unit.page_start, unit.page_end
            appearance.law_stale, appearance.status = values['law_stale'], 'published'
            session.execute(delete(AppearanceTag).where(AppearanceTag.appearance_id == appearance.id))
        total_weight = 1 + .5 * len(mapping['secondary_node_ids'])
        for index, node_id in enumerate(nodes):
            session.add(AppearanceTag(appearance_id=appearance.id, node_id=node_id,
                role='primary' if index == 0 else 'secondary', share=(1 if index == 0 else .5) / total_weight,
                decision_id=decision.id))
    session.flush()


def _result(session, publication, revision_id=None, **extra):
    return dict(revision_id=revision_id, current_revision_id=publication.current_revision_id,
        verification_count=verification_count(session, publication.current_revision_id), pending=False, **extra)


def _material_mapping(mappings):
    return sorted((mapping['part_id'], mapping['outcome'], bool(mapping.get('excluded')),
        mapping.get('primary_node_id'), tuple(sorted(mapping['secondary_node_ids']))) for mapping in mappings)


def review_classification(session: Session, suggestion_id: int, actor_id: int, mappings: list[dict],
        expected_suggestion_revision_id: int, expected_publication_revision_id: int | None,
        idempotency_key: str, blind: bool = False, note: str = '') -> dict:
    _actor(session, actor_id)
    suggestion = session.get(SuggestionRevision, suggestion_id)
    if suggestion is None:
        raise ValueError('Suggestion revision not found')
    publication = _locked(session, suggestion)
    request = dict(suggestion_id=suggestion_id, mappings=mappings, expected_suggestion_revision_id=expected_suggestion_revision_id,
        expected_publication_revision_id=expected_publication_revision_id, blind=blind, note=note)
    retry = _retry(session, actor_id, idempotency_key, 'review', request)
    if retry is not None:
        return retry
    _expect(session, suggestion, publication, expected_suggestion_revision_id, expected_publication_revision_id)
    values = validate_mappings(session, suggestion, mappings)
    if blind:
        # Benchmark annotation is independent evidence, not a publication or
        # student confirmation of model suggestions. Draft annotation is allowed.
        revision = _revision(session, suggestion, publication, actor_id, values, blind=True)
        result = _result(session, publication, revision.id)
        result.update(pending=True, status='benchmark', note=note)
        return _event(session, suggestion, actor_id, idempotency_key, 'review', request, result)
    gates = readiness(session, suggestion)
    if not gates['eligible']:
        raise ReadinessError(gates['blockers'])
    if any(m['outcome'] == 'needs_review' and not m['excluded'] for m in values):
        raise ReadinessError(['unresolved_mapping'])
    if session.scalar(select(ClassificationDispute.id).where(ClassificationDispute.question_id == suggestion.question_id,
            ClassificationDispute.status == 'open').limit(1)):
        raise ReadinessError(['open_dispute_requires_administrator'])
    current = session.get(ClassificationRevision, publication.current_revision_id) if publication.current_revision_id else None
    if current and current.input_hash == suggestion.input_hash and current.taxonomy_version_id == suggestion.taxonomy_version_id and _material_mapping(current.mappings) == _material_mapping(values):
        _verify(session, current, actor_id)
        result = _result(session, publication, current.id)
        result['note'] = note
        return _event(session, suggestion, actor_id, idempotency_key, 'review', request, result)
    revision = _revision(session, suggestion, publication, actor_id, values, blind)
    from caf_l4.questions import project_question
    snapshot = project_question(session, suggestion, revision, publication)
    _project_appearances(session, suggestion, revision, snapshot)
    publication.current_revision_id, publication.updated_at = revision.id, datetime.now(timezone.utc)
    _verify(session, revision, actor_id)
    result = _result(session, publication, revision.id)
    result['note'] = note
    return _event(session, suggestion, actor_id, idempotency_key, 'review', request, result)


def _current(session, question_id):
    initial = session.get(QuestionPublication, question_id, populate_existing=True)
    if initial and initial.current_revision_id:
        initial_revision = session.get(ClassificationRevision, initial.current_revision_id)
        _source_locks(session, session.get(SuggestionRevision, initial_revision.suggestion_revision_id))
    publication = session.scalar(select(QuestionPublication).where(QuestionPublication.question_id == question_id)
        .with_for_update().execution_options(populate_existing=True))
    if publication is None or publication.current_revision_id is None:
        raise ValueError('Question has no revisioned publication; historical verification is unknown')
    revision = session.get(ClassificationRevision, publication.current_revision_id)
    return publication, revision, session.get(SuggestionRevision, revision.suggestion_revision_id)


def verify_classification(session: Session, question_id: str, actor_id: int,
        expected_publication_revision_id: int, idempotency_key: str, withdraw: bool = False,
        expected_suggestion_revision_id: int | None = None) -> dict:
    _actor(session, actor_id)
    publication, revision, suggestion = _current(session, question_id)
    kind = 'withdraw' if withdraw else 'verify'
    request = dict(question_id=question_id, expected_publication_revision_id=expected_publication_revision_id,
        expected_suggestion_revision_id=expected_suggestion_revision_id)
    retry = _retry(session, actor_id, idempotency_key, kind, request)
    if retry is not None:
        return retry
    if revision.id != expected_publication_revision_id or expected_suggestion_revision_id not in {None, suggestion.id}:
        raise RevisionConflict('Publication changed; review its current mapping', revision.id)
    # Published historical evidence remains visible, but changed content cannot
    # receive a fresh confirmation of obsolete evidence.
    if not withdraw:
        gates = readiness(session, suggestion)
        if not gates['eligible']:
            raise ReadinessError(gates['blockers'])
        if any(mapping['outcome']=='needs_review' and not mapping['excluded'] for mapping in revision.mappings):
            raise ReadinessError(['unresolved_mapping'])
    _verify(session, revision, actor_id, not withdraw)
    return _event(session, suggestion, actor_id, idempotency_key, kind, request, _result(session, publication, revision.id))


def submit_dispute(session: Session, question_id: str, actor_id: int, expected_publication_revision_id: int,
        idempotency_key: str, reason: str, replacement_mappings: list[dict] | None = None,
        expected_suggestion_revision_id: int | None = None) -> dict:
    _actor(session, actor_id)
    if not reason.strip():
        raise ValueError('A dispute reason is required')
    publication, current, suggestion = _current(session, question_id)
    request = dict(question_id=question_id, expected_publication_revision_id=expected_publication_revision_id,
        expected_suggestion_revision_id=expected_suggestion_revision_id, reason=reason, replacement_mappings=replacement_mappings)
    retry = _retry(session, actor_id, idempotency_key, 'dispute', request)
    if retry is not None:
        return retry
    if current.id != expected_publication_revision_id:
        raise RevisionConflict('Publication changed', current.id)
    if expected_suggestion_revision_id is not None:
        suggestion = session.get(SuggestionRevision, expected_suggestion_revision_id)
        if suggestion is None or suggestion.question_id != question_id:
            raise RevisionConflict('Suggestion is for another question', current.id)
        _expect(session, suggestion, publication, expected_suggestion_revision_id, expected_publication_revision_id)
    proposed = None
    if replacement_mappings is not None:
        proposed = _revision(session, suggestion, publication, actor_id, validate_mappings(session, suggestion, replacement_mappings))
    dispute = ClassificationDispute(question_id=question_id, revision_id=current.id,
        proposed_revision_id=proposed.id if proposed else None, actor_id=actor_id, reason=reason, status='open')
    session.add(dispute)
    session.flush()
    result = _result(session, publication, proposed.id if proposed else current.id, dispute_id=dispute.id, status='open')
    result['pending'] = True
    return _event(session, suggestion, actor_id, idempotency_key, 'dispute', request, result)


def resolve_dispute(session: Session, dispute_id: int, actor_id: int, expected_publication_revision_id: int,
        idempotency_key: str, resolution: str, reason: str, replacement_mappings: list[dict] | None = None,
        expected_suggestion_revision_id: int | None = None) -> dict:
    _actor(session, actor_id, administrator=True)
    if not reason.strip() or resolution not in {'dismiss', 'replace'}:
        raise ValueError('Explicit dismiss or replace resolution and reason are required')
    dispute = session.get(ClassificationDispute, dispute_id)
    if dispute is None:
        raise ValueError('Dispute not found')
    publication, current, suggestion = _current(session, dispute.question_id)
    request = dict(dispute_id=dispute_id, expected_publication_revision_id=expected_publication_revision_id,
        expected_suggestion_revision_id=expected_suggestion_revision_id, resolution=resolution, reason=reason, replacement_mappings=replacement_mappings)
    retry = _retry(session, actor_id, idempotency_key, 'resolve', request)
    if retry is not None:
        return retry
    if current.id != expected_publication_revision_id or dispute.status != 'open':
        raise RevisionConflict('Publication or dispute changed', current.id)
    if expected_suggestion_revision_id is not None:
        suggestion = session.get(SuggestionRevision, expected_suggestion_revision_id)
    if suggestion is None or suggestion.question_id != dispute.question_id:
        raise ValueError('Suggestion does not belong to the disputed question')
    if expected_suggestion_revision_id is not None and resolution == 'replace':
        _expect(session, suggestion, publication, expected_suggestion_revision_id, expected_publication_revision_id)
    if resolution == 'dismiss' and expected_suggestion_revision_id not in {None, current.suggestion_revision_id}:
        raise RevisionConflict('Dispute retention must refer to the published suggestion evidence', current.id)
    if resolution == 'replace':
        _expect(session, suggestion, publication, suggestion.id, expected_publication_revision_id)
        gates = readiness(session, suggestion)
        if not gates['eligible']:
            raise ReadinessError(gates['blockers'])
        if replacement_mappings is None:
            raise ValueError('Explicit complete replacement mapping is required')
        values = validate_mappings(session, suggestion, replacement_mappings)
        if any(m['outcome'] == 'needs_review' and not m['excluded'] for m in values):
            raise ReadinessError(['unresolved_mapping'])
        replacement = _revision(session, suggestion, publication, actor_id, values)
        from caf_l4.questions import project_question
        snapshot = project_question(session, suggestion, replacement, publication)
        _project_appearances(session, suggestion, replacement, snapshot)
        publication.current_revision_id, publication.updated_at = replacement.id, datetime.now(timezone.utc)
        dispute.proposed_revision_id = replacement.id
        _verify(session, replacement, actor_id)
    dispute.status, dispute.resolved_by, dispute.resolution_reason = ('replaced' if resolution == 'replace' else 'dismissed'), actor_id, reason
    session.flush()
    return _event(session, suggestion, actor_id, idempotency_key, 'resolve', request,
        _result(session, publication, publication.current_revision_id, dispute_id=dispute.id, status=dispute.status))


def history(session: Session, question_id: str) -> list[dict]:
    publication = session.get(QuestionPublication, question_id)
    result = []
    for revision, suggestion in session.execute(select(ClassificationRevision, SuggestionRevision).join(
        SuggestionRevision, SuggestionRevision.id == ClassificationRevision.suggestion_revision_id).where(
        ClassificationRevision.question_id == question_id).order_by(ClassificationRevision.id.desc())):
        event = session.scalar(select(ClassificationEvent).where(ClassificationEvent.revision_id == revision.id,
            ClassificationEvent.kind == 'review').limit(1))
        published = session.scalar(select(ClassificationEvent.id).where(ClassificationEvent.revision_id == revision.id,
            ClassificationEvent.kind.in_(['review', 'resolve'])).limit(1))
        if not published and suggestion.provenance.get('baseline_release_id'):
            from caf_db.models.questions import PublishedQuestion
            published = session.get(PublishedQuestion, revision.id) is not None
        is_benchmark = bool(event and event.payload.get('status') == 'benchmark')
        result.append(dict(id=revision.id, suggestion_revision_id=suggestion.id, document_id=suggestion.document_id,
            question_id=question_id, mappings=revision.mappings, actor_id=revision.actor_id, created_at=revision.created_at,
            status='benchmark' if is_benchmark else 'current' if publication and publication.current_revision_id == revision.id else 'prior' if published else 'pending',
            verification_count=verification_count(session, revision.id), note=event.payload.get('note') if event else None))
    return result
