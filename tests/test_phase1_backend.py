"""Deterministic Phase 1 contracts: no live corpus assumptions or external API calls."""

from datetime import datetime, timedelta, timezone

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa

from caf_api.main import app
from caf_db.engine import get_engine
from caf_db.models.app import Progress
from caf_db.models.intel import ScoreRun, SubtopicScore
from caf_db.models.ingest import Document, TagSuggestion, Unit, UnitAnswer
from caf_db.models.ref import Node, WeightageMember, WeightageSection
from caf_l5 import generate_study_plan, recompute_scores
from caf_l5.config import ScoringConfig, WeightsConfig, load_scoring_config
from caf_l5.service import get_current_score_run
from caf_l5.why import get_subtopic_why


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def scored_nodes(session):
    nodes = session.query(Node).where(Node.paper_id == 's2023.P1', Node.level == 'subtopic', Node.status == 'active').order_by(Node.id).limit(3).all()
    config = load_scoring_config()
    run = ScoreRun(scoring_version=config.version, config_hash=config.config_hash,
                   config_snapshot=config.model_dump(mode='json'), target_attempt_id='2026-05',
                   shadow=False, is_current=True, status='ok', finished_at=datetime.now(timezone.utc))
    session.add(run)
    session.flush()
    for index, node in enumerate(nodes):
        session.add(SubtopicScore(score_run_id=run.id, node_id=node.id, applicable=index != 2,
                                 exam_score=7.5 if index == 0 else 15, practice_score=4,
                                 weight_prior=2, importance=0.5, freq_hits=4, freq_window=5,
                                 exam_marks_total=8, exam_count=4, practice_count=1))
    session.commit()
    return run, nodes


def test_empty_null_and_zero_contracts(client, session):
    paper = client.get('/api/v1/papers').json()[0]
    assert paper['average_importance'] is None
    assert paper['raw_progress_pct'] == paper['weighted_coverage_pct'] == 0
    assert paper['weak_topic_count'] == paper['revision_due_count'] == 0
    dashboard = client.get('/api/v1/dashboard').json()
    assert dashboard['overall_progress_pct'] == 0
    assert dashboard['weighted_coverage']['overall_coverage_pct'] is None
    assert dashboard['plan_preview'] == dashboard['weak_subtopics'] == []
    sub = session.query(Node).where(Node.level == 'subtopic').first()
    detail = client.get(f'/api/v1/subtopics/{sub.id}').json()
    assert detail['score']['importance'] is None
    assert detail['score_run'] is None
    why = client.get(f'/api/v1/why/subtopic/{sub.id}').json()
    assert why['explanation_status'] == 'no_score_run'
    assert why['importance_breakdown']['weights'] is None
    assert client.get('/api/v1/plan').json()['items'] == []
    assert client.get('/api/v1/revision/due').json() == {'total_due': 0, 'items': []}


def test_normalization_and_snapshot_survive_config_changes(client, session, scored_nodes, monkeypatch):
    run, nodes = scored_nodes
    import caf_l5.why
    changed = ScoringConfig(weights=WeightsConfig(exam=0.1, practice=0.8, prior=0.1))
    monkeypatch.setattr(caf_l5.why, 'load_scoring_config', lambda: changed)
    why = client.get(f'/api/v1/why/subtopic/{nodes[0].id}').json()
    assert why['explanation_status'] == 'available'
    assert why['configuration_source'] == 'snapshot'
    exam = why['importance_breakdown']['exam']
    assert exam['score_E'] == 7.5
    assert exam['normalized_E_pct'] == 50
    assert exam['weighted_contribution_pct'] == 30
    assert why['importance_breakdown']['weights']['exam'] == 0.6
    assert why['score_run']['target_attempt_id'] == run.target_attempt_id
    assert client.get(f'/api/v1/subtopics/{nodes[0].id}').json()['score_run'] == why['score_run']


def test_legacy_matching_and_mismatching_configuration(session, scored_nodes):
    run, nodes = scored_nodes
    run.config_snapshot = None
    session.commit()
    matching = get_subtopic_why(session, nodes[0].id)
    assert matching['explanation_status'] == 'available'
    assert matching['configuration_source'] == 'matching_current'
    run.config_hash = 'historical-config-not-present'
    session.commit()
    missing = get_subtopic_why(session, nodes[0].id)
    assert missing['explanation_status'] == 'historical_configuration_unavailable'
    assert missing['importance_breakdown']['importance'] == 0.5
    assert missing['importance_breakdown']['weights'] is None
    assert missing['importance_breakdown']['exam'] is None
    assert missing['appearances'] == []


def test_shadow_runs_are_never_selected(client, session, scored_nodes):
    run, nodes = scored_nodes
    shadow = ScoreRun(scoring_version='shadow', config_hash='shadow', target_attempt_id='2026-05',
                      shadow=True, is_current=True, status='ok')
    session.add(shadow)
    session.commit()
    assert get_current_score_run(session).id == run.id
    assert client.get(f'/api/v1/subtopics/{nodes[0].id}').json()['score_run']['id'] == run.id
    assert get_subtopic_why(session, nodes[0].id)['score_run']['id'] == run.id
    with pytest.raises(ValueError, match='non-shadow'):
        get_subtopic_why(session, nodes[0].id, shadow.id)
    run.is_current = False
    session.commit()
    assert get_current_score_run(session).id == run.id


def test_plan_budget_groups_and_ties(client, session, scored_nodes):
    for group in (1, 2):
        response = client.get('/api/v1/plan', params={'group': group, 'paper': 'P1', 'hours': 3})
        assert response.status_code == 200
        assert bool(response.json()['items']) == (group == 1)
    run, nodes = scored_nodes
    tiny = generate_study_plan(session, user_id=1, hours_per_week=0.1)
    assert tiny['budget_items'] == tiny['total_allocated'] == 0
    assert tiny['items'] == []
    ordered = generate_study_plan(session, user_id=1, hours_per_week=3, group_no=1, paper_id='P1')
    assert [item['node_id'] for item in ordered['items']] == sorted(node.id for node in nodes[:2])
    assert generate_study_plan(session, user_id=1, group_no=2, paper_id='P1')['items'] == []
    for value in (-1, 0, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='finite and positive'):
            generate_study_plan(session, user_id=1, hours_per_week=value)
    for query in ('hours=0', 'hours=-2', 'hours=nan', 'hours=inf', 'group=3'):
        assert client.get(f'/api/v1/plan?{query}').status_code == 422


def test_real_paper_metrics_and_successful_mutation_contracts(client, session, scored_nodes):
    _, nodes = scored_nodes
    paper = next(p for p in client.get('/api/v1/papers').json() if p['code'] == 'P1')
    assert paper['average_importance'] == 0.5  # excludes non-applicable score
    assert paper['weak_topic_count'] == 2
    node = nodes[0]
    progress = client.put(f'/api/v1/subtopics/{node.id}/progress', json={'status': 'done'})
    assert progress.status_code == 200
    assert progress.json()['status'] == 'done'
    notes = client.put(f'/api/v1/subtopics/{node.id}/notes', json={'notes': 'unsaved → saved'})
    assert notes.status_code == 200
    assert notes.json()['notes'] == 'unsaved → saved'
    session.expire_all()
    state = session.get(Progress, (1, node.id))
    state.first_done_at = datetime.now(timezone.utc) - timedelta(days=10)
    session.commit()
    paper = next(p for p in client.get('/api/v1/papers').json() if p['code'] == 'P1')
    assert paper['weak_topic_count'] == 1
    assert paper['revision_due_count'] == 1
    revision = client.post(f'/api/v1/subtopics/{node.id}/revisions', json={'outcome': 'ok'})
    assert revision.status_code == 200
    assert revision.json()['node_id'] == node.id
    mock = client.post('/api/v1/mock-tests', json={'paper_id': paper['id'], 'score': 0, 'max_score': 100, 'taken_on': '2026-09-01'})
    assert mock.status_code == 200
    assert mock.json()['score_pct'] == 0
    deleted = client.delete(f'/api/v1/mock-tests/{mock.json()["id"]}')
    assert deleted.json() == {'deleted': True, 'id': mock.json()['id']}
    assert client.put('/api/v1/subtopics/missing/progress', json={'status': 'done'}).status_code == 404
    assert client.post('/api/v1/mock-tests', json={'paper_id': paper['id'], 'score': 0, 'max_score': 0, 'taken_on': '2026-09-01'}).status_code == 422


@pytest.mark.parametrize('missing_kind', ['all', 'partial', 'zero_weight'])
def test_paper_weightage_unavailable_does_not_fabricate_coverage(client, session, scored_nodes, missing_kind):
    _, nodes = scored_nodes
    def paper_summary():
        return next(p for p in client.get('/api/v1/papers').json() if p['code'] == 'P1')

    # Actual positive fixture weightage and no completions means a legitimate zero.
    assert paper_summary()['weighted_coverage_pct'] == 0
    if missing_kind == 'zero_weight':
        session.execute(sa.update(WeightageSection).where(
            WeightageSection.paper_id == 's2023.P1',
        ).values(min_pct=0, max_pct=0))
    else:
        chapters = sa.select(Node.id).where(Node.paper_id == 's2023.P1', Node.level == 'chapter')
        condition = WeightageMember.chapter_id.in_(chapters)
        if missing_kind == 'partial':
            topic = session.get(Node, nodes[0].parent_id)
            condition = WeightageMember.chapter_id == topic.parent_id
        session.execute(sa.delete(WeightageMember).where(condition))
    session.commit()
    assert paper_summary()['weighted_coverage_pct'] is None
    assert paper_summary()['raw_progress_pct'] == 0


def test_scored_coverage_zero_and_unavailable_denominators(client, session, scored_nodes):
    run, _ = scored_nodes
    coverage = client.get('/api/v1/dashboard').json()['weighted_coverage']
    assert coverage['overall_coverage_pct'] == 0
    assert coverage['groups']['1']['coverage_pct'] == 0
    assert coverage['papers']['s2023.P1']['coverage_pct'] == 0
    assert coverage['groups']['2'] == {'coverage_pct': None, 'in_progress_pct': None}
    session.execute(sa.update(SubtopicScore).where(SubtopicScore.score_run_id == run.id).values(weight_prior=0))
    session.commit()
    coverage = client.get('/api/v1/dashboard').json()['weighted_coverage']
    assert coverage['overall_coverage_pct'] is None
    assert coverage['overall_in_progress_pct'] is None
    assert coverage['groups']['1'] == {'coverage_pct': None, 'in_progress_pct': None}
    assert coverage['papers']['s2023.P1']['coverage_pct'] is None


def test_recompute_records_effective_snapshot(session):
    config = ScoringConfig(weights=WeightsConfig(exam=0.2, practice=0.3, prior=0.5))
    run = recompute_scores(session, target_attempt_id="2026-05", config=config)
    assert run.config_snapshot == config.model_dump(mode='json')
    score = session.query(SubtopicScore).where(
        SubtopicScore.score_run_id == run.id, SubtopicScore.applicable.is_(True),
    ).first()
    breakdown = get_subtopic_why(session, score.node_id)['importance_breakdown']
    assert breakdown['weights'] == {'exam': 0.2, 'practice': 0.3, 'prior': 0.5}
    contributions = sum(breakdown[key]['weighted_contribution'] for key in ('exam', 'practice', 'weightage_prior'))
    assert contributions == pytest.approx(score.importance, abs=0.0001)


def test_curator_contract_ancestry_and_complete_nullable_answers(client, session, scored_nodes):
    _, nodes = scored_nodes
    node = nodes[0]
    topic = session.get(Node, node.parent_id)
    chapter = session.get(Node, topic.parent_id)
    doc = Document(sha256='phase1-contract-doc', blob_path='/tmp/fixture.pdf', bytes=0,
                   origin='manual', scheme_id='s2023', attempt_id='2024-05',
                   paper_id='s2023.P1', doc_type_id='suggested_answer',
                   catalog_status='confirmed', extract_status='ok')
    session.add(doc)
    session.flush()
    unit = Unit(document_id=doc.id, extract_run_id=1, label_path='Q1', display_label='1',
                kind='part', is_gradable=True, marks=None, page_start=1, page_end=1,
                block_start='p1-b1', block_end='p1-b2', question_text='Fixture question',
                text_origin='pdf', fingerprint='phase1-contract-unit', parse_confidence='high',
                classify_status='suggested', current=True)
    session.add(unit)
    session.flush()
    session.add(TagSuggestion(unit_id=unit.id, run_id=1, node_id=node.id, role='primary',
                              method='anchor', bucket='A', evidence={'alternatives': [topic.id]}))
    answer = UnitAnswer(unit_id=unit.id, answer_document_id=doc.id, answer_text=None, pairing_method='same_doc')
    session.add(answer)
    session.commit()
    item = client.get('/api/v1/curate/queue?paper_id=s2023.P1&bucket=A').json()[0]
    assert item['answer_text'] is None
    suggestion = item['primary_suggestion']
    assert suggestion['chapter'] == {'id': chapter.id, 'name': chapter.name}
    assert suggestion['topic'] == {'id': topic.id, 'name': topic.name}
    assert suggestion['subtopic'] == {'id': node.id, 'name': node.name}
    assert suggestion['alternatives'] == [topic.id]
    answer.answer_text = 'A long complete answer. ' * 2000 + 'END OF ANSWER'
    session.commit()
    item = client.get('/api/v1/curate/queue').json()[0]
    assert item['answer_text'] == answer.answer_text


def test_forward_migration_preserves_legacy_rows(session, isolated_database):
    # Use a fresh baseline database; identity migrations are forward-only.
    from uuid import uuid4
    database = f"caf_baseline_{uuid4().hex}"
    isolated_database.allow(database)
    admin = sa.create_engine(isolated_database.url(), isolation_level="AUTOCOMMIT")
    engine = sa.create_engine(isolated_database.url(database))
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{database}"'))
        with engine.begin() as conn:
            cfg = Config('alembic.ini')
            cfg.attributes['connection'] = conn
            command.upgrade(cfg, '0001_initial_schema')
            conn.execute(sa.text("INSERT INTO ref.attempt(id,exam_year,exam_month,label,verified) VALUES('2026-05',2026,5,'May 2026',false)"))
            before = conn.execute(sa.text("INSERT INTO intel.score_run(scoring_version, config_hash, target_attempt_id, shadow, is_current, status) VALUES('old', 'old-hash', '2026-05', false, true, 'ok') RETURNING id, config_hash")).one()
            command.upgrade(cfg, 'head')
            row = conn.execute(sa.text('SELECT id, config_hash, config_snapshot FROM intel.score_run')).one()
            assert tuple(row) == (before.id, before.config_hash, None)
            assert conn.execute(sa.text('SELECT version_num FROM ops.alembic_version')).scalar_one() == '0003_identity'
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE "{database}"'))
        admin.dispose()
