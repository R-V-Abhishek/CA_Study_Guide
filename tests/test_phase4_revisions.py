"""Behavioral extraction revision, source access and review permission regressions."""
from pathlib import Path
import pytest
import sqlalchemy as sa
import pymupdf as fitz
from caf_common.blob_store import BlobStore
from caf_common.settings import get_settings
from caf_db.models.ingest import Document, Unit, UnitAnswer
from caf_db.models.extraction import ExtractionRevision, ExtractionReview, ReconciliationLink
from caf_db.models.core import Decision, Appearance
from caf_db.models.ops import Run
from caf_l2.pipeline import ExtractionPipeline
from caf_l2.revisions import promote_revision, RevisionConflict, confirm_pair
from test_phase3_release import manifest


def source(session, tmp_path, doc_type='model_question', body=None, pages=None, **metadata):
    pdf=fitz.open()
    for text in pages or [body or 'Question 1\nShared case information for the entire question.\n(a) Explain recognition criteria in detail.\n(10 Marks)\n(b) Calculate the liability using the case facts.\n(10 Marks)']:
        page=pdf.new_page()
        page.insert_text((40,120),text,fontsize=11)
    data=pdf.tobytes(); pdf.close()
    store=BlobStore(get_settings().storage.blob_dir)
    sha,path=store.put(data)
    doc=Document(sha256=sha,blob_path=str(path),bytes=len(data),origin='manual',course_level='final',
        provenance_status='verified',scheme_id='s2023',paper_id='s2023.P1',attempt_id=None,
        collection_id='model-2026',doc_type_id=doc_type,catalog_status='confirmed',**metadata)
    session.add(doc); session.commit()
    return doc,ExtractionPipeline(store,Path('profiles'),tmp_path/'overrides')


def extract(session,pipe,doc):
    run=Run(stage='l2_extract',status='running',stats={})
    session.add(run); session.commit()
    return pipe.extract_document(session,doc.id,run.id)


def test_candidate_assembly_pairing_and_duplicate_free_promotion(session,tmp_path):
    doc,pipe=source(session,tmp_path)
    first=extract(session,pipe,doc)
    assert first.revision_status=='candidate'
    assert session.scalar(sa.select(sa.func.count(Unit.id)))==0
    revision=session.get(ExtractionRevision,first.revision_id)
    question=revision.questions[0]
    assert question['source_attempt_id'] is None
    assert len(question['parts'])==2
    assert question['common_stem'].count('Shared case')==1
    assert question['question_text']==''
    assert 'Explain recognition' not in question['question_text']
    assert question['answers']==[] and question['answer_status']=='missing'
    promote_revision(session,revision.id,None);session.commit()
    units=list(session.scalars(sa.select(Unit).where(Unit.current.is_(True))))
    assert len(units)==3
    repeated=extract(session,pipe,doc)
    assert repeated.revision_id==revision.id
    promote_revision(session,revision.id,None);session.commit()
    assert len(list(session.scalars(sa.select(Unit).where(Unit.current.is_(True)))))==3
    assert {u.id for u in units}==set(session.scalars(sa.select(Unit.id).where(Unit.current.is_(True))))


def test_failed_reextraction_preserves_current_and_reports_failure(session,tmp_path):
    doc,pipe=source(session,tmp_path)
    first=extract(session,pipe,doc)
    promote_revision(session,first.revision_id,None);session.commit()
    ids=set(session.scalars(sa.select(Unit.id).where(Unit.current.is_(True))))
    doc.doc_type_id='weightage';session.commit()
    with pytest.raises(Exception,match='profile|PROFILE'):
        extract(session,pipe,doc)
    session.refresh(doc)
    assert doc.current_revision_id==first.revision_id
    assert ids==set(session.scalars(sa.select(Unit.id).where(Unit.current.is_(True))))
    failed=session.scalar(sa.select(ExtractionRevision).where(ExtractionRevision.status=='failed'))
    assert failed.quality['outcome']=='unsupported_profile'


def test_machine_quality_keeps_answer_and_ordering_concerns_separate_from_marks(session,tmp_path):
    doc,pipe=source(session,tmp_path,doc_type='rtp',body='Question 1\n(a) Explain the detailed recognition criteria.\nQuestion 3\n(a) Explain the complete disclosure requirements.')
    doc.paper_id='s2023.P2';session.commit()
    result=extract(session,pipe,doc)
    quality=session.get(ExtractionRevision,result.revision_id).quality
    assert quality['outcome']=='needs_review'
    assert quality['answers']==quality['pairing']=='concern'
    assert quality['ordering']=='concern'
    assert quality['marks_choices']=='pending'
    assert quality['human_review']=='pending'


def test_separate_answer_document_retains_source_and_no_duplicate_questions(session,tmp_path):
    doc,pipe=source(session,tmp_path)
    answer,answer_pipe=source(session,tmp_path,doc_type='model_answer',body='Question 1\n(a) Recognition answer with the official criteria.\n(b) Numerical liability answer is 55000.')
    confirm_pair(session,doc.id,answer.id,1,'Official matching collection and paper confirmed')
    session.commit()
    answer_result=extract(session,answer_pipe,answer)
    answer_revision=session.get(ExtractionRevision,answer_result.revision_id)
    assert answer_revision.questions==[]
    promote_revision(session,answer_result.revision_id,None);session.commit()
    assert session.scalar(sa.select(sa.func.count(Unit.id)))==0
    result=extract(session,pipe,doc)
    question=session.get(ExtractionRevision,result.revision_id).questions[0]
    assert question['answer_status']=='complete'
    assert len(question['answers'])==1
    assert [part['question_part_id'] for part in question['answers'][0]['parts']]==[part['id'] for part in question['parts']]
    assert all(a['source_spans'][0]['document_sha256']==answer.sha256 for a in question['answers'])
    promote_revision(session,result.revision_id,None);session.commit()
    assert all(a.answer_document_id==answer.id for a in session.scalars(sa.select(UnitAnswer)))


def test_combined_papers_pair_only_matching_paper_ranges(session,tmp_path):
    question,pipe=source(session,tmp_path,pages=[
        'Question 1\n(a) Explain the accounting recognition criteria.\n(10 Marks)',
        'Question 1\n(a) Explain the financial risk assessment criteria.\n(10 Marks)'])
    answer,_=source(session,tmp_path,doc_type='model_answer',pages=[
        'Question 1\n(a) Accounting recognition follows the specified principles.',
        'Question 1\n(a) Financial risk assessment follows these different principles.'])
    for doc in [question,answer]:
        doc.paper_id=None
        doc.paper_page_ranges=[{'paper_id':f's2023.P{i}','page_start':i,'page_end':i} for i in [1,2]]
    session.commit()
    pair=confirm_pair(session,question.id,answer.id,1,'Confirmed combined collection and source ranges')
    session.commit()
    result=extract(session,pipe,question)
    revision=session.get(ExtractionRevision,result.revision_id)
    assert [q['paper_id'] for q in revision.questions]==['s2023.P1','s2023.P2']
    assert [q['label_path'] for q in revision.questions]==['s2023.P1/Q1','s2023.P2/Q1']
    assert all(q['answer_status']=='complete' for q in revision.questions)
    for page,q in enumerate(revision.questions,1):
        part=q['answers'][0]['parts'][0]
        assert part['source_spans'][0]['page_start']==page
        assert part['source_spans'][0]['document_sha256']==answer.sha256
    assert revision.quality['answers']=='pending'
    pair.status='rejected';session.commit()
    with pytest.raises(RevisionConflict,match='pair changed'):
        promote_revision(session,revision.id,None)
    session.rollback()
    assert session.get(Document,question.id).current_revision_id is None


def test_curator_resolves_ambiguous_answer_from_recorded_source_candidate(session,tmp_path,authenticated_client):
    doc,pipe=source(session,tmp_path,body='Question 1\n(a) Explain the recognition criteria.\n(10 Marks)')
    answer,_=source(session,tmp_path,doc_type='model_answer',pages=[
        'Question 1\n(a) First source candidate says recognition requires evidence.',
        'Question 1\n(a) Second source candidate says recognition requires a signed contract.'])
    confirm_pair(session,doc.id,answer.id,1,'Confirmed identical collection, paper and source roles')
    session.commit()
    result=extract(session,pipe,doc)
    original=session.get(ExtractionRevision,result.revision_id)
    group=next(group for group in original.questions[0]['pairing_candidates'] if group['label_path']=='Q1.a')
    assert group['status']=='ambiguous' and len(group['candidates'])==2
    selected=next(candidate for candidate in group['candidates'] if candidate['page_start']==2)
    url=f'/api/v1/extraction/revisions/{original.id}/corrections'
    body={'label_path':'Q1.a','answer_candidate_label':selected['label_path'],'reason':'Compared the repeated source labels and selected the second original page'}
    student=authenticated_client(role='student')
    assert student.post(url,json=body).status_code==403
    admin=authenticated_client(role='administrator')
    assert admin.post(url,json={**body,'answer_candidate_label':'unrecorded-source'}).status_code==422
    assert admin.post(url,json={'label_path':'Q1.a','answer_text':'Invented replacement','reason':'Cannot resolve a source by replacing its text'}).status_code==422
    response=admin.post(url,json=body)
    assert response.status_code==200,response.text
    corrected=session.get(ExtractionRevision,response.json()['id'])
    assert corrected.status=='candidate' and corrected.content_digest!=original.content_digest
    assert corrected.created_by is not None
    assert corrected.configuration['correction']['edits']=={'answer_candidate_label':selected['label_path']}
    part=corrected.questions[0]['answers'][0]['parts'][0]
    assert part['answer_text']==selected['answer_text']
    assert part['source_spans'][0]['document_sha256']==answer.sha256
    assert part['source_spans'][0]['page_start']==part['source_spans'][0]['page_end']==2
    assert original.questions[0]['pairing_candidates'][0]['status']=='ambiguous'
    assert doc.current_revision_id is None


def test_classification_requires_actual_quality_reviews_and_receives_complete_context(session,tmp_path,manifest,monkeypatch):
    from test_phase3_classification import prepare
    from caf_l3.pipeline import ClassificationPipeline
    release=prepare(session,manifest)
    question,pipe=source(session,tmp_path,body='Question 1\nUse discounting for both calculations in this shared case.\n(a) Calculate the first cash-flow value.\n(10 Marks)\n(b) Calculate the second cash-flow value.\n(10 Marks)')
    answer,_=source(session,tmp_path,doc_type='model_answer',body='Question 1\n(a) The first discounted cash-flow value is 100.\n(b) The second discounted cash-flow value is 200.')
    pair=confirm_pair(session,question.id,answer.id,9,'Matching model identities in the isolated fixture');session.commit()
    result=extract(session,pipe,question)
    promote_revision(session,result.revision_id,None);session.commit()
    question.extract_status='needs_review';session.commit()
    run=Run(stage='l3_classify',status='running',stats={});session.add(run);session.commit()
    pipeline=ClassificationPipeline(session,version_id=release.version_id)
    calls=[]
    original=pipeline.classifier.classify_unit
    def capture(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(pipeline.classifier,'classify_unit',capture)
    assert pipeline.run_classification(run.id,doc_id=question.id,use_llm=False).total_processed==0
    assert calls==[]
    revision=session.get(ExtractionRevision,result.revision_id)
    for dimension in ('metadata','questions','answers','pairing','ordering','marks_choices','readability','human_review'):
        session.add(ExtractionReview(revision_id=revision.id,actor_id=9,content_digest=revision.content_digest,
            dimension=dimension,status='passed',note='Reviewed deterministic isolated source fixture'))
    session.commit()
    assert pipeline.run_classification(run.id,doc_id=question.id,use_llm=False).total_processed==2
    assert all('shared case' in call['context_text'] and 'second cash-flow' in call['context_text'] for call in calls)
    assert calls[0]['answer_text'].endswith('100.') and calls[1]['answer_text'].endswith('200.')
    pair.status='rejected';session.commit()
    assert pipeline.run_classification(run.id,doc_id=question.id,use_llm=False,resume=False).total_processed==0
    assert len(calls)==2


@pytest.mark.parametrize('relation',['split','merged'])
def test_exact_ordered_split_merge_is_review_evidence_without_decision_transfer(session,tmp_path,relation):
    sentences=['Explain recognition criteria using the shared facts.','Calculate the liability from the supplied numerical facts.']
    whole='Question 1\nShared case information.\n(a) '+'\n'.join(sentences)
    parts='Question 1\nShared case information.\n(a) '+sentences[0]+'\n(b) '+sentences[1]
    before,after=(whole,parts) if relation=='split' else (parts,whole)
    doc,pipe=source(session,tmp_path,body=before)
    original=extract(session,pipe,doc)
    promote_revision(session,original.revision_id,None);session.commit()
    old_units=list(session.scalars(sa.select(Unit).where(Unit.is_gradable.is_(True))))
    decision=Decision(unit_fingerprint=old_units[0].fingerprint,actor_id=1,action='accept',payload={'original':True})
    session.add(decision);session.commit()
    successor,next_pipe=source(session,tmp_path,body=after,supersedes_document_id=doc.id)
    candidate=extract(session,next_pipe,successor)
    links=list(session.scalars(sa.select(ReconciliationLink).where(ReconciliationLink.revision_id==candidate.revision_id,
        ReconciliationLink.relation==relation)))
    assert len(links)==2
    assert all(link.evidence['requires_fresh_review'] for link in links)
    assert session.get(Decision,decision.id).payload=={'original':True}


def test_revision_stale_conflict_and_audited_correction_preserve_decisions(session,tmp_path,authenticated_client):
    doc,pipe=source(session,tmp_path)
    result=extract(session,pipe,doc)
    promote_revision(session,result.revision_id,None);session.commit()
    unit=session.scalar(sa.select(Unit).where(Unit.label_path=='Q1.a'))
    decision=Decision(unit_fingerprint=unit.fingerprint,actor_id=1,action='accept',payload={'original':True})
    session.add(decision);session.commit()
    admin=authenticated_client(role='administrator')
    correction={'label_path':'Q1.a','question_text':'Corrected complete question text with changed content.','reason':'Read against original page'}
    candidate=admin.post(f'/api/v1/extraction/revisions/{result.revision_id}/corrections',json=correction)
    assert candidate.status_code==200,candidate.text
    new_id=candidate.json()['id']
    newer=admin.post(f'/api/v1/extraction/revisions/{result.revision_id}/corrections',json={**correction,'question_text':'Another candidate with different content.'})
    assert newer.status_code==200,newer.text
    promoted=admin.post(f'/api/v1/extraction/revisions/{new_id}/promote',json={'expected_current_revision_id':result.revision_id})
    assert promoted.status_code==200,promoted.text
    conflict=admin.post(f'/api/v1/extraction/revisions/{newer.json()["id"]}/promote',json={'expected_current_revision_id':result.revision_id})
    assert conflict.status_code==409
    session.expire_all()
    assert session.get(Decision,decision.id).payload=={'original':True}
    assert session.get(Unit,unit.id).current is False
    assert session.scalar(sa.select(ReconciliationLink).where(ReconciliationLink.revision_id==new_id,ReconciliationLink.old_unit_id==unit.id)).relation=='changed'
    restored=extract(session,pipe,doc)
    restored_revision=session.get(ExtractionRevision,restored.revision_id)
    assert restored_revision.base_revision_id==new_id and restored_revision.id!=result.revision_id
    assert restored_revision.questions[0]['parts'][0]['question_text']!=correction['question_text']
    assert extract(session,pipe,doc).revision_id==restored_revision.id
    promote_revision(session,restored_revision.id,new_id);session.commit()
    assert extract(session,pipe,doc).revision_id==restored_revision.id


def test_quality_permissions_protected_page_bounds_and_no_path_disclosure(session,tmp_path,authenticated_client):
    doc,pipe=source(session,tmp_path)
    result=extract(session,pipe,doc)
    student=authenticated_client(role='student')
    reviewed=student.post(f'/api/v1/extraction/revisions/{result.revision_id}/reviews',json={'dimension':'readability','status':'passed','note':'Compared with original rendered page'})
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['content_digest']==session.get(ExtractionRevision,result.revision_id).content_digest
    assert student.post(f'/api/v1/extraction/revisions/{result.revision_id}/reviews',json={'dimension':'metadata','status':'passed','note':'Metadata'}).status_code==403
    assert student.post(f'/api/v1/extraction/revisions/{result.revision_id}/promote',json={'expected_current_revision_id':None}).status_code==403
    assert student.get(f'/api/v1/extraction/documents/{doc.id}/pages/1').headers['content-type']=='image/png'
    assert student.get(f'/api/v1/extraction/documents/{doc.id}/pages/0').status_code==422
    assert student.get(f'/api/v1/extraction/documents/{doc.id}/pages/2').status_code==422
    detail=student.get(f'/api/v1/extraction/revisions/{result.revision_id}').json()
    assert 'blob_path' not in str(detail)
    assert detail['source_documents'][0]['id']==doc.id
    student.cookies.clear()
    assert student.get(f'/api/v1/extraction/documents/{doc.id}/pages/1').status_code==401


def test_metadata_confirmation_records_actual_administrator_and_resolved_conflicts(session,tmp_path,authenticated_client):
    doc,_=source(session,tmp_path)
    doc.catalog_status='needs_curation'
    conflicts=[{'field':'paper_id','navigation':'s2023.P2','content':'s2023.P1'}]
    doc.metadata_evidence={'conflicts':conflicts};session.commit()
    student=authenticated_client(role='student')
    assert student.post(f'/api/v1/curate/documents/{doc.id}/confirm',json={'paper_id':'s2023.P1'}).status_code==403
    admin=authenticated_client(role='administrator')
    response=admin.post(f'/api/v1/curate/documents/{doc.id}/confirm',json={'paper_id':'s2023.P1'})
    assert response.status_code==200,response.text
    session.refresh(doc)
    assert doc.metadata_evidence['conflicts']==[]
    confirmation=doc.metadata_evidence['administrator_confirmation']
    assert confirmation['actor_id']==1 and confirmation['resolved_conflicts']==conflicts


def test_source_span_edits_and_stale_corrections_require_fresh_lineage(session,tmp_path,authenticated_client):
    doc,pipe=source(session,tmp_path)
    initial=extract(session,pipe,doc)
    promote_revision(session,initial.revision_id,None);session.commit()
    admin=authenticated_client(role='administrator')
    old=session.scalar(sa.select(Unit).where(Unit.label_path=='Q1.a'))
    candidate=admin.post(f'/api/v1/extraction/revisions/{initial.revision_id}/corrections',json={
        'label_path':'Q1.a','block_start':'p1-b4','block_end':'p1-b4','reason':'Correct the registered block bounds'})
    assert candidate.status_code==200,candidate.text
    new_id=candidate.json()['id']
    assert admin.post(f'/api/v1/extraction/revisions/{new_id}/promote',json={'expected_current_revision_id':initial.revision_id}).status_code==200
    stale=admin.post(f'/api/v1/extraction/revisions/{initial.revision_id}/corrections',json={
        'label_path':'Q1.a','question_text':'Obsolete correction','reason':'Old page'})
    assert stale.status_code==409
    session.expire_all()
    current=session.scalar(sa.select(Unit).where(Unit.label_path=='Q1.a',Unit.current.is_(True)))
    assert current.id!=old.id and current.fingerprint!=old.fingerprint
    assert current.block_start==current.block_end=='p1-b4'
    for payload in ({'question_text':None},{'page_start':None},{'block_end':None},{}):
        rejected=admin.post(f'/api/v1/extraction/revisions/{new_id}/corrections',json={'label_path':'Q1.a','reason':'Null invalid',**payload})
        assert rejected.status_code==422,rejected.text


def test_promotion_rejects_metadata_drift(session,tmp_path):
    doc,pipe=source(session,tmp_path)
    candidate=extract(session,pipe,doc)
    doc.paper_id='s2023.P2';session.commit()
    with pytest.raises(RevisionConflict,match='metadata changed'):
        promote_revision(session,candidate.revision_id,None)
    session.rollback()
    assert session.scalar(sa.select(sa.func.count(Unit.id)))==0


def test_combined_pdf_keeps_per_paper_identity_and_order(session,tmp_path):
    pdf=fitz.open()
    for name in ('Financial reporting question','Finance calculation question'):
        page=pdf.new_page();page.insert_text((40,120),f'Question 1\n{name} (100 Marks)',fontsize=11)
    store=BlobStore(get_settings().storage.blob_dir);data=pdf.tobytes();pdf.close()
    sha,path=store.put(data)
    doc=Document(sha256=sha,blob_path=str(path),bytes=len(data),origin='manual',course_level='final',provenance_status='verified',
        scheme_id='s2023',paper_id=None,attempt_id='2024-05',doc_type_id='question_paper',catalog_status='confirmed',
        paper_page_ranges=[{'paper_id':'s2023.P1','page_start':1,'page_end':1},{'paper_id':'s2023.P2','page_start':2,'page_end':2}])
    session.add(doc);session.commit()
    pipe=ExtractionPipeline(store,Path('profiles'),tmp_path/'overrides')
    summary=extract(session,pipe,doc)
    revision=session.get(ExtractionRevision,summary.revision_id)
    assert [q['paper_id'] for q in revision.questions]==['s2023.P1','s2023.P2']
    assert [q['label_path'] for q in revision.questions]==['s2023.P1/Q1','s2023.P2/Q1']
    promote_revision(session,revision.id,None);session.commit()
    assert {u.extraction_data['paper_id'] for u in session.scalars(sa.select(Unit))}=={'s2023.P1','s2023.P2'}


def test_concurrent_promotions_have_one_winner_and_keep_old_units(session,tmp_path,authenticated_client):
    from concurrent.futures import ThreadPoolExecutor
    from caf_db.engine import get_session_factory
    doc,pipe=source(session,tmp_path)
    original=extract(session,pipe,doc)
    promote_revision(session,original.revision_id,None);session.commit()
    admin=authenticated_client(role='administrator')
    candidates=[]
    for text in ('First replacement question text','Second replacement question text'):
        response=admin.post(f'/api/v1/extraction/revisions/{original.revision_id}/corrections',json={
            'label_path':'Q1.a','question_text':text,'reason':'Candidate from independent curator'})
        assert response.status_code==200,response.text
        candidates.append(response.json()['id'])
    def promote_one(key):
        with get_session_factory()() as db:
            try:
                promote_revision(db,key,original.revision_id);db.commit();return 'promoted'
            except RevisionConflict:
                db.rollback();return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes=list(workers.map(promote_one,candidates))
    assert sorted(outcomes)==['conflict','promoted']
    session.expire_all()
    assert session.scalar(sa.select(sa.func.count(ExtractionRevision.id)).where(ExtractionRevision.status=='current'))==1
    assert session.scalar(sa.select(sa.func.count(Unit.id)).where(Unit.current.is_(True)))==3


def test_concurrent_pair_confirmations_keep_one_confirmed_answer_source(session,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from caf_db.engine import get_session_factory
    from caf_db.models.extraction import DocumentPair
    question,_=source(session,tmp_path)
    answers=[source(session,tmp_path,doc_type='model_answer',body=f'Question 1\n(a) Official answer candidate {i}.')[0].id for i in (1,2)]
    def confirm_one(answer_id):
        with get_session_factory()() as db:
            try:
                confirm_pair(db,question.id,answer_id,1,'Matching source collection checked in this isolated test')
                db.commit();return 'confirmed'
            except ValueError as exc:
                db.rollback()
                assert 'competing' in str(exc)
                return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes=list(workers.map(confirm_one,answers))
    assert sorted(outcomes)==['confirmed','conflict']
    assert session.scalar(sa.select(sa.func.count(DocumentPair.id)).where(DocumentPair.status=='confirmed'))==1


def test_changed_source_bytes_reconcile_predecessor_without_deleting_publication(session,tmp_path):
    doc,pipe=source(session,tmp_path)
    original=extract(session,pipe,doc)
    promote_revision(session,original.revision_id,None);session.commit()
    old=session.scalar(sa.select(Unit).where(Unit.label_path=='Q1.a'))
    appearance=Appearance(unit_fingerprint=old.fingerprint,source_unit_id=old.id,doc_sha256=doc.sha256,
        attempt_id='2024-05',source_paper_id=doc.paper_id,doc_type_id='model_question',signal_class='practice',
        display_label=old.display_label,marks=old.marks,gist='Published original',page_start=old.page_start,page_end=old.page_end)
    session.add(appearance);session.commit()
    changed,other_pipe=source(session,tmp_path,body='Question 1\nShared facts have changed.\n(a) New question with different complete text.\n(10 Marks)',supersedes_document_id=doc.id)
    candidate=extract(session,other_pipe,changed)
    link=session.scalar(sa.select(ReconciliationLink).where(ReconciliationLink.revision_id==candidate.revision_id,ReconciliationLink.old_unit_id==old.id))
    assert link.relation=='changed' and link.evidence['published_review_required']
    promote_revision(session,candidate.revision_id,None);session.commit()
    session.expire_all()
    assert session.get(Appearance,appearance.id).status=='published'
    assert session.get(Unit,old.id).current is False
    assert session.get(Document,doc.id).superseded
