"""Synthetic Phase 6 reader publication, confined to the browser sandbox."""
import hashlib
import fitz
import sqlalchemy as sa
from caf_common.settings import get_settings
from caf_contracts.extraction import ExtractedQuestion
from caf_db.models.classification import ClassificationRevision, QuestionPublication, SuggestionRevision
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.questions import CorpusGeneration, PublishedQuestion, PublishedSource, QuestionOccurrence
from caf_db.models.ref import Node, TaxonomyVersion


def seed_reader(db, nodes):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((50, 70), 'SYNTHETIC BROWSER FIXTURE: shared case and both question parts.')
    data = pdf.tobytes()
    pdf.close()
    digest = hashlib.sha256(data).hexdigest()
    path = get_settings().storage.blob_dir / digest[:2] / digest[2:4] / f'{digest}.pdf'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    document = Document(sha256=digest, blob_path=str(path), bytes=len(data), origin='manual',
        scheme_id='s2023', paper_id='s2023.P1', doc_type_id='model_question', title='Synthetic undated reader fixture',
        catalog_status='confirmed', extract_status='ok')
    db.add(document)
    db.flush()
    span = dict(document_sha256=digest, page_start=1, page_end=1)
    question = ExtractedQuestion(question_id='synthetic.reader', content_revision='synthetic-reader.v1',
        paper_id='s2023.P1', source_attempt_id=None, display_label='Synthetic reader question',
        common_stem='Synthetic shared case: a company considers two accounting requirements.',
        question_text='Answer both parts using this complete case.', label_path='1', course_level='final',
        scheme_id='s2023', source_family='practice', source_collection_id='synthetic.undated',
        question_status='complete', readability_status='passed', review_status='reviewed', pairing_status='partial',
        parts=[dict(id='synthetic.reader.a', label='(a)', sequence=1, question_text='Synthetic first requirement.',
                    marks=4, source_spans=[span]),
               dict(id='synthetic.reader.b', label='(b)', sequence=2, question_text='Synthetic second requirement.',
                    marks=None, source_spans=[span])],
        answers=[dict(id='synthetic.reader.answer', question_part_id='synthetic.reader.a', sequence=1,
                      answer_text='SYNTHETIC READER ANSWER SENTINEL', source_spans=[span])],
        answer_status='partial', source_spans=[span], source_document_ids=[document.id])
    content = question.model_dump(mode='json')
    taxonomy_id = db.scalar(sa.select(TaxonomyVersion.id).order_by(TaxonomyVersion.id.desc()).limit(1))
    extraction = ExtractionRevision(document_id=document.id, run_id=1, status='current',
        content_digest=digest, profile_id='synthetic-browser-reader', configuration={'synthetic': True},
        quality={'outcome': 'synthetic-reviewed-fixture'}, questions=[content], parsed_units=[])
    db.add(extraction)
    db.flush()
    mappings = [dict(part_id=f'synthetic.reader.{part}', outcome='matched', primary_node_id=node.id,
        secondary_node_ids=[], evidence={'synthetic': True}, confidence=1, bucket='A', excluded=False)
        for part, node in zip(('a', 'b'), nodes[:2])]
    suggestion = SuggestionRevision(batch_key='synthetic-browser-reader', input_hash=digest,
        document_id=document.id, extraction_revision_id=extraction.id, question_id=question.question_id,
        taxonomy_version_id=taxonomy_id, run_id=1, experimental=False, context=content, candidates=[],
        mappings=mappings, provenance={'synthetic_browser_fixture': True})
    db.add(suggestion)
    db.flush()
    revision = ClassificationRevision(question_id=question.question_id, suggestion_revision_id=suggestion.id,
        extraction_revision_id=extraction.id, taxonomy_version_id=taxonomy_id, mappings=mappings,
        context=content, input_hash=digest, actor_id=1, blind=False)
    source = PublishedSource(document_id=document.id, sha256=digest, title=document.title,
        doc_type_id=document.doc_type_id, attempt_id=None, page_count=1, approved_blob_path=str(path))
    occurrence = QuestionOccurrence(identity_key='synthetic-browser-reader', question_id=question.question_id,
        paper_id='s2023.P1', attempt_id=None, source_family='practice', signal_class='practice',
        identity_status='confirmed', pairing_evidence={'synthetic_browser_fixture': True})
    db.add_all([revision, source, occurrence])
    db.flush()
    covered = []
    for node in nodes[:2]:
        current = node
        node_path = []
        while current:
            node_path.append(dict(id=current.id, name=current.name, level=current.level))
            current = db.get(Node, current.parent_id) if current.parent_id else None
        covered.append(dict(node_id=node.id, name=node.name, path=list(reversed(node_path))))
    generation = db.get(CorpusGeneration, 1)
    generation.generation += 1
    db.add(PublishedQuestion(id=revision.id, question_id=question.question_id,
        extraction_revision_id=extraction.id, taxonomy_version_id=taxonomy_id, occurrence_id=occurrence.id,
        publication_generation=generation.generation, content=content, mappings=mappings,
        covered_subtopics=covered, marks=dict(whole_question_marks=None, offered_marks=None,
            selectable_marks=None, allocations=[dict(part_id='synthetic.reader.a', marks=4,
                allocation_status='reviewed', choice_group=None,
                node_shares=[dict(node_id=nodes[0].id, share=1, attributed_marks=4)])],
            issues=['Part (b) marks unknown in this synthetic fixture.']), quality=extraction.quality,
        source_ids=[source.id], assets=[], search_text=' '.join([question.common_stem, question.question_text,
            *(node['name'] for node in covered)])))
    db.flush()
    db.add(QuestionPublication(question_id=question.question_id, document_id=document.id,
        current_revision_id=revision.id, current_snapshot_id=revision.id))
    db.flush()
    return dict(question_id=question.question_id, reader_part_id='synthetic.reader.a', source_id=source.id)
