"""Student API scope and queued administration against reviewed isolated fixtures."""

import sqlalchemy as sa

from caf_db.models.app import Progress, Settings
from caf_db.models.intel import AttemptTaxonomyBinding, CorpusCoverage, RecomputeJob
from caf_db.models.ref import ApplicabilityRule
from caf_l5.config import load_scoring_config
from caf_l5.scoring import recompute_scores
from test_phase5_publication import suggestion
from test_phase6_intelligence import manifest, reviewed_context


def test_missing_profile_settings_return_unavailable_context_without_server_error(
    session, authenticated_client,
):
    session.delete(session.get(Settings, 1))
    session.commit()
    client = authenticated_client(1)
    context = client.get('/api/v1/meta').json()['context']
    assert context['readiness'] == 'profile_settings_unavailable'
    assert context['target_attempt_id'] is None
    assert client.get('/api/v1/papers').status_code == 200


def test_two_profiles_share_no_attempt_snapshot_or_applicability(
    session, reviewed_context, authenticated_client,
):
    suggestion, target = reviewed_context
    a = authenticated_client(1, target=target)
    session.add(Settings(user_id=2, target_attempt_id='2026-05', selected_paper_ids=['s2023.P1']))
    session.commit()
    b = authenticated_client(2, target='2026-05')
    session.add(AttemptTaxonomyBinding(
        target_attempt_id='2026-05', taxonomy_version_id=suggestion.taxonomy_version_id,
        status='reviewed', reviewed_by=9,
        scoring_config=load_scoring_config().model_dump(mode='json'),
    ))
    settings = session.get(Settings, 2)
    settings.selected_paper_ids = ['s2023.P1']
    node_id = suggestion.mappings[0]['primary_node_id']
    session.add(ApplicabilityRule(node_id=node_id, attempt_id='2026-05',
                                 effect='exclude', source_note='Synthetic version-bound exclusion'))
    session.commit()
    run_a = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    run_b = recompute_scores(session, '2026-05', taxonomy_version_id=suggestion.taxonomy_version_id)
    meta_a, meta_b = a.get('/api/v1/meta').json(), b.get('/api/v1/meta').json()
    assert meta_a['context']['target_attempt_id'] == target
    assert meta_b['context']['target_attempt_id'] == '2026-05'
    assert meta_a['score_run_id'] == run_a.id
    assert meta_b['score_run_id'] == run_b.id
    assert a.get(f'/api/v1/subtopics/{node_id}').status_code == 200
    assert b.get(f'/api/v1/subtopics/{node_id}').status_code == 404
    assert b.put(f'/api/v1/subtopics/{node_id}/progress', json={'status': 'done'}).status_code == 404
    assert session.get(Progress, (2, node_id)) is None
    assert a.get('/api/v1/plan').json()['basis'] == 'syllabus'
    assert b.get('/api/v1/plan').json()['items'] == []


def test_partial_score_explanation_is_typed_and_uses_resolved_snapshot(
    session, reviewed_context, authenticated_client,
):
    suggestion, target = reviewed_context
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    client = authenticated_client(1, target=target)
    node_id = suggestion.mappings[0]['primary_node_id']
    response = client.get(f'/api/v1/why/subtopic/{node_id}')
    assert response.status_code == 200, response.text
    why = response.json()
    assert why['score_run']['id'] == run.id
    assert why['explanation_status'] == 'partial_evidence'
    assert why['importance_breakdown']['importance'] is None
    assert why['importance_breakdown']['weights'] == {'exam': .6, 'practice': .2, 'prior': .2}
    assert why['frequency']['available'] is False
    detail = client.get(f'/api/v1/subtopics/{node_id}').json()
    assert detail['score']['known_weighted_subtotal'] == why['importance_breakdown']['known_weighted_subtotal']
    assert detail['score']['exam_normalized'] is None


def test_admin_recompute_queues_and_coalesces_without_computing(
    session, reviewed_context, authenticated_client,
):
    suggestion, target = reviewed_context
    client = authenticated_client(9, role='administrator', target=target)
    params = {'target_attempt_id': target, 'taxonomy_version_id': suggestion.taxonomy_version_id}
    first = client.post('/api/v1/curate/intel/recompute', params=params)
    second = client.post('/api/v1/curate/intel/recompute', params=params)
    assert first.status_code == second.status_code == 202, first.text
    assert first.json()['job_id'] == second.json()['job_id']
    assert first.json()['run_id'] is None
    assert session.scalar(sa.select(sa.func.count()).select_from(RecomputeJob)) == 1


def test_coverage_keeps_unknown_inventory_and_partial_scope_visible(
    session, reviewed_context, authenticated_client,
):
    suggestion, target = reviewed_context
    session.add(CorpusCoverage(taxonomy_version_id=suggestion.taxonomy_version_id,
        paper_id='s2023.P1', attempt_id='2026-05', source_family='QP',
        expected_slots=None, discovered_count=1, acquired_count=1,
        published_roots=1, reviewed_roots=1, missing_answers=1,
        blockers=['question_scope_not_confirmed']))
    session.commit()
    response = authenticated_client(1, target=target).get('/api/v1/coverage')
    assert response.status_code == 200, response.text
    item = response.json()['items'][0]
    assert item['expected_slots'] is None
    assert item['usable_exam'] is False
    assert item['missing_answers'] == 1
    assert 'expected_inventory_unknown' in item['blockers']
    assert 'question_scope_not_confirmed' in item['blockers']
