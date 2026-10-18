"""Original-page references, conservative cropping, and bounded verified raster reuse."""
import hashlib
from pathlib import Path

import fitz
from fastapi import HTTPException
import pytest

from caf_api.published_pages import RasterCache, page_bounds, question_pages, render_page
from caf_common.settings import get_settings
from caf_db.models.questions import PublishedQuestion, PublishedSource
from test_phase5_publication import suggestion, review
from test_phase3_release import manifest


def span(sha='a' * 64, start=1, end=1, first='p1-b1', last='p1-b2'):
    return dict(document_sha256=sha, page_start=start, page_end=end,
        block_start=first, block_end=last)


def source_pdf():
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    for y, text in [(80, 'Question 1'), (110, 'First sibling'), (240, 'OR second sibling'), (600, 'Unrelated next question')]:
        page.insert_text((60, y), text)
    return pdf


def test_references_include_root_siblings_and_recursive_answers_with_exact_source_hash():
    one = span(start=1, end=2)
    two = span(start=2, end=3)
    unknown = span(sha='b' * 64)
    row = PublishedQuestion(question_id='q1', source_ids=[8], content={
        'source_spans': [one, unknown], 'parts': [{'source_spans': [two], 'parts': []}],
        'answers': [{'source_spans': [two], 'parts': [{'source_spans': [one], 'parts': []}]}]})
    source = PublishedSource(id=8, sha256='a' * 64, page_count=3)
    assert [p.page for p in question_pages(row, [source], 'question')] == [1, 2, 3]
    assert [p.page for p in question_pages(row, [source], 'answer')] == [2, 3, 1]
    source.sha256 = 'c' * 64
    assert question_pages(row, [source], 'question') == []


def test_crop_unions_sibling_spans_and_unknown_bounds_retain_full_page():
    with source_pdf() as pdf:
        clip, marker = page_bounds(pdf, 1, [span(last='p1-b2'), span(first='p1-b3', last='p1-b3')])
        assert clip.x0 == 0 and clip.x1 == 600
        assert 40 < clip.y0 < 80 and 240 < clip.y1 < 300
        assert marker is not None
        # A boundary on an OR sibling with unavailable coordinates must retain it.
        clip, marker = page_bounds(pdf, 1, [span(), span(first=None, last=None)])
        assert clip == pdf[0].rect and marker is not None
        clip, marker = page_bounds(pdf, 1, [span(first='p1-b999')])
        assert clip == pdf[0].rect and marker is None


def test_raster_cache_is_byte_bounded_and_lru():
    cache = RasterCache(10)
    cache.put(('a',), b'1234')
    cache.put(('b',), b'5678')
    assert cache.get(('a',)) == b'1234'
    cache.put(('c',), b'9999')
    assert cache.get(('b',)) is None
    assert cache.size == 8
    cache.put(('large',), b'0' * 11)
    assert cache.size == 8 and cache.get(('large',)) is None


def test_render_warm_cache_rechecks_integrity_path_and_file_signature(monkeypatch, tmp_path):
    from caf_api import questions
    with source_pdf() as pdf:
        data = pdf.tobytes()
    sha = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(get_settings().storage, 'blob_dir', tmp_path)
    root = Path(get_settings().storage.blob_dir)
    path = root / sha[:2] / sha[2:4] / f'{sha}.pdf'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    source = PublishedSource(id=91, sha256=sha, approved_blob_path=str(path))
    calls = []
    original = questions.source_bytes

    def recorded(source):
        calls.append(source.id)
        return original(source)

    monkeypatch.setattr(questions, 'source_bytes', recorded)
    first = render_page(source, 1, [span(sha)])
    assert first.startswith(b'\x89PNG')
    assert render_page(source, 1, [span(sha)]) == first
    assert calls == [91]
    full = render_page(source, 1, [span(sha)], crop=False)
    # Full-page mode retains the source and the reliable start marker.
    pixmap = fitz.Pixmap(full)
    assert pixmap.height == 1200
    rgb = pixmap.pixel(76, 106)
    assert rgb[1] > rgb[0] and rgb[1] > rgb[2]
    with pytest.raises(HTTPException) as outside:
        render_page(source, 999, [span(sha)])
    assert outside.value.status_code == 422
    path.write_bytes(data + b'tampered')
    with pytest.raises(HTTPException) as mismatch:
        render_page(source, 1, [span(sha)])
    assert mismatch.value.status_code == 409
    source.approved_blob_path = str(root / 'arbitrary.pdf')
    with pytest.raises(HTTPException) as unsafe:
        render_page(source, 1, [span(sha)])
    assert unsafe.value.status_code == 404
    source.approved_blob_path = str(path)
    path.unlink()
    with pytest.raises(HTTPException) as missing:
        render_page(source, 1, [span(sha)])
    assert missing.value.status_code == 404


def test_published_page_route_checks_binding_and_permission(session, suggestion, authenticated_client):
    client = authenticated_client()
    review(session, suggestion)
    session.commit()
    result = client.get(f'/api/v1/questions/{suggestion.question_id}').json()
    assert result['question_pages']
    reference = result['question_pages'][0]
    response = client.get(reference['url'])
    assert response.status_code == 200, response.text
    assert 'no-store' in response.headers['cache-control']
    assert response.headers['content-type'] == 'image/png'
    assert client.get(reference['url'] + '?crop=false').status_code == 200
    assert client.get(reference['url'].rsplit('/', 1)[0] + '/999').status_code == 404
    assert client.get(reference['url'].replace('/question/', '/answer/')).status_code == 404
    assert client.get(reference['url'].replace('/question/', '/unknown/')).status_code == 422
    assert client.get(reference['url'].replace(f'/{reference["source_id"]}/', '/999999/')).status_code == 404
    from caf_db.models.classification import QuestionPublication
    publication = session.get(QuestionPublication, suggestion.question_id)
    publication.current_snapshot_id = None
    session.commit()
    # A previously warmed image must no longer be reachable after withdrawal.
    assert client.get(reference['url']).status_code == 404
