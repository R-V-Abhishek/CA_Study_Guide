"""Authenticated API review against the restricted curator database pool."""
from uuid import uuid4
import sqlalchemy as sa
from fastapi.testclient import TestClient
from caf_api.main import app
from caf_db.models.classification import (SuggestionRevision, ClassificationRevision,
    ClassificationVerification, ClassificationEvent, QuestionPublication)
from caf_db.models.core import Appearance
from caf_db.models.ingest import Unit
from caf_db.models.taxonomy import TaxonomyMember, TaxonomyRelease
from caf_db.models.ref import TaxonomyVersion
from test_phase5_publication import suggestion, manifest


BASE = '/api/v1/curate/classifications'


def review_body(suggestion, previous=None, key='api-review', **extra):
    return dict(expected_suggestion_revision_id=suggestion.id, expected_publication_revision_id=previous,
        idempotency_key=key, mappings=suggestion.mappings, note='Compared the complete question and available source answer', **extra)


def expectation(suggestion, publication_id, key):
    return dict(expected_suggestion_revision_id=suggestion.id,
        expected_publication_revision_id=publication_id, idempotency_key=key)


def clone(session, suggestion, *, experimental=False, mappings=None):
    row = SuggestionRevision(batch_key=str(uuid4()), input_hash=suggestion.input_hash, document_id=suggestion.document_id,
        extraction_revision_id=suggestion.extraction_revision_id, question_id=suggestion.question_id,
        taxonomy_version_id=suggestion.taxonomy_version_id, run_id=1, experimental=experimental,
        context=suggestion.context, candidates=suggestion.candidates, mappings=mappings or suggestion.mappings,
        provenance={**suggestion.provenance, 'benchmark': True})
    session.add(row)
    session.commit()
    return row


def test_authenticated_review_idempotency_revision_conflict_and_identity(session, suggestion, authenticated_client):
    client = authenticated_client(user_id=2, role='student')
    url = f'{BASE}/{suggestion.id}/review'
    forged = client.post(url, json={**review_body(suggestion), 'actor_id': 9})
    assert forged.status_code == 422
    accepted = client.post(url, json=review_body(suggestion))
    assert accepted.status_code == 200, accepted.text
    result = accepted.json()
    assert result['verification_count'] == 1
    assert client.post(url, json=review_body(suggestion)).json() == result
    current = session.get(ClassificationRevision, result['revision_id'])
    assert current.actor_id == 2
    assert session.scalar(sa.select(sa.func.count(ClassificationRevision.id))) == 1
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 1
    stale = client.post(url, json=review_body(suggestion, key='stale-new-click'))
    assert stale.status_code == 409
    assert stale.json()['detail']['code'] == 'stale_revision'
    assert stale.json()['detail']['current_revision_id'] == result['revision_id']
    reused = client.post(url, json={**review_body(suggestion), 'note': 'Different request under reused key'})
    assert reused.status_code == 409
    assert session.scalar(sa.select(sa.func.count(ClassificationEvent.id))) == 1
    unauthenticated = TestClient(app)
    unauthenticated.cookies.clear()
    assert unauthenticated.get(BASE).status_code == 401
    assert unauthenticated.get(f'{BASE}/questions/{suggestion.question_id}/history').status_code == 401


def test_draft_readiness_errors_and_blind_annotation_without_publication(session, suggestion, authenticated_client):
    draft = clone(session, suggestion, experimental=True)
    client = authenticated_client(user_id=2, role='student')
    rows = client.get(BASE, params={'experimental': True, 'blind': True}).json()
    assert len(rows) == 1
    row = rows[0]
    assert row['suggestion_revision_id'] == draft.id
    assert row['question']['common_stem'] == draft.context['common_stem']
    assert row['question']['answer_status'] == draft.context['answer_status']
    assert row['provenance'] == {} and row['run_id'] is None
    assert all(mapping['outcome'] == 'needs_review' and mapping['primary_node_id'] is None and mapping['evidence'] == {} for mapping in row['mappings'])
    assert not row['publication_ready']
    rejected = client.post(f'{BASE}/{draft.id}/review', json=review_body(draft))
    assert rejected.status_code == 422
    detail = rejected.json()['detail']
    assert detail['code'] == 'readiness_failed' and 'experimental_suggestion' in detail['blockers']
    body = review_body(draft, key='blind-annotation', blind=True)
    unresolved = [{**mapping, 'outcome': 'needs_review', 'primary_node_id': None,
        'secondary_node_ids': [], 'evidence': {'note': 'Independent reviewer needs source context'}} for mapping in draft.mappings]
    body['mappings'] = unresolved
    accepted = client.post(f'{BASE}/{draft.id}/review', json=body)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'benchmark' and accepted.json()['pending']
    assert accepted.json()['current_revision_id'] is None and accepted.json()['verification_count'] == 0
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 0
    assert session.scalar(sa.select(sa.func.count(Appearance.id))) == 0
    assert session.get(QuestionPublication, draft.question_id).current_revision_id is None
    history = client.get(f'{BASE}/questions/{draft.question_id}/history')
    assert history.status_code == 200, history.text
    assert history.json()[0]['status'] == 'benchmark'
    assert history.json()[0]['mappings'] == unresolved
    verification = client.post(f'{BASE}/questions/{draft.question_id}/verify', json=expectation(draft, accepted.json()['revision_id'], 'draft-verify'))
    assert verification.status_code == 422


def test_latest_suggestion_keeps_frozen_published_mapping_and_verification_binding(session, suggestion, authenticated_client):
    initial = authenticated_client(user_id=1, role='student')
    student = authenticated_client(user_id=2, role='student')
    published = initial.post(f'{BASE}/{suggestion.id}/review', json=review_body(suggestion)).json()
    assert published['verification_count'] == 1
    newer_mappings = [{**mapping, 'outcome': 'none_fits', 'primary_node_id': None,
        'evidence': {'note': 'Revised model found no supported label'}} for mapping in suggestion.mappings]
    newer = clone(session, suggestion, mappings=newer_mappings)
    response = student.get(BASE)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row['suggestion_revision_id'] == newer.id
    assert row['mappings'] == newer.mappings
    assert row['publication_suggestion_revision_id'] == suggestion.id
    assert row['publication_revision_id'] == published['revision_id']
    assert row['published_mappings'] == suggestion.mappings
    wrong = student.post(f'{BASE}/questions/{suggestion.question_id}/verify', json=expectation(newer, published['revision_id'], 'wrong-binding'))
    assert wrong.status_code == 409
    body = expectation(suggestion, published['revision_id'], 'verify-frozen-publication')
    for _ in range(2):
        confirmed = student.post(f'{BASE}/questions/{suggestion.question_id}/verify', json=body)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()['verification_count'] == 2
    replacement = student.post(f'{BASE}/{newer.id}/review', json=review_body(newer, previous=published['revision_id'], key='review-replacement'))
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()['verification_count'] == 1
    assert replacement.json()['revision_id'] != published['revision_id']
    old = initial.post(f'{BASE}/questions/{suggestion.question_id}/verify', json=expectation(suggestion, published['revision_id'], 'verify-superseded'))
    assert old.status_code == 409


def test_student_bulk_and_admin_dispute_resolution_permissions(session, suggestion, authenticated_client):
    student = authenticated_client(user_id=2, role='student')
    admin = authenticated_client(user_id=9, role='administrator')
    forbidden = student.post(f'{BASE}/bulk', json={'reviews': [review_body(suggestion)]})
    assert forbidden.status_code == 403
    publication = student.post(f'{BASE}/{suggestion.id}/review', json=review_body(suggestion))
    assert publication.status_code == 200, publication.text
    published_id = publication.json()['revision_id']
    replacement = [{**mapping, 'outcome': 'none_fits', 'primary_node_id': None} for mapping in suggestion.mappings]
    disputed = student.post(f'{BASE}/questions/{suggestion.question_id}/disputes', json={
        **expectation(suggestion, published_id, 'open-correction'), 'reason': 'Question attribution needs correction',
        'replacement_mappings': replacement})
    assert disputed.status_code == 200, disputed.text
    assert disputed.json()['current_revision_id'] == published_id
    resolve_body = {**expectation(suggestion, published_id, 'resolve-correction'), 'reason': 'Checked complete source and textbook evidence',
        'resolution': 'replace', 'replacement_mappings': replacement}
    url = f"{BASE}/disputes/{disputed.json()['dispute_id']}/resolve"
    assert student.post(url, json=resolve_body).status_code == 403
    unresolved = student.post(f'{BASE}/{suggestion.id}/review', json=review_body(suggestion, previous=published_id, key='cannot-overwrite-dispute'))
    assert unresolved.status_code == 422 and 'open_dispute_requires_administrator' in unresolved.json()['detail']['blockers']
    resolved = admin.post(url, json=resolve_body)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['status'] == 'replaced' and resolved.json()['verification_count'] == 1
    assert admin.post(url, json=resolve_body).json() == resolved.json()
    disputes = student.get(f'{BASE}/questions/{suggestion.question_id}/disputes')
    assert disputes.status_code == 200 and disputes.json()[0]['status'] == 'replaced'


def test_admin_bulk_checks_explicit_versions_atomically(session, suggestion, authenticated_client):
    admin = authenticated_client(user_id=9, role='administrator')
    first = review_body(suggestion, key='bulk-first')
    stale_second = review_body(suggestion, key='bulk-stale-second')
    failed = admin.post(f'{BASE}/bulk', json={'reviews': [first, stale_second]})
    assert failed.status_code == 409
    assert session.scalar(sa.select(sa.func.count(ClassificationRevision.id))) == 0
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 0
    assert session.scalar(sa.select(sa.func.count(Appearance.id))) == 0
    accepted = admin.post(f'{BASE}/bulk', json={'reviews': [first]})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['revisions'][0]['verification_count'] == 1
    assert admin.post(f'{BASE}/bulk', json={'reviews': [first]}).json() == accepted.json()
    assert session.scalar(sa.select(sa.func.count(ClassificationRevision.id))) == 1


def test_legacy_http_publication_cannot_bypass_root_readiness(session, suggestion, authenticated_client):
    admin = authenticated_client(user_id=9, role='administrator')
    student = authenticated_client(user_id=2, role='student')
    unit = session.scalar(sa.select(Unit).where(Unit.document_id == suggestion.document_id, Unit.is_gradable.is_(True)).limit(1))
    unit.classify_status = 'suggested'
    legacy_id = session.scalar(sa.select(TaxonomyMember.node_id).join(TaxonomyRelease,
        TaxonomyRelease.taxonomy_version_id == TaxonomyMember.taxonomy_version_id).where(
        TaxonomyRelease.status == 'legacy', TaxonomyMember.level == 'subtopic').limit(1))
    session.commit()
    for action in ('accept', 'accept_alt', 'edit'):
        response = student.post(f'/api/v1/curate/units/{unit.id}/decision', json={'action': action,
            'primary_node_id': legacy_id, 'secondary_node_ids': []})
        assert response.status_code == 422
        assert response.json()['detail']['code'] == 'revision_review_required'
    bulk = admin.post(f'/api/v1/curate/documents/{suggestion.document_id}/bulk_accept_bucket_a')
    assert bulk.status_code == 422
    assert bulk.json()['detail']['code'] == 'revision_review_required'
    assert session.scalar(sa.select(sa.func.count(Appearance.id))) == 0


def test_dispute_retention_binds_published_suggestion_after_model_rerun(session, suggestion, authenticated_client):
    student = authenticated_client(user_id=2, role='student')
    admin = authenticated_client(user_id=9, role='administrator')
    publication = student.post(f'{BASE}/{suggestion.id}/review', json=review_body(suggestion)).json()
    newer = clone(session, suggestion)
    disputed = student.post(f'{BASE}/questions/{suggestion.question_id}/disputes', json={
        **expectation(newer, publication['revision_id'], 'dispute-rerun'), 'reason': 'Please compare published source evidence'})
    assert disputed.status_code == 200, disputed.text
    dismissed = admin.post(f"{BASE}/disputes/{disputed.json()['dispute_id']}/resolve", json={
        **expectation(suggestion, publication['revision_id'], 'retain-old-evidence'),
        'resolution': 'dismiss', 'reason': 'Reviewed the published classification and retained its supported labels'})
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()['status'] == 'dismissed'
    assert dismissed.json()['current_revision_id'] == publication['revision_id']
    assert dismissed.json()['verification_count'] == 1


def test_selected_reviewed_taxonomy_is_not_superseded_by_foreign_draft_experiment(session, suggestion, authenticated_client):
    version = TaxonomyVersion(yaml_hash=str(uuid4()), notes='Independent draft fixture release')
    session.add(version)
    session.flush()
    session.add(TaxonomyRelease(version_id='independent-draft', taxonomy_version_id=version.id,
        target_attempt='2027-05', status='draft', manifest_hash=str(uuid4()), manifest={}))
    experiment = SuggestionRevision(batch_key=str(uuid4()), input_hash='draft-experiment', document_id=suggestion.document_id,
        extraction_revision_id=suggestion.extraction_revision_id, question_id=suggestion.question_id,
        taxonomy_version_id=version.id, run_id=1, experimental=True, context=suggestion.context,
        candidates=[], mappings=[], provenance={'method': 'fixture-draft'})
    session.add(experiment)
    session.commit()
    client = authenticated_client(user_id=2, role='student')
    queue = client.get(BASE, params={'taxonomy_version_id': suggestion.taxonomy_version_id})
    assert queue.status_code == 200, queue.text
    assert [row['suggestion_revision_id'] for row in queue.json()] == [suggestion.id]
    reviewed = client.post(f'{BASE}/{suggestion.id}/review', json=review_body(suggestion))
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['verification_count'] == 1
    assert session.get(ClassificationRevision, reviewed.json()['revision_id']).taxonomy_version_id == suggestion.taxonomy_version_id
