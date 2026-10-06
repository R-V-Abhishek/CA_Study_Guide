"""Private profile and capability tests using real opaque database sessions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa

from caf_api.auth import require_admin, router as auth_router
from caf_api.routes import router as study_router
from caf_api.curate import router as curation_router
from caf_api.main import app
from caf_db.models.app import Progress, Settings, StudySession
from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.intel import ScoreRun, SubtopicScore
from caf_db.models.ref import Node
from caf_l5 import recompute_scores
from caf_l5.config import load_scoring_config


def settings_update(settings):
    return {key: settings[key] for key in (
        'display_name', 'target_attempt_id', 'selected_paper_ids', 'hours_per_week',
        'minutes_per_subtopic', 'revision_intervals', 'exam_start_date',
    )}


def subtopic(session, paper='s2023.P1'):
    return session.scalars(sa.select(Node).where(
        Node.paper_id == paper, Node.level == 'subtopic', Node.status == 'active',
    ).order_by(Node.id)).first()


def test_all_application_routes_require_session():
    client = TestClient(app)
    checked = []
    for route in (*auth_router.routes, *study_router.routes, *curation_router.routes):
        if not isinstance(route, APIRoute) or not route.path.startswith('/api/v1'):
            continue
        path = route.path
        for parameter in route.param_convertors:
            path = path.replace('{' + parameter + '}', '999999')
        for method in sorted(route.methods - {'HEAD', 'OPTIONS'}):
            response = client.request(method, path, json={})
            assert response.status_code == 401, (method, route.path, response.status_code, response.text)
            checked.append((method, route.path))
    assert len(checked) >= 25


def test_every_administrative_endpoint_denies_student(authenticated_client):
    client = authenticated_client(2)
    checked = []
    for route in (*auth_router.routes, *study_router.routes, *curation_router.routes):
        if not isinstance(route, APIRoute):
            continue
        if not any(dependency.call is require_admin for dependency in route.dependant.dependencies):
            continue
        path = route.path
        for parameter in route.param_convertors:
            path = path.replace('{' + parameter + '}', '999999')
        for method in sorted(route.methods - {'HEAD', 'OPTIONS'}):
            response = client.request(method, path, json={})
            assert response.status_code == 403, (method, route.path, response.status_code, response.text)
            checked.append((method, route.path))
    assert len(checked) >= 10


def test_concurrent_private_records_and_exports(authenticated_client, session):
    a, b = authenticated_client(2), authenticated_client(3)
    node = subtopic(session)

    def write(client, label, status, score):
        assert client.put(f'/api/v1/subtopics/{node.id}/notes', json={'notes': label}).status_code == 200
        assert client.put(f'/api/v1/subtopics/{node.id}/progress', json={'status': status}).status_code == 200
        response = client.post('/api/v1/mock-tests', json={
            'paper_id': node.paper_id, 'score': score, 'taken_on': '2026-09-01', 'notes': label,
        })
        assert response.status_code == 200
        return response.json()['id']

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(write, a, 'private A', 'done', 77)
        future_b = pool.submit(write, b, 'private B', 'in_progress', 38)
        mock_a, mock_b = future_a.result(), future_b.result()
    assert a.delete(f'/api/v1/mock-tests/{mock_b}').status_code == 404
    assert b.delete(f'/api/v1/mock-tests/{mock_a}').status_code == 404
    for client, label, status in ((a, 'private A', 'done'), (b, 'private B', 'in_progress')):
        detail = client.get(f'/api/v1/subtopics/{node.id}').json()
        assert (detail['notes'], detail['status']) == (label, status)
        export = client.get('/api/v1/me/export')
        assert export.status_code == 200, export.text
        data = export.json()
        assert len(data['notes']) == len(data['progress']) == len(data['mock_tests']) == 1
        assert data['notes'][0]['body'] == data['mock_tests'][0]['notes'] == label
        assert data['progress'][0]['status'] == status
    assert a.put(f'/api/v1/subtopics/{node.id}/notes', json={'notes': 'forged', 'user_id': 3}).status_code == 422
    assert a.put(f'/api/v1/subtopics/{node.id}/progress', json={'status': 'done', 'owner_id': 3}).status_code == 422
    assert a.post('/api/v1/mock-tests', json={'paper_id': node.paper_id, 'score': 1, 'taken_on': '2026-09-01', 'user_id': 3}).status_code == 422


def test_profile_settings_validation_and_selected_personal_scope(authenticated_client, session):
    a, b = authenticated_client(2), authenticated_client(3)
    original_b = b.get('/api/v1/me/settings').json()
    payload = settings_update(a.get('/api/v1/me/settings').json())
    payload.update(display_name='Private A', target_attempt_id='2027-05', selected_paper_ids=['s2023.P1'], hours_per_week=12.5, revision_intervals=[2, 5, 11])
    response = a.put('/api/v1/me/settings', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['groups'] == [1]
    assert response.json()['available_attempts']
    assert a.get('/api/v1/me').json()['account']['name'] == 'Private A'
    assert b.get('/api/v1/me/settings').json() == original_b
    for invalid in (
        {'target_attempt_id': 'unknown'}, {'selected_paper_ids': ['unknown']},
        {'selected_paper_ids': []}, {'hours_per_week': 0}, {'minutes_per_subtopic': -1},
        {'revision_intervals': [3, 3]}, {'revision_intervals': [0, 5]}, {'display_name': '  '},
        {'user_id': 3},
    ):
        assert a.put('/api/v1/me/settings', json=payload | invalid).status_code == 422
    p1, p2 = subtopic(session), subtopic(session, 's2023.P2')
    now = datetime.now(timezone.utc)
    session.add_all([
        Progress(user_id=2, node_id=p1.id, status='done', first_done_at=now-timedelta(days=40)),
        Progress(user_id=2, node_id=p2.id, status='done', first_done_at=now-timedelta(days=40)),
        StudySession(user_id=2, node_id=p1.id, started_at=now),
        StudySession(user_id=3, node_id=p2.id, started_at=now),
    ])
    session.commit()
    dashboard = a.get('/api/v1/dashboard').json()
    assert dashboard['done_subtopics'] == 1
    assert dashboard['total_subtopics'] == session.scalar(sa.select(sa.func.count()).select_from(Node).where(Node.paper_id == 's2023.P1', Node.level == 'subtopic', Node.status == 'active'))
    revisions = a.get('/api/v1/revision/due').json()['items']
    assert [item['node_id'] for item in revisions] == [p1.id]
    assert a.get('/api/v1/papers/s2023.P2/tree').status_code == 200
    export = a.get('/api/v1/me/export').json()
    assert len(export['progress']) == 2
    assert [row['node_id'] for row in export['study_sessions']] == [p1.id]


def test_matching_score_run_and_no_cross_attempt_fallback(authenticated_client, session):
    a = authenticated_client(2, target='2026-05')
    b = authenticated_client(3, target='2027-05')
    node = subtopic(session)
    config = load_scoring_config()
    def add_run(target, importance, shadow=False, status='ok'):
        run = ScoreRun(scoring_version=config.version, config_hash=config.config_hash,
                       config_snapshot=config.model_dump(mode='json'), target_attempt_id=target,
                       shadow=shadow, is_current=False, status=status, finished_at=datetime.now(timezone.utc))
        session.add(run)
        session.flush()
        session.add(SubtopicScore(score_run_id=run.id, node_id=node.id, applicable=True,
                                 exam_score=0, practice_score=0, weight_prior=1, importance=importance,
                                 freq_hits=0, freq_window=0, exam_marks_total=0, exam_count=0, practice_count=0))
        session.commit()
        return run.id
    first = add_run('2026-05', .3)
    latest = add_run('2026-05', .7)
    add_run('2027-05', .8, shadow=True)
    add_run('2027-05', .9, status='failed')
    assert latest > first
    detail = a.get(f'/api/v1/subtopics/{node.id}').json()
    assert detail['score_run']['id'] == latest
    assert detail['score']['importance'] == .7
    other = b.get(f'/api/v1/subtopics/{node.id}').json()
    assert other['score_run'] is None and other['score']['importance'] is None
    assert b.get('/api/v1/meta').json()['score_run'] is None
    assert b.get(f'/api/v1/why/subtopic/{node.id}').json()['explanation_status'] == 'no_score_run'
    plan = b.get('/api/v1/plan').json()
    assert plan['items'] == [] and 'target attempt' in plan['score_unavailable_reason']
    with pytest.raises(ValueError, match='explicit'):
        recompute_scores(session)
    with pytest.raises(ValueError, match='Unknown target attempt'):
        recompute_scores(session, target_attempt_id='unknown')
    settings = settings_update(b.get('/api/v1/me/settings').json())
    settings['target_attempt_id'] = '2026-05'
    assert b.put('/api/v1/me/settings', json=settings).status_code == 200
    assert session.scalar(sa.select(sa.func.count()).select_from(ScoreRun)) == 4
    assert b.get('/api/v1/meta').json()['score_run_id'] == latest


def test_curator_actor_and_concurrent_stale_review(authenticated_client, session):
    a, b = authenticated_client(2), authenticated_client(3)
    node = subtopic(session)
    doc = Document(sha256='phase2-document', blob_path='/tmp/test.pdf', bytes=0,
                   origin='manual', scheme_id='s2023', attempt_id='2024-05', paper_id='s2023.P1',
                   doc_type_id='suggested_answer', catalog_status='confirmed', extract_status='ok')
    session.add(doc)
    session.flush()
    unit = Unit(document_id=doc.id, extract_run_id=1, label_path='Q1', display_label='1',
                kind='part', is_gradable=True, marks=4, page_start=1, page_end=1,
                block_start='p1-b1', block_end='p1-b2', question_text='Phase 2 question',
                text_origin='pdf', fingerprint='phase2-unit', parse_confidence='high',
                classify_status='suggested', current=True)
    session.add(unit)
    session.flush()
    session.add(TagSuggestion(unit_id=unit.id, run_id=1, node_id=node.id, role='primary',
                              method='anchor', bucket='A', evidence={}))
    session.commit()
    assert a.post(f'/api/v1/curate/units/{unit.id}/decision', json={'action': 'bulk_accept', 'primary_node_id': node.id}).status_code == 403
    def review(client):
        return client.post(f'/api/v1/curate/units/{unit.id}/decision', json={'action': 'none_fits'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(review, client) for client in (a, b)]
        responses = [future.result() for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
    rows = session.scalars(sa.select(Decision).where(Decision.unit_fingerprint == unit.fingerprint)).all()
    assert len(rows) == 1 and rows[0].actor_id in (2, 3)
