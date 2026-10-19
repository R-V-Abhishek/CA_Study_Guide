"""Authenticated published content, metadata search and hash-bound source access."""
import hashlib
from pathlib import Path
import re
import fitz
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session
from caf_api.auth import Principal, require_account
from caf_common.settings import get_settings
from caf_contracts.extraction import PageResult
from caf_contracts.questions import (AppearanceResolution, OccurrenceResult, PublishedAssetResult,
    PublishedSourceResult, QuestionResult, QuestionSummary, SearchResult, PrivateNoteResult)
from caf_db.engine import get_db_session
from caf_db.models.app import Note, Settings
from caf_db.models.classification import ClassificationDispute, ClassificationVerification, QuestionPublication
from caf_db.models.core import Appearance
from caf_db.models.questions import PublishedQuestion, PublishedSource, QuestionOccurrence
from caf_db.models.ref import Node

router=APIRouter(prefix='/api/v1', tags=['questions'], dependencies=[Depends(require_account)])
HINDI_SCRIPT = '[\u0900-\u097f]'
HINDI_TITLE = r'(^|[^A-Za-z])hindi([^A-Za-z]|$)'


def includes_hindi(db: Session, account: Principal) -> bool:
    settings = db.get(Settings, account.id)
    return bool(settings and settings.include_hindi)


def hindi_source():
    return select(PublishedSource.id).where(
        PublishedQuestion.source_ids.contains(func.jsonb_build_array(PublishedSource.id)),
        PublishedSource.title.op('~*')(HINDI_TITLE)).exists()


def require_question_language(db: Session, account: Principal, row: PublishedQuestion) -> None:
    if includes_hindi(db, account):
        return
    source_is_hindi = db.scalar(select(PublishedSource.id).where(
        PublishedSource.id.in_(row.source_ids), PublishedSource.title.op('~*')(HINDI_TITLE)).limit(1))
    if re.search(HINDI_SCRIPT, row.search_text) or source_is_hindi is not None:
        raise HTTPException(403, 'Hindi questions are hidden. Enable them in Profile preferences to read this question.')


def current_questions():
    return select(PublishedQuestion).join(QuestionPublication,
        QuestionPublication.current_snapshot_id == PublishedQuestion.id)


def current_question(db, question_id):
    row=db.scalar(current_questions().where(PublishedQuestion.question_id == question_id))
    if row is None:
        raise HTTPException(404,'published_question_not_found')
    return row


def source_result(source):
    return PublishedSourceResult(id=source.id,sha256=source.sha256,title=source.title,
        doc_type_id=source.doc_type_id,attempt_id=source.attempt_id,page_count=source.page_count,
        url=f'/api/v1/published-sources/{source.id}',page_url=f'/api/v1/published-sources/{source.id}/pages/{{page}}')


@router.get('/questions/{question_id}',response_model=QuestionResult)
def question(question_id: str, db:Session=Depends(get_db_session), account:Principal=Depends(require_account)):
    row=current_question(db,question_id)
    require_question_language(db, account, row)
    sources=list(db.scalars(select(PublishedSource).where(PublishedSource.id.in_(row.source_ids)).order_by(PublishedSource.id)))
    occurrence=db.get(QuestionOccurrence,row.occurrence_id)
    from caf_api.published_pages import question_pages
    return QuestionResult(question_id=row.question_id,snapshot_id=row.id,classification_revision_id=row.id,
        extraction_revision_id=row.extraction_revision_id,taxonomy_version_id=row.taxonomy_version_id,
        publication_generation=row.publication_generation,content=row.content,mappings=row.mappings,
        covered_subtopics=row.covered_subtopics,marks=row.marks,sources=[source_result(source) for source in sources],
        question_pages=question_pages(row,sources,'question'),answer_pages=question_pages(row,sources,'answer'),
        assets=[PublishedAssetResult(**asset,url=f'/api/v1/published-assets/{asset["id"]}') for asset in row.assets],
        verification_count=db.scalar(select(func.count()).select_from(ClassificationVerification).where(
            ClassificationVerification.revision_id == row.id,ClassificationVerification.active.is_(True))) or 0,
        open_disputes=db.scalar(select(func.count()).select_from(ClassificationDispute).where(
            ClassificationDispute.revision_id == row.id,ClassificationDispute.status == 'open')) or 0,
        extraction_quality=row.quality,occurrence=OccurrenceResult(id=occurrence.id,canonical_occurrence_id=occurrence.canonical_occurrence_id,question_id=occurrence.question_id,paper_id=occurrence.paper_id,attempt_id=occurrence.attempt_id,source_family=occurrence.source_family,signal_class=occurrence.signal_class,series=occurrence.series,identity_status=occurrence.identity_status,pairing_evidence=occurrence.pairing_evidence))


def question_summary(row,subtopic_id=None):
    content=row.content
    mapped = {mapping['part_id'] for mapping in row.mappings
              if mapping['outcome']=='matched' and not mapping['excluded'] and
              (subtopic_id is None or mapping['primary_node_id']==subtopic_id or
               subtopic_id in mapping['secondary_node_ids'])}
    matched_parts=[]
    seen=set()
    def append_part(part_id,label):
        if part_id in mapped and part_id not in seen:
            seen.add(part_id)
            matched_parts.append({'id':part_id,'label':label})
    def visit(parts):
        for part in parts:
            append_part(part['id'],part['label_path'] or part['label'])
            visit(part['parts'])
    append_part(content['question_id'],content['display_label'])
    visit(content['parts'])
    return QuestionSummary(question_id=row.question_id,snapshot_id=row.id,paper_id=content['paper_id'],
        attempt_id=content['source_attempt_id'],display_label=content['display_label'],question_text=content['question_text'],
        common_stem=content['common_stem'],answer_status=content['answer_status'],source_family=content['source_family'],
        covered_subtopics=row.covered_subtopics,marks=row.marks,matched_parts=matched_parts)


def filtered_questions(paper_id,subtopic_id,attempt_id,source_family,answer_status,q=None,include_hindi=False):
    statement=current_questions()
    if not include_hindi:
        statement=statement.where(PublishedQuestion.search_text.op('!~')(HINDI_SCRIPT), ~hindi_source())
    for field,value in [('paper_id',paper_id),('source_attempt_id',attempt_id),('source_family',source_family),('answer_status',answer_status)]:
        if value is not None:
            statement=statement.where(PublishedQuestion.content[field].astext == value)
    if subtopic_id:
        statement=statement.where(PublishedQuestion.covered_subtopics.contains([{'node_id':subtopic_id}]))
    if q:
        vector=func.to_tsvector(literal_column("'english'"),PublishedQuestion.search_text)
        statement=statement.where(vector.op('@@')(func.websearch_to_tsquery(literal_column("'english'"),q)))
    return statement


def page_questions(db,statement,page,page_size,subtopic_id=None):
    total=db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows=db.scalars(statement.order_by(PublishedQuestion.question_id).offset((page-1)*page_size).limit(page_size))
    return dict(items=[question_summary(row,subtopic_id) for row in rows],total=total,page=page,page_size=page_size)


@router.get('/questions',response_model=PageResult[QuestionSummary])
def questions(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),paper_id:str|None=None,
        subtopic_id:str|None=None,attempt_id:str|None=None,source_family:str|None=None,answer_status:str|None=None,
        db:Session=Depends(get_db_session),account:Principal=Depends(require_account)):
    return page_questions(db,filtered_questions(paper_id,subtopic_id,attempt_id,source_family,answer_status,
        include_hindi=includes_hindi(db,account)),page,page_size,subtopic_id)


@router.get('/search',response_model=SearchResult)
def search(q:str=Query(min_length=1,max_length=500),page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),
        paper_id:str|None=None,subtopic_id:str|None=None,attempt_id:str|None=None,source_family:str|None=None,
        answer_status:str|None=None,include_notes:bool=False,account:Principal=Depends(require_account),db:Session=Depends(get_db_session)):
    result=page_questions(db,filtered_questions(paper_id,subtopic_id,attempt_id,source_family,answer_status,q,
        include_hindi=includes_hindi(db,account)),page,page_size,subtopic_id)
    result['notes']=[]
    if include_notes:
        notes=select(Note).where(Note.user_id==account.id,
            func.to_tsvector(literal_column("'english'"),Note.body).op('@@')(func.websearch_to_tsquery(literal_column("'english'"),q)))
        if subtopic_id:
            notes=notes.where(Note.node_id==subtopic_id)
        if paper_id:
            notes=notes.join(Node,Node.id==Note.node_id).where(Node.paper_id==paper_id)
        result['notes']=[PrivateNoteResult(node_id=note.node_id,content=note.body) for note in
            db.scalars(notes.order_by(Note.node_id).offset((page-1)*page_size).limit(page_size))]
    return SearchResult(**result)


@router.get('/appearances/{appearance_id}',response_model=AppearanceResolution)
def appearance(appearance_id:int,db:Session=Depends(get_db_session)):
    row=db.get(Appearance,appearance_id)
    if row is None or row.status != 'published':
        raise HTTPException(404,'published_appearance_not_found')
    bound=db.scalar(current_questions().where(PublishedQuestion.question_id==row.question_id)) if row.question_id else None
    return AppearanceResolution(appearance_id=row.id,question_id=row.question_id if bound else None,
        part_id=row.part_id if bound else None,provenance_limitation=None if bound else 'Legacy appearance has no reliable complete-question revision binding')


def approved_source(db,source_id):
    source=db.get(PublishedSource,source_id)
    referenced=db.scalar(current_questions().where(PublishedQuestion.source_ids.contains([source_id])).limit(1))
    if source is None or referenced is None:
        raise HTTPException(404,'published_source_not_found')
    return source


def source_bytes(source):
    """Only read the recorded content-addressed PDF inside the configured store."""
    if not re.fullmatch('[0-9a-f]{64}',source.sha256):
        raise HTTPException(404,'published_source_unavailable')
    base=Path(get_settings().storage.blob_dir).resolve()
    expected=(base/source.sha256[:2]/source.sha256[2:4]/f'{source.sha256}.pdf').resolve()
    approved=Path(source.approved_blob_path).resolve()
    if approved != expected or not expected.is_relative_to(base):
        raise HTTPException(404,'published_source_unavailable')
    try:
        data=expected.read_bytes()
    except FileNotFoundError as exc:
        raise HTTPException(404,'published_source_unavailable') from exc
    if hashlib.sha256(data).hexdigest()!=source.sha256:
        raise HTTPException(409,'published_source_hash_mismatch')
    return data


@router.get('/published-sources/{source_id}',responses={200:{'content':{'application/pdf':{}}}})
def source_file(source_id:int,db:Session=Depends(get_db_session)):
    return Response(source_bytes(approved_source(db,source_id)),media_type='application/pdf',headers={'Cache-Control':'private, no-store'})


def source_image(source,page,bbox=None):
    try:
        with fitz.open(stream=source_bytes(source),filetype='pdf') as pdf:
            if page<1 or page>len(pdf):
                raise HTTPException(422,'page_outside_published_source')
            target=pdf[page-1]
            clip=fitz.Rect(bbox) if bbox else target.rect
            if clip.is_empty or not target.rect.contains(clip):
                raise HTTPException(422,'asset_outside_published_source')
            return Response(target.get_pixmap(matrix=fitz.Matrix(1.5,1.5),clip=clip).tobytes('png'),media_type='image/png')
    except fitz.FileDataError as exc:
        raise HTTPException(404,'published_source_unavailable') from exc


@router.get('/published-sources/{source_id}/pages/{page}',responses={200:{'content':{'image/png':{}}}})
def source_page(source_id:int,page:int,db:Session=Depends(get_db_session)):
    return source_image(approved_source(db,source_id),page)


@router.get('/published-assets/{asset_id}',responses={200:{'content':{'image/png':{}}}})
def asset_image(asset_id:str,db:Session=Depends(get_db_session)):
    if not re.fullmatch(r'\d+:\d+',asset_id):
        raise HTTPException(404,'published_asset_not_found')
    snapshot_id,index=(int(value) for value in asset_id.split(':'))
    row=db.scalar(current_questions().where(PublishedQuestion.id==snapshot_id))
    if row is None or index>=len(row.assets):
        raise HTTPException(404,'published_asset_not_found')
    asset=row.assets[index]
    return source_image(approved_source(db,asset['source_id']),asset['page'],asset.get('bbox'))
