"""Complete published projections remain usable with incomplete reviewed corpora."""
import copy
import hashlib
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from caf_db.engine import get_engine
from caf_db.models.app import Note, UserAccount
from caf_db.models.classification import ClassificationEvent, QuestionPublication
from caf_db.models.questions import PublishedQuestion, PublishedSource, QuestionOccurrence, CorpusGeneration
from caf_db.models.intel import AttemptTaxonomyBinding, RecomputeJob, ScoreRun
from caf_l4.questions import backfill_publications, marks_projection, _occurrence
from test_phase5_publication import suggestion, review
from test_phase3_release import manifest


def test_complete_reader_and_search_under_student_credentials(session,suggestion,authenticated_client):
    client=authenticated_client()
    result=review(session,suggestion);session.commit()
    question_id=suggestion.question_id
    response=client.get(f'/api/v1/questions/{question_id}')
    assert response.status_code==200,response.text
    question=response.json()
    assert question['snapshot_id']==result['revision_id']
    assert len(question['content']['parts'])==2
    assert 'Shared case' in question['content']['common_stem']
    assert question['content']['answer_status']=='missing'
    assert question['verification_count']==1
    assert question['covered_subtopics'][0]['path'][-1]['id']==suggestion.mappings[0]['primary_node_id']
    from caf_db.models.core import Appearance
    appearances=list(session.scalars(sa.select(Appearance).where(Appearance.question_id==question_id)))
    for appearance in appearances:
        resolved=client.get(f'/api/v1/appearances/{appearance.id}').json()
        assert resolved['question_id']==question_id
        assert resolved['part_id']==appearance.part_id
    listing=client.get('/api/v1/questions',params={'paper_id':'s2023.P1','page_size':1}).json()
    assert listing['total']==1 and len(listing['items'])==1
    assert client.get('/api/v1/questions',params={'paper_id':'s2023.P2'}).json()['total']==0
    found=client.get('/api/v1/search',params={'q':'recognition'}).json()
    assert found['total']==1
    assert client.get(question['sources'][0]['url']).content[:4]==b'%PDF'
    assert client.get(question['sources'][0]['page_url'].replace('{page}','1')).headers['content-type']=='image/png'
    assert client.get('/api/v1/published-sources/999999').status_code==404
    # Student serves snapshots through restricted privileges without staging.
    with Session(get_engine('student')) as student:
        assert student.get(PublishedQuestion,result['revision_id']).content['question_id']==question_id
        with pytest.raises(DBAPIError):
            student.execute(sa.text('SELECT id FROM ingest.extraction_revision'))
        student.rollback()


def test_undated_published_question_is_readable_without_invented_attempt(session,suggestion,authenticated_client):
    client=authenticated_client()
    from caf_db.models.ingest import Document
    doc=session.get(Document,suggestion.document_id)
    # Fixture suggestion was already pinned to a dated source, so keep that
    # immutable context consistent and use the publication service directly to
    # demonstrate the approved undated projection path independently of review.
    from caf_db.models.classification import ClassificationRevision
    from caf_l4.questions import project_question
    revision=ClassificationRevision(question_id=suggestion.question_id,suggestion_revision_id=suggestion.id,
        extraction_revision_id=suggestion.extraction_revision_id,taxonomy_version_id=suggestion.taxonomy_version_id,
        mappings=suggestion.mappings,context={**suggestion.context,'source_attempt_id':None},input_hash=suggestion.input_hash,
        actor_id=1,blind=False)
    session.add(revision);session.flush()
    doc.attempt_id=None
    publication=QuestionPublication(question_id=suggestion.question_id,document_id=doc.id,current_revision_id=revision.id)
    session.add(publication);session.flush()
    project_question(session,suggestion,revision,publication);session.commit()
    question=client.get(f'/api/v1/questions/{suggestion.question_id}').json()
    assert question['content']['source_attempt_id'] is None
    assert question['occurrence']['attempt_id'] is None
    assert client.get('/api/v1/questions',params={'source_family':question['content']['source_family']}).json()['total']==1


def test_private_note_search_enforces_account_owner(session,suggestion,authenticated_client):
    client=authenticated_client()
    review(session,suggestion)
    node_id=suggestion.mappings[0]['primary_node_id']
    session.add_all([Note(user_id=1,node_id=node_id,body='Private recognition notebook'),
        Note(user_id=2,node_id=node_id,body='Secret recognition notebook')])
    session.commit()
    result=client.get('/api/v1/search',params={'q':'recognition','include_notes':True}).json()
    assert result['notes']==[{'node_id':node_id,'content':'Private recognition notebook'}]
    assert client.get('/api/v1/search',params={'q':'recognition'}).json()['notes']==[]


def test_snapshot_history_immutable_and_backfill_does_not_create_review(session,suggestion):
    result=review(session,suggestion);session.commit()
    snapshot=session.get(PublishedQuestion,result['revision_id'])
    with pytest.raises(DBAPIError):
        session.execute(sa.update(PublishedQuestion).where(PublishedQuestion.id==snapshot.id).values(search_text='tampered'))
    session.rollback()
    before=session.scalar(sa.select(sa.func.count()).select_from(ClassificationEvent))
    publication=session.get(QuestionPublication,suggestion.question_id)
    publication.current_snapshot_id=None
    session.flush()
    assert backfill_publications(session)['created']==1
    assert publication.current_snapshot_id==snapshot.id
    # Already materialized publications make a backfill idempotent.
    assert backfill_publications(session)=={'created':0,'skipped_experimental_or_blind':[]}
    assert session.scalar(sa.select(sa.func.count()).select_from(ClassificationEvent))==before


def test_marks_disjoint_unknown_and_or_groups():
    def node(label,marks,children=(),group=None):
        return dict(label_path=label,marks=marks,children=list(children),is_gradable=True,choice_role='compulsory',or_group=group)
    child_a=node('1.a',10);child_b=node('1.b',10)
    root=node('1',20,[child_a,child_b])
    mappings=[dict(part_id=part_id,outcome='matched',excluded=False,primary_node_id='topic',secondary_node_ids=['secondary'])
        for part_id in ['q','q:1.a','q:1.b']]
    result=marks_projection(root,'q',mappings)
    assert result['offered_marks']==20
    assert len(result['allocations'])==2
    assert sum(s['attributed_marks'] for a in result['allocations'] for s in a['node_shares'])==pytest.approx(20)
    child_a['marks']=None
    assert marks_projection(root,'q',mappings)['offered_marks'] is None
    child_a['marks']=10;child_a['or_group']=child_b['or_group']='choice-1'
    result=marks_projection(root,'q',mappings)
    assert result['offered_marks']==20 and result['selectable_marks'] is None
    assert all(s['attributed_marks'] is None for a in result['allocations'] for s in a['node_shares'])


def test_generation_transactionally_queues_exact_known_context(session,suggestion):
    from caf_l5.config import load_scoring_config
    config=load_scoring_config()
    session.add(AttemptTaxonomyBinding(target_attempt_id='2026-05',taxonomy_version_id=suggestion.taxonomy_version_id,
        status='reviewed',reviewed_by=9,scoring_config={}))
    session.commit()
    run=ScoreRun(scoring_version='phase6',config_hash=config.config_hash,config_snapshot=config.model_dump(mode='json'),
        target_attempt_id='2026-05',taxonomy_version_id=suggestion.taxonomy_version_id,status='ok',is_current=True)
    session.add(run);session.commit()
    before=session.get(CorpusGeneration,1).generation
    review(session,suggestion);session.commit()
    session.expire_all()
    state=session.get(CorpusGeneration,1)
    assert state.generation>before
    jobs=list(session.scalars(sa.select(RecomputeJob).where(RecomputeJob.status=='pending')))
    assert len(jobs)==1 and jobs[0].corpus_generation==state.generation
    assert jobs[0].taxonomy_version_id==suggestion.taxonomy_version_id
    assert jobs[0].config_snapshot==run.config_snapshot


def test_confirmed_pair_reconciles_existing_occurrences_and_reuse_stays_separate(session,tmp_path):
    from test_phase4_revisions import source
    from caf_l2.revisions import confirm_pair
    qdoc,_=source(session,tmp_path,doc_type='question_paper')
    adoc,_=source(session,tmp_path,doc_type='suggested_answer',body='Question 1\nRecognition explanation answer.')
    qdoc.attempt_id=adoc.attempt_id='2026-05'
    session.commit()
    qcontent=dict(question_id='question-root',paper_id='s2023.P1',source_family='examination',
        label_path='1',source_document_ids=[qdoc.id])
    acontent={**qcontent,'question_id':'answer-root','source_document_ids':[adoc.id]}
    qocc=_occurrence(session,qdoc,qcontent)
    aocc=_occurrence(session,adoc,acontent)
    session.commit()
    assert qocc.id!=aocc.id and aocc.identity_status=='ambiguous'
    pair=confirm_pair(session,qdoc.id,adoc.id,1,'Compared identity and question label in both official fixtures')
    session.commit();session.refresh(aocc)
    assert aocc.canonical_occurrence_id==qocc.id and aocc.identity_status=='confirmed'
    assert _occurrence(session,adoc,acontent).id==qocc.id
    practice,_=source(session,tmp_path,doc_type='rtp',body='Question 1\nRecognition criteria reused in RTP.')
    practice.attempt_id='2026-05';session.commit()
    poc=_occurrence(session,practice,{**qcontent,'source_family':'rtp','source_document_ids':[practice.id]})
    session.commit()
    assert poc.id not in {qocc.id,aocc.id} and poc.signal_class=='practice'
    pair.status='rejected';session.commit();session.refresh(aocc)
    assert aocc.canonical_occurrence_id is None and aocc.identity_status=='ambiguous'
