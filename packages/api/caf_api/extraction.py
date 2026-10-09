"""Authenticated curator extraction workspace, immutable corrections and source access."""
import copy
import hashlib
from typing import Any
import pymupdf as fitz
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from caf_api.auth import Principal, require_account, require_admin
from caf_api.curate import get_curation_db
from caf_api.routes import get_operations_db
from caf_common.settings import get_settings
from caf_common.blob_store import BlobStore
from caf_contracts.extraction import (ExtractionDocument, RevisionSummary, RevisionDetail,
    PageResult, ExtractedQuestion, ReviewRequest, ReviewResult, PromoteRequest, PromoteResult,
    PairRequest, PairResult, ReconciliationResult, BlockResult, AssetResult, CorrectionRequest)
from caf_db.models.ingest import Document
from caf_db.models.core import ChangeLog
from caf_db.models.extraction import (ExtractionRevision, ExtractionReview, ContentBlock,
    ExtractionAsset, DocumentPair, ReconciliationLink)
from caf_l2.revisions import (promote_revision, RevisionConflict, confirm_pair, pair_identity,
    digest, flatten_snapshots, assemble_questions, reconcile, refresh_snapshot_digests, reviewed_quality, extraction_ready)

router = APIRouter(prefix='/api/v1/extraction', tags=['extraction review'], dependencies=[Depends(require_account)])


def found(db, model, key):
    row = db.get(model,key)
    if row is None:
        raise HTTPException(404,'Record not found')
    return row


def revision_value(row, db=None):
    return dict(id=row.id,document_id=row.document_id,base_revision_id=row.base_revision_id,status=row.status,
        content_digest=row.content_digest,profile_id=row.profile_id,quality=reviewed_quality(db,row) if db is not None else row.quality,created_at=row.created_at.isoformat())


def question_values(db,revision):
    quality=reviewed_quality(db,revision)
    ready=extraction_ready(db,revision)
    return [{**question,
        'question_status':'complete' if quality.get('questions')=='passed' else 'partial' if quality.get('questions')=='concern' else question.get('question_status','unknown'),
        'readability_status':quality.get('readability','pending'),
        'review_status':'reviewed' if ready else 'pending'} for question in revision.questions]


def page_query(db, query, model, page, page_size):
    count = db.scalar(sa.select(sa.func.count()).select_from(query.order_by(None).subquery()))
    items = list(db.scalars(query.offset((page-1)*page_size).limit(page_size)))
    return dict(items=[{c.name:row.__dict__[c.name] for c in model.__table__.columns} for row in items],
        total=count,page=page,page_size=page_size)


@router.get('/documents',response_model=PageResult[ExtractionDocument])
def documents(page: int = Query(1,ge=1),page_size: int = Query(25,ge=1,le=100),
              paper_id: str | None = None, attempt_id: str | None = None,
              db: Session = Depends(get_curation_db)):
    query = sa.select(Document).where(Document.superseded.is_(False)).order_by(Document.id.desc())
    if paper_id: query = query.where(Document.paper_id==paper_id)
    if attempt_id: query = query.where(Document.attempt_id==attempt_id)
    return page_query(db,query,Document,page,page_size)


@router.get('/documents/{document_id}/revisions',response_model=PageResult[RevisionSummary])
def revisions(document_id: int,page: int=Query(1,ge=1),page_size: int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    found(db,Document,document_id)
    query=sa.select(ExtractionRevision).where(ExtractionRevision.document_id==document_id).order_by(ExtractionRevision.id.desc())
    count=db.scalar(sa.select(sa.func.count()).select_from(query.order_by(None).subquery()))
    return dict(items=[revision_value(r,db) for r in db.scalars(query.offset((page-1)*page_size).limit(page_size))],total=count,page=page,page_size=page_size)


@router.get('/revisions/{revision_id}',response_model=RevisionDetail)
def revision_detail(revision_id:int,db:Session=Depends(get_curation_db)):
    row=found(db,ExtractionRevision,revision_id)
    ids={row.document_id}
    for question in row.questions:
        ids.update(question['source_document_ids'])
    sources=list(db.scalars(sa.select(Document).where(Document.id.in_(ids))))
    return {**revision_value(row,db),'configuration':row.configuration,'questions':question_values(db,row),
        'source_documents':[{'id':d.id,'sha256':d.sha256,'page_count':d.page_count} for d in sources]}


@router.get('/revisions/{revision_id}/questions',response_model=PageResult[ExtractedQuestion])
def questions(revision_id:int,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    row=found(db,ExtractionRevision,revision_id)
    return dict(items=question_values(db,row)[(page-1)*page_size:page*page_size],total=len(row.questions),page=page,page_size=page_size)


@router.get('/revisions/{revision_id}/blocks',response_model=PageResult[BlockResult])
def blocks(revision_id:int,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    found(db,ExtractionRevision,revision_id)
    return page_query(db,sa.select(ContentBlock).where(ContentBlock.revision_id==revision_id).order_by(ContentBlock.sequence),ContentBlock,page,page_size)


@router.get('/revisions/{revision_id}/assets',response_model=PageResult[AssetResult])
def assets(revision_id:int,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    found(db,ExtractionRevision,revision_id)
    return page_query(db,sa.select(ExtractionAsset).where(ExtractionAsset.revision_id==revision_id).order_by(ExtractionAsset.page,ExtractionAsset.id),ExtractionAsset,page,page_size)


@router.get('/revisions/{revision_id}/reconciliation',response_model=PageResult[ReconciliationResult])
def reconciliation(revision_id:int,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    found(db,ExtractionRevision,revision_id)
    return page_query(db,sa.select(ReconciliationLink).where(ReconciliationLink.revision_id==revision_id).order_by(ReconciliationLink.id),ReconciliationLink,page,page_size)


@router.get('/revisions/{revision_id}/reviews',response_model=PageResult[ReviewResult])
def reviews(revision_id:int,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    found(db,ExtractionRevision,revision_id)
    return page_query(db,sa.select(ExtractionReview).where(ExtractionReview.revision_id==revision_id).order_by(ExtractionReview.id.desc()),ExtractionReview,page,page_size)


@router.post('/revisions/{revision_id}/reviews',response_model=ReviewResult)
def review(revision_id:int,body:ReviewRequest,db:Session=Depends(get_curation_db),account:Principal=Depends(require_account)):
    row=found(db,ExtractionRevision,revision_id)
    db.execute(sa.text('SELECT pg_advisory_xact_lock(:document_id)'), {'document_id': row.document_id})
    if body.dimension=='metadata' and account.role!='administrator':
        raise HTTPException(403,'Administrator confirms metadata')
    value=ExtractionReview(revision_id=row.id,actor_id=account.id,content_digest=row.content_digest,**body.model_dump())
    db.add(value); db.commit(); db.refresh(value)
    return {key:value.__dict__[key] for key in ('id','revision_id','actor_id','content_digest','dimension','status','note')}


@router.post('/revisions/{revision_id}/promote',response_model=PromoteResult)
def promote(revision_id:int,body:PromoteRequest,db:Session=Depends(get_operations_db),admin:Principal=Depends(require_admin)):
    found(db,ExtractionRevision,revision_id)
    try:
        result=promote_revision(db,revision_id,body.expected_current_revision_id)
        db.add(ChangeLog(entity='extraction_revision',entity_id=str(revision_id),change='promoted',
            before={'current_revision_id':body.expected_current_revision_id},
            after={'current_revision_id':revision_id,'actor_id':admin.id},reason='Administrator accepted candidate revision'))
        db.commit()
        return result
    except RevisionConflict as exc:
        db.rollback(); raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        db.rollback(); raise HTTPException(422,str(exc)) from exc


@router.get('/documents/{document_id}/pairs',response_model=PageResult[PairResult])
def pairs(document_id:int,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_curation_db)):
    found(db,Document,document_id)
    return page_query(db,sa.select(DocumentPair).where(DocumentPair.question_document_id==document_id).order_by(DocumentPair.id),DocumentPair,page,page_size)


@router.post('/documents/{document_id}/pairs',response_model=PairResult)
def pair(document_id:int,body:PairRequest,db:Session=Depends(get_operations_db),admin:Principal=Depends(require_admin)):
    try:
        row=confirm_pair(db,document_id,body.answer_document_id,admin.id,body.evidence)
        db.add(ChangeLog(entity='document_pair',entity_id=str(row.id),change='confirmed',
            after={'actor_id':admin.id,'evidence':row.evidence},reason=body.evidence))
        db.commit()
        return {key:row.__dict__[key] for key in ('id','question_document_id','answer_document_id','status','evidence')}
    except ValueError as exc:
        db.rollback(); raise HTTPException(422,str(exc)) from exc


@router.delete('/pairs/{pair_id}',response_model=PairResult)
def revoke_pair(pair_id:int,db:Session=Depends(get_operations_db),admin:Principal=Depends(require_admin)):
    row=found(db,DocumentPair,pair_id)
    db.execute(sa.select(Document.id).where(Document.id==row.question_document_id).with_for_update())
    db.refresh(row)
    row.status='rejected'
    row.evidence={**row.evidence,'revoked_by':admin.id}
    db.add(ChangeLog(entity='document_pair',entity_id=str(row.id),change='rejected',after={'actor_id':admin.id}))
    db.commit()
    return {key:row.__dict__[key] for key in ('id','question_document_id','answer_document_id','status','evidence')}


def source_bytes(db,document_id):
    doc=found(db,Document,document_id)
    store=BlobStore(get_settings().storage.blob_dir)
    try:
        data = store.read(doc.sha256)
        if hashlib.sha256(data).hexdigest() != doc.sha256:
            raise HTTPException(404,'Registered source bytes unavailable')
        return data
    except FileNotFoundError as exc:
        raise HTTPException(404,'Registered source bytes unavailable') from exc


def source_pdf(db,document_id):
    try:
        return fitz.open(stream=source_bytes(db,document_id),filetype='pdf')
    except (FileNotFoundError,fitz.FileDataError) as exc:
        raise HTTPException(404,'Registered source bytes unavailable') from exc


@router.get('/documents/{document_id}/pdf',responses={200:{'content':{'application/pdf':{}}}})
def original_pdf(document_id:int,db:Session=Depends(get_curation_db)):
    return Response(source_bytes(db,document_id),media_type='application/pdf',
        headers={'Content-Disposition':f'inline; filename="document-{document_id}.pdf"'})


@router.get('/documents/{document_id}/pages/{page}',responses={200:{'content':{'image/png':{}}}})
def source_page(document_id:int,page:int,db:Session=Depends(get_curation_db)):
    with source_pdf(db,document_id) as pdf:
        if page < 1 or page > len(pdf):
            raise HTTPException(422,'Page outside source bounds')
        return Response(pdf[page-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).tobytes('png'),media_type='image/png')


@router.get('/assets/{asset_id}/image',responses={200:{'content':{'image/png':{}}}})
def source_asset(asset_id:int,db:Session=Depends(get_curation_db)):
    asset=found(db,ExtractionAsset,asset_id)
    revision=found(db,ExtractionRevision,asset.revision_id)
    with source_pdf(db,revision.document_id) as pdf:
        if asset.page < 1 or asset.page > len(pdf): raise HTTPException(422,'Asset page outside source bounds')
        source=pdf[asset.page-1]
        clip=fitz.Rect(asset.bbox) if asset.bbox else source.rect
        if clip.is_empty or not source.rect.contains(clip): raise HTTPException(422,'Asset crop outside source bounds')
        return Response(source.get_pixmap(matrix=fitz.Matrix(1.5,1.5),clip=clip).tobytes('png'),media_type='image/png')


@router.post('/revisions/{revision_id}/corrections',response_model=RevisionSummary)
def correction(revision_id:int,body:CorrectionRequest,db:Session=Depends(get_operations_db),admin:Principal=Depends(require_admin)):
    old=found(db,ExtractionRevision,revision_id)
    doc=db.scalar(sa.select(Document).where(Document.id==old.document_id).with_for_update().execution_options(populate_existing=True))
    if old.status == 'superseded' or old.status == 'failed' or (old.status == 'candidate' and old.base_revision_id != doc.current_revision_id):
        raise HTTPException(409,'Correction source is stale; select the current revision')
    roots=copy.deepcopy(old.parsed_units)
    nodes={n['label_path']:n for n in flatten_snapshots(roots)}
    node=nodes.get(body.label_path)
    if node is None: raise HTTPException(404,'Part label not found')
    edits=body.model_dump(exclude_unset=True,exclude={'reason','label_path'})
    if not edits or any(value is None for key,value in edits.items() if key!='marks'):
        raise HTTPException(422,'Corrections require concrete text or source bounds; null is allowed only to clear marks')
    if 'answer_candidate_label' in edits:
        candidates=[candidate for candidate in (node['answer'] or {}).get('candidates',[])
            if candidate['label_path']==edits['answer_candidate_label']]
        if len(candidates)!=1:
            raise HTTPException(422,'Select one recorded answer candidate with an unambiguous source label')
        candidate=candidates[0]
        if candidate['answer_doc_id'] is None:
            raise HTTPException(422,'Selected answer candidate has no registered source document')
        answer_doc=found(db,Document,candidate['answer_doc_id'])
        if answer_doc.catalog_status!='confirmed' or answer_doc.page_count is None or candidate['page_start'] is None or candidate['page_end'] is None or not 1<=candidate['page_start']<=candidate['page_end']<=answer_doc.page_count:
            raise HTTPException(422,'Selected answer candidate has no confirmed, bounded source')
        if not candidate['answer_text'] and not candidate['mcq_correct_option']:
            raise HTTPException(422,'Selected source candidate contains no available answer or MCQ key')
        node['answer'].update({key:value for key,value in candidate.items() if key!='label_path'})
        node['answer'].update(status='matched',pairing_method='curator_candidate',candidate_labels=[candidate['label_path']])
    elif 'answer_text' in edits and (node['answer'] or {}).get('status')=='ambiguous':
        raise HTTPException(422,'Resolve the actual source candidate before correcting an ambiguous answer')
    for key,value in edits.items():
        if key=='answer_candidate_label':
            continue
        elif key=='answer_text':
            if node['answer'] is None: raise HTTPException(422,'Pair an actual answer source before correcting its text')
            node['answer']['answer_text']=value
        else: node[key]=value
    if node['page_end'] < node['page_start'] or node['page_end'] > (doc.page_count or 0):
        raise HTTPException(422,'Correction pages outside source bounds')
    bound_blocks=[]
    for key in ('block_start','block_end'):
        block=db.scalar(sa.select(ContentBlock).where(ContentBlock.revision_id==old.id,ContentBlock.block_key==node[key]))
        if block is None or not node['page_start'] <= block.page <= node['page_end']:
            raise HTTPException(422,'Correction source block outside selected span')
        bound_blocks.append(block)
    if bound_blocks[0].sequence > bound_blocks[1].sequence:
        raise HTTPException(422,'Correction source blocks must be ordered')
    refresh_snapshot_digests(roots)
    configuration={**old.configuration,'correction':{'source_revision_id':old.id,'actor_id':admin.id,'reason':body.reason,'edits':edits,'label_path':body.label_path}}
    content_digest=digest({'configuration':configuration,'units':roots})
    existing=db.scalar(sa.select(ExtractionRevision).where(ExtractionRevision.document_id==doc.id,ExtractionRevision.content_digest==content_digest))
    if existing: return revision_value(existing)
    quality={**old.quality,**{k:'pending' for k in ('questions','answers','ordering','marks_choices','readability','human_review')},'outcome':'needs_review'}
    row=ExtractionRevision(document_id=doc.id,run_id=old.run_id,base_revision_id=doc.current_revision_id,content_digest=content_digest,
        profile_id=old.profile_id,configuration=configuration,quality=quality,parsed_units=roots,
        questions=assemble_questions(db,doc,roots,content_digest,old.quality['answers']!='not_applicable'),created_by=admin.id)
    for question in row.questions:
        question['assets']=[{**asset,'document_id':doc.id} for original in old.questions for asset in original['assets']
            if original['question_id']==question['question_id'] and question['source_spans'][0]['page_start']<=asset['page']<=question['source_spans'][0]['page_end']]
    db.add(row); db.flush()
    for block in db.scalars(sa.select(ContentBlock).where(ContentBlock.revision_id==old.id)):
        db.add(ContentBlock(revision_id=row.id,block_key=block.block_key,sequence=block.sequence,page=block.page,bbox=block.bbox,
            raw_text=block.raw_text,normalized_text=block.normalized_text,origin=block.origin))
    for asset in db.scalars(sa.select(ExtractionAsset).where(ExtractionAsset.revision_id==old.id)):
        db.add(ExtractionAsset(revision_id=row.id,page=asset.page,kind=asset.kind,bbox=asset.bbox,concerns=asset.concerns))
    reconcile(db,row); db.commit()
    return revision_value(row)
