"""Authenticated, publication-bound original pages with conservative line crops."""
from collections import OrderedDict
from pathlib import Path
import re
from threading import Lock
from typing import Literal

import fitz
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from caf_api.auth import Principal, require_account
from caf_common.settings import get_settings
from caf_contracts.questions import PublishedQuestionPage
from caf_db.engine import get_db_session
from caf_db.models.questions import PublishedQuestion, PublishedSource
from caf_l2.blocks import OCRUnavailableError, extract_raw_lines

PageKind = Literal['question', 'answer']
router = APIRouter(prefix='/api/v1', tags=['questions'], dependencies=[Depends(require_account)])


class RasterCache:
    """Small process-local LRU; never retains open PDFs or unbounded raster data."""

    def __init__(self, byte_budget: int = 48 * 1024 * 1024):
        self.byte_budget = byte_budget
        self.size = 0
        self.entries: OrderedDict[tuple, bytes] = OrderedDict()
        self.lock = Lock()

    def get(self, key: tuple) -> bytes | None:
        with self.lock:
            value = self.entries.get(key)
            if value is not None:
                self.entries.move_to_end(key)
            return value

    def put(self, key: tuple, value: bytes) -> None:
        with self.lock:
            old = self.entries.pop(key, None)
            if old is not None:
                self.size -= len(old)
            if len(value) > self.byte_budget:
                return
            self.entries[key] = value
            self.size += len(value)
            while self.size > self.byte_budget:
                _, removed = self.entries.popitem(last=False)
                self.size -= len(removed)


_rasters = RasterCache()


def source_spans(row: PublishedQuestion, kind: PageKind) -> list[dict]:
    """Keep the root and every sibling/OR part, never just the selected part."""
    spans = []

    def visit(parts):
        for part in parts:
            spans.extend(part['source_spans'])
            visit(part['parts'])

    if kind == 'question':
        spans.extend(row.content['source_spans'])
        visit(row.content['parts'])
    else:
        visit(row.content['answers'])
    return spans


def question_pages(row: PublishedQuestion, sources: list[PublishedSource], kind: PageKind) -> list[PublishedQuestionPage]:
    by_hash = {source.sha256: source for source in sources if source.id in row.source_ids}
    seen = set()
    pages = []
    for span in source_spans(row, kind):
        source = by_hash.get(span['document_sha256'])
        if source is None:
            continue
        for page in range(span['page_start'], span['page_end'] + 1):
            key = (source.id, page)
            if key in seen or (source.page_count is not None and page > source.page_count):
                continue
            seen.add(key)
            pages.append(PublishedQuestionPage(source_id=source.id, page=page,
                url=f'/api/v1/questions/{row.question_id}/pages/{kind}/{source.id}/{page}'))
    return pages


def source_signature(source: PublishedSource) -> tuple:
    """Recheck the approved content-addressed path and file identity on every hit."""
    if not re.fullmatch('[0-9a-f]{64}', source.sha256):
        raise HTTPException(404, 'published_source_unavailable')
    base = Path(get_settings().storage.blob_dir).resolve()
    expected = (base / source.sha256[:2] / source.sha256[2:4] / f'{source.sha256}.pdf').resolve()
    if Path(source.approved_blob_path).resolve() != expected or not expected.is_relative_to(base):
        raise HTTPException(404, 'published_source_unavailable')
    try:
        stat = expected.stat()
    except FileNotFoundError as exc:
        raise HTTPException(404, 'published_source_unavailable') from exc
    return (source.sha256, str(expected), stat.st_dev, stat.st_ino, stat.st_size,
        stat.st_mtime_ns, stat.st_ctime_ns)


def page_bounds(pdf: fitz.Document, page: int, spans: list[dict]) -> tuple[fitz.Rect, fitz.Rect | None]:
    """Use precisely the extractor's block IDs; unknown boundaries keep the full page."""
    target = pdf[page - 1]
    relevant = [span for span in spans if span['page_start'] <= page <= span['page_end']]
    try:
        lines = extract_raw_lines(pdf, ignored_pages=set(range(1, len(pdf) + 1)) - {page})
    except OCRUnavailableError:
        return target.rect, None
    blocks = {line.block_id: fitz.Rect(line.bbox) for _, _, _, line in lines}
    starts, ends = [], []
    first = relevant[0] if relevant else None
    highlight = blocks.get(first['block_start']) if first and first['page_start'] == page else None
    for span in relevant:
        if page == span['page_start']:
            start = blocks.get(span['block_start'])
            if start is None:
                return target.rect, highlight
            starts.append(start.y0)
        else:
            starts.append(target.rect.y0)
        if page == span['page_end']:
            end = blocks.get(span['block_end'])
            if end is None:
                return target.rect, highlight
            ends.append(end.y1)
        else:
            ends.append(target.rect.y1)
    if not starts or min(starts) >= max(ends):
        return target.rect, None
    clip = fitz.Rect(target.rect.x0, max(target.rect.y0, min(starts) - 16),
        target.rect.x1, min(target.rect.y1, max(ends) + 16))
    return clip, highlight


def render_page(source: PublishedSource, page: int, spans: list[dict], crop: bool = True) -> bytes:
    from caf_api.questions import source_bytes

    signature = source_signature(source)
    span_key = tuple((span['page_start'], span['page_end'], span['block_start'], span['block_end']) for span in spans)
    key = (signature, page, span_key, crop)
    cached = _rasters.get(key)
    if cached is not None:
        return cached
    data = source_bytes(source)  # Hash verification is mandatory on every new file signature.
    try:
        with fitz.open(stream=data, filetype='pdf') as pdf:
            if page < 1 or page > len(pdf):
                raise HTTPException(422, 'page_outside_published_source')
            target = pdf[page - 1]
            bounds, highlight = page_bounds(pdf, page, spans)
            clip = bounds if crop else target.rect
            if highlight is not None:
                # A margin marker identifies the start without covering original text.
                target.draw_rect(fitz.Rect(max(0, highlight.x0 - 10), highlight.y0,
                    max(2, highlight.x0 - 6), highlight.y1), color=(0.1, 0.5, 0.25), fill=(0.1, 0.5, 0.25))
            raster = target.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=clip).tobytes('png')
    except fitz.FileDataError as exc:
        raise HTTPException(404, 'published_source_unavailable') from exc
    # A concurrently replaced file must never populate its old verified cache key.
    if source_signature(source) == signature:
        _rasters.put(key, raster)
    return raster


@router.get('/questions/{question_id}/pages/{kind}/{source_id}/{page}',
    responses={200: {'content': {'image/png': {}}}})
def published_question_page(question_id: str, kind: PageKind, source_id: int, page: int,
    crop: bool = True, db: Session = Depends(get_db_session), account: Principal = Depends(require_account)):
    from caf_api.questions import approved_source, current_question, require_question_language

    row = current_question(db, question_id)
    require_question_language(db, account, row)
    source = approved_source(db, source_id)
    if not any(reference.source_id == source_id and reference.page == page
        for reference in question_pages(row, [source], kind)):
        raise HTTPException(404, 'question_source_page_not_found')
    spans = [span for span in source_spans(row, kind) if span['document_sha256'] == source.sha256]
    return Response(render_page(source, page, spans, crop), media_type='image/png',
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
