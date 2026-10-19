"""Conservative readiness and audited source-bound administrative decisions.

The existing corpus invalidation triggers run in the same transaction as each
write. Generic operational events hold the durable decision and replay receipt;
transaction locks serialize readiness edits, including creation of absent rows.
No request accepts an actor identity or a derived completeness flag.
"""
import hashlib
import json
from urllib.parse import urlparse
import sqlalchemy as sa
from sqlalchemy.orm import Session
from caf_contracts.readiness import BindingWrite, InventoryWrite, PriorWrite
from caf_db.models.intel import AttemptTaxonomyBinding, CorpusCoverage, ReviewedPrior, ScoreRun
from caf_db.models.ops import Event
from caf_db.models.ref import Attempt, Paper
from caf_db.models.taxonomy import TaxonomyRelease, TaxonomyMember, TextbookArtifact, NodeSourceSpan
from caf_db.models.extraction import ExtractionRevision, ExtractionReview
from caf_db.models.ingest import Document, DiscoveredLink
from caf_db.models.questions import PublishedQuestion, QuestionOccurrence
from caf_db.models.classification import QuestionPublication, ClassificationDispute
from caf_l2.revisions import family, reviewed_quality, extraction_ready
from caf_l0.releases import eligible_candidates
from caf_l5.config import load_scoring_config
from caf_l5.context import corpus_generation
from caf_l5.jobs import enqueue_recompute
from caf_l5.scoring import coverage_eligibility, publication_exclusions

STAGES = {
    1: 'Textbook edition/source', 2: 'Heading taxonomy and descriptors',
    3: 'Applicability and attempt binding', 4: 'Source metadata/ranges',
    5: 'Extraction and answer pairing', 6: 'Classification/publication',
    7: 'Expected inventory and coverage', 8: 'Official priors and scoring freshness',
}
AUDIT_CODE = 'readiness_decision'


class ReadinessConflict(ValueError):
    def __init__(self, current_hash: str, current: dict | None):
        super().__init__('Readiness evidence changed; compare the current record before submitting again')
        self.current_hash = current_hash
        self.current = current


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode()).hexdigest()


def snapshot(row) -> dict | None:
    if row is None:
        return None
    # Table contracts define all columns; no shape guessing or private fields.
    return {column.name: row.__dict__[column.name] for column in row.__table__.columns}


def record(row, **identity):
    value = snapshot(row)
    return {**identity, **(value or {}), 'expected_hash': digest(value)}


def official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ''
    return parsed.scheme == 'https' and (host == 'icai.org' or host.endswith('.icai.org'))


def validate_sources(session: Session, sources, taxonomy: int, *, paper: str | None = None,
                     target_attempt: str | None = None) -> list[dict]:
    validated = []
    for source in sources:
        if source.kind == 'textbook_span':
            span = session.scalar(sa.select(NodeSourceSpan).where(NodeSourceSpan.id == source.span_id)
                                  .with_for_update().execution_options(populate_existing=True))
            if span is None or span.taxonomy_version_id != taxonomy:
                raise ValueError('Source span does not belong to this taxonomy')
            artifact = session.scalar(sa.select(TextbookArtifact).where(
                TextbookArtifact.taxonomy_version_id == taxonomy, TextbookArtifact.id == span.artifact_id)
                .with_for_update().execution_options(populate_existing=True))
            if artifact.sha256 != source.sha256:
                current = {'span_id': span.id, 'sha256': artifact.sha256}
                raise ReadinessConflict(digest(current), current)
            if (span.review_status != 'reviewed' or span.reviewed_by is None or
                    artifact.availability != 'verified' or artifact.sha256 != source.sha256 or
                    not official_url(artifact.metadata_json['download_url'])):
                raise ValueError('Approved, verified official source evidence is required')
            if paper and artifact.paper_id != paper:
                raise ValueError('Source evidence belongs to another paper')
            if target_attempt and artifact.metadata_json['target_applicability'] != 'verified':
                raise ValueError('Source has no reviewed applicability to the target attempt')
        else:
            revision = session.scalar(sa.select(ExtractionRevision).where(
                ExtractionRevision.id == source.revision_id).with_for_update()
                .execution_options(populate_existing=True))
            if revision is None:
                raise ValueError('Approved current document revision is required')
            if revision.content_digest != source.content_digest or revision.status != 'current':
                current = {'revision_id': revision.id, 'content_digest': revision.content_digest,
                           'status': revision.status}
                raise ReadinessConflict(digest(current), current)
            document = session.scalar(sa.select(Document).where(Document.id == revision.document_id)
                .with_for_update().execution_options(populate_existing=True))
            urls = list(session.scalars(sa.select(DiscoveredLink.url).where(
                DiscoveredLink.document_id == document.id)))
            reviews = list(session.scalars(sa.select(ExtractionReview).where(
                ExtractionReview.revision_id == revision.id,
                ExtractionReview.content_digest == revision.content_digest,
                ExtractionReview.dimension == 'metadata').order_by(ExtractionReview.id)))
            if (document.current_revision_id != revision.id or document.catalog_status != 'confirmed' or
                    document.provenance_status != 'verified' or document.superseded or
                    not any(official_url(url) for url in urls) or not reviews or reviews[-1].status != 'passed'):
                raise ValueError('Approved, verified official document metadata is required')
            if source.pdf_page_end > (document.page_count or 0):
                raise ValueError('Source page range exceeds the approved artifact')
            ranges = document.paper_page_ranges or [{'paper_id': document.paper_id,
                         'page_start': 1, 'page_end': document.page_count}]
            if paper and not any(r['paper_id'] == paper and r['page_start'] <= source.pdf_page_start
                                 and r['page_end'] >= source.pdf_page_end for r in ranges):
                raise ValueError('Source pages do not cover this paper')
            if target_attempt and document.attempt_id != target_attempt:
                raise ValueError('Document source is not bound to this attempt')
        validated.append(source.model_dump(mode='json'))
    return validated


def scoped_documents(session, paper_id, attempt_id, source_family):
    # Historical source inventory used past_exam; assembled roots use examination.
    canonical = {'past_exam': 'examination', 'QP': 'examination'}.get(source_family, source_family)
    documents = list(session.scalars(sa.select(Document).where(Document.attempt_id == attempt_id,
        Document.superseded.is_(False)).order_by(Document.id)))
    return [d for d in documents if family(d.doc_type_id) == canonical and
            (d.paper_id == paper_id or any(r['paper_id'] == paper_id for r in d.paper_page_ranges)) and
            d.doc_type_id not in {'suggested_answer', 'mtp_answer', 'model_answer'}]


def derive_coverage(session, row):
    documents = scoped_documents(session, row.paper_id, row.attempt_id, row.source_family)
    revisions = [session.get(ExtractionRevision, d.current_revision_id) for d in documents if d.current_revision_id]
    ready = bool(documents) and len(revisions) == len(documents) and all(
        extraction_ready(session, r) for r in revisions)
    qualities = [reviewed_quality(session, r) for r in revisions]
    publications = session.execute(sa.select(PublishedQuestion, QuestionOccurrence).join(
        QuestionPublication, QuestionPublication.current_snapshot_id == PublishedQuestion.id).join(
        QuestionOccurrence, QuestionOccurrence.id == PublishedQuestion.occurrence_id).where(
        PublishedQuestion.taxonomy_version_id == row.taxonomy_version_id,
        QuestionOccurrence.paper_id == row.paper_id, QuestionOccurrence.attempt_id == row.attempt_id)).all()
    revision_ids = {r.id for r in revisions}
    bound = [(p, o) for p, o in publications if p.extraction_revision_id in revision_ids]
    roots = [q for r in revisions for q in r.questions if q['paper_id'] == row.paper_id]
    row.discovered_count = len(documents)
    row.acquired_count = sum(d.provenance_status == 'verified' for d in documents)
    row.metadata_reviewed = bool(documents) and all(d.catalog_status == 'confirmed' for d in documents)
    row.extraction_reviewed = ready
    row.pairing_reviewed = bool(qualities) and all(q['pairing'] in {'passed', 'not_applicable'} for q in qualities)
    row.official_scope_confirmed = row.inventory_reviewed and row.expected_slots is not None
    row.gradable_regions_accounted = ready and bool(roots) and all(q['question_status'] == 'complete' for q in roots)
    row.reviewed_roots = len(roots) if ready else 0
    row.reviewed_parts = sum(len(p.mappings) for p, _ in bound)
    row.published_roots = len(bound)
    row.labels_complete = bool(roots) and len(bound) == len(roots) and all(not publication_exclusions(p) for p, _ in bound)
    row.occurrence_resolved = bool(bound) and all(o.identity_status == 'confirmed' for _, o in bound)
    row.missing_answers = sum(p.content['answer_status'] == 'missing' for p, _ in bound)
    # Preserve acquisition/source blockers. Only this decision's pending inventory
    # markers can be resolved by an inventory attestation.
    row.blockers = [b for b in row.blockers if b not in {'expected_inventory_unreviewed', 'official_scope_review_pending'}]


def write_readiness(session: Session, body: BindingWrite | InventoryWrite | PriorWrite,
                    actor_id: int, kind: str) -> dict:
    session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended('caf:readiness', 0))"))
    request_hash = digest({'kind': kind, 'body': body.model_dump(mode='json')})
    previous = session.scalar(sa.select(Event).where(Event.code == AUDIT_CODE,
        Event.context['actor_id'].as_integer() == actor_id,
        Event.context['idempotency_key'].as_string() == body.idempotency_key))
    if previous:
        if previous.context['request_hash'] != request_hash:
            raise ReadinessConflict(previous.context['result']['expected_hash'], previous.context['after'])
        return previous.context['result']
    release = session.scalar(sa.select(TaxonomyRelease).where(
        TaxonomyRelease.taxonomy_version_id == body.taxonomy_version_id).with_for_update())
    if release is None:
        raise ValueError('Unknown taxonomy release')
    if kind == 'binding':
        key = (body.target_attempt_id, body.taxonomy_version_id)
        row = session.get(AttemptTaxonomyBinding, key)
        record_id = ':'.join(map(str, key))
    elif kind == 'inventory':
        key = (body.taxonomy_version_id, body.paper_id, body.attempt_id, body.source_family)
        row = session.get(CorpusCoverage, key)
        record_id = ':'.join(map(str, key))
    else:
        key = (body.taxonomy_version_id, body.node_id)
        row = session.get(ReviewedPrior, key)
        record_id = ':'.join(map(str, key))
    if row:
        session.refresh(row, with_for_update=True)
    before = snapshot(row)
    if digest(before) != body.expected_hash:
        raise ReadinessConflict(digest(before), before)
    if kind == 'binding':
        if session.get(Attempt, body.target_attempt_id) is None:
            raise ValueError('Unknown target attempt')
        sources = validate_sources(session, body.source_evidence, body.taxonomy_version_id,
                                  target_attempt=body.target_attempt_id if body.action == 'review' else None)
        if body.action == 'review':
            if release.status not in {'approved', 'active', 'archived'} or release.approved_by is None:
                raise ValueError('Taxonomy release must be approved before binding review')
            if release.target_attempt != body.target_attempt_id:
                raise ValueError('Taxonomy release applicability does not cover this target attempt')
        if row is None:
            row = AttemptTaxonomyBinding(target_attempt_id=body.target_attempt_id,
                taxonomy_version_id=body.taxonomy_version_id,
                scoring_config=load_scoring_config().model_dump(mode='json'))
            session.add(row)
        row.status = 'reviewed' if body.action == 'review' else 'pending'
        row.reviewed_by = actor_id if body.action == 'review' else None
    elif kind == 'inventory':
        if session.get(Paper, body.paper_id) is None or session.get(Attempt, body.attempt_id) is None:
            raise ValueError('Unknown paper or inventory attempt')
        if any(s.kind != 'document_revision' for s in body.source_evidence):
            raise ValueError('Expected inventory requires approved document evidence')
        sources = validate_sources(session, body.source_evidence, body.taxonomy_version_id,
                                  paper=body.paper_id, target_attempt=body.attempt_id)
        canonical = {'past_exam': 'examination', 'QP': 'examination'}.get(body.source_family, body.source_family)
        for source in body.source_evidence:
            revision = session.get(ExtractionRevision, source.revision_id)
            document = session.get(Document, revision.document_id)
            if family(document.doc_type_id) != canonical:
                raise ValueError('Inventory source evidence belongs to another source family')
        if row is None:
            row = CorpusCoverage(taxonomy_version_id=body.taxonomy_version_id, paper_id=body.paper_id,
                attempt_id=body.attempt_id, source_family=body.source_family, blockers=[])
            session.add(row)
        row.expected_slots = body.expected_slots
        row.inventory_reviewed = body.expected_slots is not None
        derive_coverage(session, row)
    else:
        member = session.get(TaxonomyMember, key)
        if member is None or member.level != 'subtopic':
            raise ValueError('Prior must refer to a subtopic in this taxonomy')
        if any(s.kind != 'document_revision' for s in body.source_evidence):
            raise ValueError('Official priors require approved document page evidence')
        sources = validate_sources(session, body.source_evidence, body.taxonomy_version_id, paper=member.paper_id)
        prior_sources = []
        for source in body.source_evidence:
            revision = session.get(ExtractionRevision, source.revision_id)
            document = session.get(Document, revision.document_id)
            if document.doc_type_id != 'weightage' or document.course_level != 'final':
                raise ValueError('Official prior evidence must be an official Final weightage document')
            urls = list(session.scalars(sa.select(DiscoveredLink.url).where(DiscoveredLink.document_id == document.id)))
            official = next((u for u in urls if urlparse(u).scheme == 'https' and
                urlparse(u).hostname in {'www.icai.org', 'icai.org', 'resource.cdn.icai.org'}), None)
            if official is None:
                raise ValueError('Official weightage requires an approved HTTPS ICAI source URL')
            prior_sources.append((document.sha256, official))
        if row is None:
            row = ReviewedPrior(taxonomy_version_id=body.taxonomy_version_id, node_id=body.node_id)
            session.add(row)
        row.value, row.reviewed_by = body.value, actor_id
        row.source = {'evidence': body.evidence, 'source_evidence': sources,
                     'kind': 'official_weightage', 'taxonomy_version_id': body.taxonomy_version_id,
                     'document_sha256': prior_sources[0][0], 'official_url': prior_sources[0][1]}
    session.flush()  # durable invalidation triggers execute before receipt creation
    if kind == 'binding' and body.action == 'review':
        enqueue_recompute(session, body.target_attempt_id, body.taxonomy_version_id, commit=False)
    after = snapshot(row)
    audit = Event(level='info', code=AUDIT_CODE, message='Administrator readiness decision', context={
        'actor_id': actor_id, 'kind': kind, 'record_id': record_id, 'taxonomy_version_id': body.taxonomy_version_id,
        'evidence': body.evidence, 'source_evidence': sources, 'idempotency_key': body.idempotency_key,
        'request_hash': request_hash, 'before': before, 'after': after})
    session.add(audit)
    session.flush()
    result = {'record_id': record_id, 'expected_hash': digest(after), 'audit_id': audit.id,
              'actor_id': actor_id, 'corpus_generation': corpus_generation(session)}
    audit.context = {**audit.context, 'result': result}
    return result


def readiness_summary(session: Session, target_attempt_id: str, taxonomy_version_id: int | None = None,
                      paper_id: str | None = None, source_family: str | None = None,
                      blocker_type: str | None = None) -> dict:
    if session.get(Attempt, target_attempt_id) is None:
        raise ValueError('Unknown target attempt')
    release_query = sa.select(TaxonomyRelease)
    if taxonomy_version_id is not None:
        release_query = release_query.where(TaxonomyRelease.taxonomy_version_id == taxonomy_version_id)
    else:
        release_query = release_query.where(TaxonomyRelease.target_attempt == target_attempt_id)
    release = session.scalar(release_query.order_by(TaxonomyRelease.taxonomy_version_id.desc()).limit(1))
    if taxonomy_version_id is not None and release is None:
        raise ValueError('Unknown taxonomy release')
    version = release.taxonomy_version_id if release else None
    papers = list(session.scalars(sa.select(Paper).where(Paper.is_current.is_(True)).order_by(Paper.code)))
    if paper_id:
        papers = [p for p in papers if p.id == paper_id]
    tasks, inventories, priors, bindings, sources = [], [], [], [], []

    def task(paper, stage, blocker, evidence, href, affected=(), role='administrator'):
        tasks.append({'id': f'{paper}:{stage}:{blocker}:{len(tasks)}', 'paper_id': paper,
            'stage': stage, 'stage_name': STAGES[stage], 'blocker': blocker,
            'evidence': evidence, 'required_role': role,
            'next_action': {'label': 'Review evidence', 'href': href},
            'affected_records': list(affected)})

    if release:
        binding = session.get(AttemptTaxonomyBinding, (target_attempt_id, version))
        bindings.append(record(binding, target_attempt_id=target_attempt_id, taxonomy_version_id=version,
                               status='pending', reviewed_by=None))
        if binding is None or binding.status != 'reviewed' or binding.reviewed_by is None:
            task(None, 3, 'attempt_binding_unreviewed',
                 ['The target attempt has no reviewed taxonomy binding.'], '/curator/readiness',
                 [{'kind': 'attempt_binding', 'id': f'{target_attempt_id}:{version}',
                   'revision': digest(snapshot(binding))}])
        artifacts = list(session.scalars(sa.select(TextbookArtifact).where(
            TextbookArtifact.taxonomy_version_id == version)))
        spans = list(session.scalars(sa.select(NodeSourceSpan).where(NodeSourceSpan.taxonomy_version_id == version)))
        eligible = {n.node_id for n in eligible_candidates(session, version)}
        members = list(session.scalars(sa.select(TaxonomyMember).where(TaxonomyMember.taxonomy_version_id == version)))
        for gap in release.manifest.get('source_gaps', []):
            scope = gap['paper_id'] if gap['paper_id'] != 'all' else None
            if paper_id and scope not in {None, paper_id}:
                continue
            stage = 1 if scope == 's2023.P5' else (3 if scope == 's2023.P6' else 2)
            task(scope, stage, 'source_manifest_gap', [gap['reason']], '/curator/textbooks',
                 [{'kind': 'taxonomy_release', 'id': release.version_id, 'revision': release.manifest_hash}])
        for span in spans:
            artifact = next((a for a in artifacts if a.id == span.artifact_id), None)
            if artifact and artifact.sha256 and artifact.availability == 'verified' and span.review_status == 'reviewed' and span.reviewed_by:
                sources.append({'kind': 'textbook_span', 'span_id': span.id, 'sha256': artifact.sha256})
    else:
        artifacts, spans, members, eligible = [], [], [], set()
        task(None, 2, 'taxonomy_release_missing', ['No textbook release exists for this target attempt.'], '/curator/textbooks')

    coverage_query = sa.select(CorpusCoverage).where(CorpusCoverage.taxonomy_version_id == version)
    if source_family:
        coverage_query = coverage_query.where(CorpusCoverage.source_family == source_family)
    coverage = list(session.scalars(coverage_query.order_by(CorpusCoverage.paper_id,
                      CorpusCoverage.attempt_id, CorpusCoverage.source_family))) if release else []
    for row in coverage:
        if paper_id and row.paper_id != paper_id:
            continue
        inventories.append(record(row))
        _, blockers = coverage_eligibility(row)
        for blocker in blockers:
            stage = {'sources_not_acquired': 4, 'metadata_unreviewed': 4,
                     'extraction_unreviewed': 5, 'pairing_unreviewed': 5,
                     'gradable_regions_unaccounted': 5, 'labels_incomplete': 6,
                     'occurrence_identity_unresolved': 6, 'unpublished_roots': 6}.get(blocker, 7)
            task(row.paper_id, stage, blocker,
                 [f'{row.attempt_id} / {row.source_family}: expected inventory ' +
                  ('unknown' if row.expected_slots is None else str(row.expected_slots))], '/curator/readiness',
                 [{'kind': 'corpus_coverage', 'id': f'{version}:{row.paper_id}:{row.attempt_id}:{row.source_family}',
                   'revision': digest(snapshot(row))}])

    summaries = []
    for paper in papers:
        paper_artifacts = [a for a in artifacts if a.paper_id == paper.id]
        for artifact in paper_artifacts:
            unresolved = artifact.availability != 'verified' or artifact.metadata_json['target_applicability'] != 'verified' or artifact.metadata_json['fallback']
            if unresolved:
                task(paper.id, 1, 'textbook_source_unresolved',
                     [f'{artifact.edition}: {artifact.availability}; applicability {artifact.metadata_json["target_applicability"]}',
                      'Fallback edition' if artifact.metadata_json['fallback'] else 'Prescribed edition'], '/curator/textbooks',
                     [{'kind': 'textbook_artifact', 'id': artifact.id, 'revision': artifact.sha256}])
        if not paper_artifacts:
            task(paper.id, 1, 'textbook_source_missing', ['No textbook source artifact is registered.'], '/curator/textbooks')
        paper_leaves = [n for n in members if n.paper_id == paper.id and n.level == 'subtopic']
        pending = [n for n in paper_leaves if n.node_id not in eligible]
        if not paper_leaves or pending or (release and release.status not in {'approved', 'active', 'archived'}):
            task(paper.id, 2, 'taxonomy_review_pending',
                 [f'{len(pending)} subtopics await source/descriptor eligibility.',
                  f'Release status: {release.status}' if release else 'Release unavailable'], '/curator/textbooks',
                 [{'kind': 'taxonomy_member', 'id': n.node_id, 'revision': str(version)} for n in pending], role='student reviewer; administrator activates release')
        documents = list(session.scalars(sa.select(Document).where(Document.superseded.is_(False),
            sa.or_(Document.paper_id == paper.id, Document.paper_page_ranges.contains([{'paper_id': paper.id}]))).order_by(Document.id)))
        if source_family:
            canonical = {'past_exam': 'examination', 'QP': 'examination'}.get(source_family, source_family)
            documents = [d for d in documents if family(d.doc_type_id) == canonical]
        if not documents:
            task(paper.id, 4, 'question_source_missing', ['No question artifacts match this paper/source scope.'], '/curator/catalog')
        for document in documents:
            affected = [{'kind': 'document', 'id': str(document.id), 'revision': document.sha256}]
            href = f'/curator/extraction?document_id={document.id}'
            if document.catalog_status != 'confirmed' or document.provenance_status != 'verified':
                task(paper.id, 4, 'source_metadata_unreviewed',
                     [document.title or f'Document {document.id}', f'{document.catalog_status}; {document.provenance_status}'], href, affected)
            revision = session.get(ExtractionRevision, document.current_revision_id) if document.current_revision_id else None
            if revision is None or not extraction_ready(session, revision):
                task(paper.id, 5, 'extraction_review_pending',
                     [document.title or f'Document {document.id}', 'No current revision' if revision is None else json.dumps(reviewed_quality(session, revision), sort_keys=True)], href,
                     affected + ([{'kind': 'extraction_revision', 'id': str(revision.id), 'revision': revision.content_digest}] if revision else []), role='student reviewer; administrator promotes')
            if revision:
                metadata_reviews = list(session.scalars(sa.select(ExtractionReview).where(
                    ExtractionReview.revision_id == revision.id, ExtractionReview.content_digest == revision.content_digest,
                    ExtractionReview.dimension == 'metadata').order_by(ExtractionReview.id)))
                urls = list(session.scalars(sa.select(DiscoveredLink.url).where(DiscoveredLink.document_id == document.id)))
                if metadata_reviews and metadata_reviews[-1].status == 'passed' and document.provenance_status == 'verified' and document.catalog_status == 'confirmed' and document.page_count and any(official_url(u) for u in urls):
                    sources.append({'kind': 'document_revision', 'revision_id': revision.id,
                                    'content_digest': revision.content_digest, 'pdf_page_start': 1,
                                    'pdf_page_end': document.page_count})
        count = session.scalar(sa.select(sa.func.count(PublishedQuestion.id)).join(
            QuestionPublication, QuestionPublication.current_snapshot_id == PublishedQuestion.id).join(
            QuestionOccurrence, QuestionOccurrence.id == PublishedQuestion.occurrence_id).where(
            PublishedQuestion.taxonomy_version_id == version, QuestionOccurrence.paper_id == paper.id)) or 0
        if count == 0:
            task(paper.id, 6, 'classification_unpublished', ['No reviewed question snapshots are published.'], '/curator/review', role='student reviewer')
        disputes = list(session.scalars(sa.select(ClassificationDispute).join(QuestionPublication,
            QuestionPublication.question_id == ClassificationDispute.question_id).join(Document,
            Document.id == QuestionPublication.document_id).where(ClassificationDispute.status == 'open', Document.paper_id == paper.id)))
        for dispute in disputes:
            task(paper.id, 6, 'classification_disputed', [dispute.reason], f'/curator/review?question_id={dispute.question_id}',
                 [{'kind': 'classification_dispute', 'id': str(dispute.id), 'revision': str(dispute.revision_id)}])
        paper_coverage = [c for c in coverage if c.paper_id == paper.id]
        if not paper_coverage:
            task(paper.id, 7, 'expected_inventory_unknown', ['No expected inventory has been reviewed.'], '/curator/readiness')
        for node in paper_leaves:
            prior = session.get(ReviewedPrior, (version, node.node_id))
            priors.append(record(prior, taxonomy_version_id=version, node_id=node.node_id, value=None, reviewed_by=None))
        missing_priors = [p for p in priors if p['node_id'] in {n.node_id for n in paper_leaves} and p['reviewed_by'] is None]
        if missing_priors:
            task(paper.id, 8, 'official_prior_unreviewed', [f'{len(missing_priors)} subtopics have no reviewed official prior.'], '/curator/readiness')
        summaries.append({'paper_id': paper.id, 'name': paper.name,
            'blocker_count': sum(t['paper_id'] in {None, paper.id} for t in tasks),
            'published_roots': count,
            'expected_slots': sum(c.expected_slots for c in paper_coverage)
                if paper_coverage and all(c.expected_slots is not None for c in paper_coverage) else None})
    runs = list(session.scalars(sa.select(ScoreRun).where(ScoreRun.target_attempt_id == target_attempt_id,
        ScoreRun.taxonomy_version_id == version, ScoreRun.is_current.is_(True), ScoreRun.shadow.is_(False))))
    if not runs or any(r.stale or r.corpus_generation != corpus_generation(session) for r in runs):
        task(None, 8, 'scores_unavailable_or_stale', ['No fresh current score snapshot is available.'], '/curator/system')
    history = []
    audit_query = sa.select(Event).where(Event.code == AUDIT_CODE)
    if version:
        audit_query = audit_query.where(Event.context['taxonomy_version_id'].as_integer() == version)
    for event in session.scalars(audit_query.order_by(Event.id.desc()).limit(100)):
        context = event.context
        history.append({'id': event.id, 'actor_id': context['actor_id'], 'action': context['kind'],
            'evidence': context['evidence'], 'created_at': event.at, 'record_id': context['record_id'],
            'before_hash': digest(context['before']), 'after_hash': digest(context['after'])})
    if blocker_type:
        tasks = [t for t in tasks if t['blocker'] == blocker_type]
    tasks.sort(key=lambda t: (t['stage'], t['paper_id'] or '', t['id']))
    return {'target_attempt_id': target_attempt_id, 'taxonomy_version_id': version, 'papers': summaries,
            'tasks': tasks, 'bindings': bindings, 'inventory': inventories, 'priors': priors,
            'source_evidence': sources, 'history': history}
