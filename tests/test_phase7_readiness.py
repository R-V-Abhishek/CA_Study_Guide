"""Readiness attestations use isolated reviewed evidence, never live approvals."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from caf_db.engine import get_engine
from caf_db.models.extraction import ExtractionRevision, ExtractionReview
from caf_db.models.ingest import Document, DiscoveredLink
from caf_db.models.intel import AttemptTaxonomyBinding, CorpusCoverage, ReviewedPrior, ScoreRun, SubtopicScore
from caf_db.models.ops import Event
from caf_db.models.taxonomy import NodeSourceSpan, TextbookArtifact
from caf_contracts.readiness import BindingWrite, InventoryWrite, PriorWrite, ReadinessSummary
from caf_l5.readiness import digest, snapshot, write_readiness, readiness_summary, ReadinessConflict
from caf_l5.scoring import recompute_scores
from test_phase5_publication import suggestion
from test_phase6_intelligence import manifest, reviewed_context


def binding_body(session, suggestion, target, **changes):
    row = session.get(AttemptTaxonomyBinding, (target, suggestion.taxonomy_version_id))
    span = session.scalar(sa.select(NodeSourceSpan).where(NodeSourceSpan.taxonomy_version_id == suggestion.taxonomy_version_id))
    artifact = session.get(TextbookArtifact, (suggestion.taxonomy_version_id, span.artifact_id))
    return BindingWrite.model_validate(dict(taxonomy_version_id=suggestion.taxonomy_version_id,
        target_attempt_id=target, action='review', expected_hash=digest(snapshot(row)),
        idempotency_key=str(uuid4()), evidence='Compared the approved edition applicability and release.',
        source_evidence=[dict(kind='textbook_span', span_id=span.id, sha256=artifact.sha256)], **changes))


def approved_document_evidence(session, suggestion, *, weightage=False):
    revision = session.get(ExtractionRevision, suggestion.extraction_revision_id)
    document = session.get(Document, revision.document_id)
    document.provenance_status = 'verified'
    if weightage:
        document.doc_type_id = 'weightage'
        document.course_level = 'final'
    session.add(ExtractionReview(revision_id=revision.id, actor_id=9, content_digest=revision.content_digest,
        dimension='metadata', status='passed', note='Compared exact official pages and metadata.'))
    if session.scalar(sa.select(DiscoveredLink).where(DiscoveredLink.document_id == document.id)) is None:
        session.add(DiscoveredLink(document_id=document.id, url='https://resource.cdn.icai.org/readiness-fixture.pdf',
                                  link_status='downloaded', inferred={}))
    session.commit()
    return dict(kind='document_revision', revision_id=revision.id, content_digest=revision.content_digest,
                pdf_page_start=1, pdf_page_end=1)


def test_summary_is_typed_dependency_ordered_and_unknown_stays_unknown(session, reviewed_context):
    suggestion, target = reviewed_context
    result = ReadinessSummary.model_validate(readiness_summary(session, target, suggestion.taxonomy_version_id))
    assert result.papers and result.bindings[0].reviewed_by == 9
    assert result.tasks and [t.stage for t in result.tasks] == sorted(t.stage for t in result.tasks)
    assert all(p.expected_slots is None for p in result.papers)
    assert any(t.blocker == 'expected_inventory_unknown' for t in result.tasks)
    filtered = readiness_summary(session, target, suggestion.taxonomy_version_id,
        's2023.P1', blocker_type='official_prior_unreviewed')
    assert len(filtered['papers']) == 1
    assert all(t['blocker'] == 'official_prior_unreviewed' for t in filtered['tasks'])


def test_administrator_only_and_actor_cannot_be_supplied(session, reviewed_context, authenticated_client):
    suggestion, target = reviewed_context
    body = binding_body(session, suggestion, target).model_dump(mode='json')
    client = authenticated_client(1, target=target)
    assert client.get('/api/v1/admin/readiness').status_code == 403
    assert client.put('/api/v1/admin/readiness/bindings', json=body).status_code == 403
    admin = authenticated_client(9, role='administrator', target=target)
    response = admin.get('/api/v1/admin/readiness', params={'target_attempt_id':target,
        'taxonomy_version_id':suggestion.taxonomy_version_id})
    assert response.status_code == 200, response.text
    assert admin.put('/api/v1/admin/readiness/bindings', json={**body, 'actor_id':1}).status_code == 422


def test_binding_replay_conflict_audit_and_transactional_invalidation(session, reviewed_context):
    suggestion, target = reviewed_context
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    body = binding_body(session, suggestion, target).model_copy(update={'action':'withdraw'})
    first = write_readiness(session, body, 9, 'binding')
    session.commit()
    replay = write_readiness(session, body, 9, 'binding')
    session.commit()
    assert replay == first
    assert session.scalar(sa.select(sa.func.count(Event.id)).where(Event.code == 'readiness_decision')) == 1
    session.refresh(run)
    assert first['corpus_generation'] > run.corpus_generation
    assert first['actor_id'] == 9
    with pytest.raises(ReadinessConflict):
        write_readiness(session, body.model_copy(update={'evidence':'Different evidence under the same key'}), 9, 'binding')
    session.rollback()
    stale = body.model_copy(update={'expected_hash':digest(None), 'idempotency_key':str(uuid4())})
    with pytest.raises(ReadinessConflict):
        write_readiness(session, stale, 9, 'binding')
    session.rollback()


def test_binding_rejects_unapproved_source(session, reviewed_context):
    suggestion, target = reviewed_context
    body = binding_body(session, suggestion, target)
    span = session.get(NodeSourceSpan, body.source_evidence[0].span_id)
    span.review_status = 'pending'
    session.commit()
    with pytest.raises(ValueError, match='Approved'):
        write_readiness(session, body, 9, 'binding')
    session.rollback()


def test_inventory_unknown_and_source_family_validation(session, reviewed_context):
    suggestion, _ = reviewed_context
    source = approved_document_evidence(session, suggestion)
    body = InventoryWrite(taxonomy_version_id=suggestion.taxonomy_version_id, paper_id='s2023.P1',
        attempt_id='2026-05', source_family='model', expected_slots=None,
        expected_hash=digest(None), idempotency_key=str(uuid4()), evidence='Inventory is not yet known.',
        source_evidence=[source])
    write_readiness(session, body, 9, 'inventory')
    session.commit()
    row = session.get(CorpusCoverage, (suggestion.taxonomy_version_id,'s2023.P1','2026-05','model'))
    assert row.expected_slots is None and not row.inventory_reviewed and not row.official_scope_confirmed
    wrong = body.model_copy(update={'source_family':'mock', 'idempotency_key':str(uuid4())})
    with pytest.raises(ValueError, match='another source family'):
        write_readiness(session, wrong, 9, 'inventory')
    session.rollback()


def test_prior_source_contract_drives_real_scoring_and_wrong_document_rejected(session, reviewed_context):
    suggestion, target = reviewed_context
    source = approved_document_evidence(session, suggestion)
    node = suggestion.mappings[0]['primary_node_id']
    body = PriorWrite(taxonomy_version_id=suggestion.taxonomy_version_id, node_id=node, value=.4,
        expected_hash=digest(None), idempotency_key=str(uuid4()), evidence='Official prescribed weightage mapping.',
        source_evidence=[source])
    with pytest.raises(ValueError, match='weightage document'):
        write_readiness(session, body, 9, 'prior')
    session.rollback()
    source = approved_document_evidence(session, suggestion, weightage=True)
    body = body.model_copy(update={'source_evidence':PriorWrite.model_validate({**body.model_dump(), 'source_evidence':[source]}).source_evidence})
    write_readiness(session, body, 9, 'prior')
    session.commit()
    prior = session.get(ReviewedPrior,(suggestion.taxonomy_version_id,node))
    assert prior.source['kind'] == 'official_weightage'
    run = recompute_scores(session,target,taxonomy_version_id=suggestion.taxonomy_version_id)
    assert session.get(SubtopicScore,(run.id,node)).weight_prior == pytest.approx(.4)


def test_concurrent_same_request_has_one_durable_receipt(session, reviewed_context):
    suggestion, target = reviewed_context
    body = binding_body(session,suggestion,target)
    def execute():
        with Session(get_engine('operations')) as db:
            result = write_readiness(db,body,9,'binding')
            db.commit()
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(),range(2)))
    assert results[0] == results[1]
    assert session.scalar(sa.select(sa.func.count(Event.id)).where(Event.code == 'readiness_decision')) == 1


def test_student_context_block_duration_marks_and_tree_status_are_account_scoped(
    session, reviewed_context, authenticated_client,
):
    from caf_db.models.app import Progress, Settings
    suggestion, target = reviewed_context
    session.add(Settings(user_id=2,target_attempt_id=target,selected_paper_ids=['s2023.P1']))
    session.commit()
    first = authenticated_client(1, target=target)
    second = authenticated_client(2, target=target)
    node = suggestion.mappings[0]['primary_node_id']
    session.add(Progress(user_id=1,node_id=node,status='in_progress'))
    session.commit()
    for client, expected in ((first,'in_progress'),(second,'not_started')):
        result = client.get('/api/v1/papers/s2023.P1/tree')
        assert result.status_code == 200, result.text
        def leaves(nodes):
            for item in nodes:
                if item['id'] == node:
                    yield item
                yield from leaves(item['children'])
        assert list(leaves(result.json()['hierarchy']))[0]['status'] == expected
    papers = first.get('/api/v1/papers').json()
    assert all(p['context']['target_attempt_id'] == target for p in papers)
    assert all(p['weighted_coverage_pct'] is None for p in papers)
    settings_minutes = session.get(Settings,1).minutes_per_subtopic
    plan = first.get('/api/v1/plan',params={'minutes':17,'hours':1}).json()
    assert plan['items'] and plan['minutes_per_subtopic'] == 17
    assert plan['allocated_minutes'] == len(plan['items']) * 17
    assert first.get('/api/v1/plan',params={'minutes':0}).status_code == 422
    session.expire_all()
    assert session.get(Settings,1).minutes_per_subtopic == settings_minutes
    summaries = first.get('/api/v1/questions').json()['items']
    assert summaries and summaries[0]['marks'] is not None


def test_failed_readiness_mutation_retains_scope_and_no_audit(session, reviewed_context, authenticated_client):
    suggestion, target = reviewed_context
    client = authenticated_client(9, role='administrator', target=target)
    body = binding_body(session,suggestion,target).model_dump(mode='json')
    body['expected_hash'] = digest(None)
    response = client.put('/api/v1/admin/readiness/bindings',json=body)
    assert response.status_code == 409, response.text
    assert response.json()['detail']['current_hash'] != digest(None)
    assert response.json()['detail']['current']['target_attempt_id'] == target
    assert session.scalar(sa.select(sa.func.count(Event.id)).where(Event.code == 'readiness_decision')) == 0
    row = session.get(AttemptTaxonomyBinding,(target,suggestion.taxonomy_version_id))
    assert row.status == 'reviewed'
