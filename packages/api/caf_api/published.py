"""Published-content access rules shared by the question and page routers."""
import hashlib
from pathlib import Path
import re
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from caf_api.auth import Principal
from caf_common.settings import get_settings
from caf_db.models.app import Settings
from caf_db.models.classification import QuestionPublication
from caf_db.models.questions import PublishedQuestion, PublishedSource

HINDI_SCRIPT = '[\u0900-\u097f]'
HINDI_TITLE = r'(^|[^A-Za-z])hindi([^A-Za-z]|$)'


def includes_hindi(db: Session, account: Principal) -> bool:
    settings = db.get(Settings, account.id)
    return bool(settings and settings.include_hindi)


def require_question_language(db: Session, account: Principal, row: PublishedQuestion) -> None:
    if includes_hindi(db, account):
        return
    source_is_hindi = db.scalar(select(PublishedSource.id).where(
        PublishedSource.id.in_(row.source_ids), PublishedSource.title.op('~*')(HINDI_TITLE)).limit(1))
    if re.search(HINDI_SCRIPT, row.search_text) or source_is_hindi is not None:
        raise HTTPException(403, 'Hindi questions are hidden. Enable them in Profile preferences to read this question.')


def require_source_language(db: Session, account: Principal, source: PublishedSource) -> None:
    """Every question using a Hindi-titled source is hidden, so its raw pages are hidden too."""
    title = source.title or ''
    hindi = re.search(HINDI_TITLE, title, re.IGNORECASE) or re.search(HINDI_SCRIPT, title)
    if hindi and not includes_hindi(db, account):
        raise HTTPException(403, 'Hindi questions are hidden. Enable them in Profile preferences to read this source.')


def current_questions():
    return select(PublishedQuestion).join(QuestionPublication,
        QuestionPublication.current_snapshot_id == PublishedQuestion.id)


def current_question(db, question_id):
    row=db.scalar(current_questions().where(PublishedQuestion.question_id == question_id))
    if row is None:
        raise HTTPException(404,'published_question_not_found')
    return row


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
