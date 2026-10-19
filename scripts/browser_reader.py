"""Synthetic Phase 6 reader publication, confined to the browser sandbox."""
import hashlib
import textwrap
import fitz
import sqlalchemy as sa
from caf_common.settings import get_settings
from caf_contracts.extraction import ExtractedQuestion
from caf_db.models.classification import ClassificationRevision, QuestionPublication, SuggestionRevision
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.questions import CorpusGeneration, PublishedQuestion, PublishedSource, QuestionOccurrence
from caf_db.models.ref import Node, TaxonomyVersion


def reader_stem(scenario):
    stem = 'Synthetic shared case: a company considers two accounting requirements.'
    if scenario == 'complete':
        stem += '\n\n' + '\n\n'.join(
            f'Case paragraph {number}: The company considers recognition, measurement, disclosure '
            'and the supporting evidence. Read this information before answering either part.'
            for number in range(1, 17)
        )
        stem += '\n\n| Item | Current year | Previous year | Evidence |\n| --- | --- | --- | --- |\n'
        stem += '| Revenue | 100 | 80 | Synthetic contract |\n| Liability | 40 | 30 | Synthetic obligation |'
    return stem


def seed_reader(db, nodes, *, scenario='partial'):
    if get_settings().app.env != 'test':
        raise RuntimeError('Synthetic reader fixtures require the isolated test environment')
    if scenario not in {'partial', 'complete', 'missing'}:
        raise ValueError('Unknown synthetic reader scenario')
    question_id = 'synthetic.reader' + ('' if scenario == 'partial' else '.' + scenario)
    stem = reader_stem(scenario)
    source_text = (f'SYNTHETIC BROWSER FIXTURE ({scenario} answer)\n\n' + stem +
                   '\n\nAnswer both parts using this complete case.\n'
                   '(a) Synthetic first requirement. (4 marks)\n'
                   '(b) Synthetic second requirement. (Marks unknown)\n\n')
    if scenario != 'missing':
        source_text += 'Answer (a): SYNTHETIC READER ANSWER SENTINEL\n'
    if scenario == 'complete':
        source_text += 'Answer (b): Synthetic complete answer for part (b).\n'
    lines = [line for paragraph in source_text.splitlines()
             for line in (textwrap.wrap(paragraph, width=85) or [''])]
    with fitz.open() as pdf:
        for offset in range(0, len(lines), 45):
            page = pdf.new_page()
            remaining = page.insert_textbox((50, 60, 545, 780), '\n'.join(lines[offset:offset + 45]), fontsize=11)
            if remaining < 0:
                raise ValueError('Synthetic source page overflowed')
        page_count = pdf.page_count
        data = pdf.tobytes()
    digest = hashlib.sha256(data).hexdigest()
    path = get_settings().storage.blob_dir / digest[:2] / digest[2:4] / f'{digest}.pdf'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    document = Document(sha256=digest, blob_path=str(path), bytes=len(data), origin='manual',
        scheme_id='s2023', paper_id='s2023.P1', doc_type_id='model_question',
        title=f'Synthetic undated reader fixture — {scenario} answer', page_count=page_count,
        catalog_status='confirmed', extract_status='ok')
    db.add(document)
    db.flush()
    span = dict(document_sha256=digest, page_start=1, page_end=page_count)
    answers = [] if scenario == 'missing' else [dict(
        id=question_id + '.answer', question_part_id=question_id + '.a', sequence=1,
        answer_text='SYNTHETIC READER ANSWER SENTINEL', source_spans=[span])]
    if scenario == 'complete':
        answers.append(dict(id=question_id + '.answer.b', question_part_id=question_id + '.b',
            sequence=2, answer_text='Synthetic complete answer for part (b).', source_spans=[span]))
    question = ExtractedQuestion(question_id=question_id, content_revision='synthetic-reader.v1',
        paper_id='s2023.P1', source_attempt_id=None,
        display_label='Synthetic reader question' if scenario == 'partial' else f'Synthetic reader question — {scenario} answer',
        common_stem=stem,
        question_text='Answer both parts using this complete case.', label_path='1', course_level='final',
        scheme_id='s2023', source_family='practice', source_collection_id='synthetic.undated',
        question_status='complete', readability_status='passed', review_status='reviewed',
        pairing_status='matched' if scenario == 'complete' else scenario,
        parts=[dict(id=question_id + '.a', label='(a)', sequence=1, question_text='Synthetic first requirement.',
                    marks=4, source_spans=[span]),
               dict(id=question_id + '.b', label='(b)', sequence=2, question_text='Synthetic second requirement.',
                    marks=None, source_spans=[span])],
        answers=answers, answer_status=scenario, source_spans=[span], source_document_ids=[document.id])
    content = question.model_dump(mode='json')
    taxonomy_id = db.scalar(sa.select(TaxonomyVersion.id).order_by(TaxonomyVersion.id.desc()).limit(1))
    extraction = ExtractionRevision(document_id=document.id, run_id=1, status='current',
        content_digest=digest, profile_id='synthetic-browser-reader', configuration={'synthetic': True},
        quality={'outcome': 'synthetic-reviewed-fixture'}, questions=[content], parsed_units=[])
    db.add(extraction)
    db.flush()
    mappings = [dict(part_id=f'{question_id}.{part}', outcome='matched', primary_node_id=node.id,
        secondary_node_ids=[], evidence={'synthetic': True}, confidence=1, bucket='A', excluded=False)
        for part, node in zip(('a', 'b'), nodes[:2])]
    suggestion = SuggestionRevision(batch_key='synthetic-browser-reader-' + scenario, input_hash=digest,
        document_id=document.id, extraction_revision_id=extraction.id, question_id=question.question_id,
        taxonomy_version_id=taxonomy_id, run_id=1, experimental=False, context=content, candidates=[],
        mappings=mappings, provenance={'synthetic_browser_fixture': True})
    db.add(suggestion)
    db.flush()
    revision = ClassificationRevision(question_id=question.question_id, suggestion_revision_id=suggestion.id,
        extraction_revision_id=extraction.id, taxonomy_version_id=taxonomy_id, mappings=mappings,
        context=content, input_hash=digest, actor_id=1, blind=False)
    source = PublishedSource(document_id=document.id, sha256=digest, title=document.title,
        doc_type_id=document.doc_type_id, attempt_id=None, page_count=page_count, approved_blob_path=str(path))
    occurrence = QuestionOccurrence(identity_key='synthetic-browser-reader-' + scenario, question_id=question.question_id,
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
            selectable_marks=None, allocations=[dict(part_id=question_id + '.a', marks=4,
                allocation_status='reviewed', choice_group=None,
                node_shares=[dict(node_id=nodes[0].id, share=1, attributed_marks=4)])],
            issues=['Part (b) marks unknown in this synthetic fixture.']), quality=extraction.quality,
        source_ids=[source.id], assets=[], search_text=' '.join([question.common_stem, question.question_text,
            *(node['name'] for node in covered)])))
    db.flush()
    db.add(QuestionPublication(question_id=question.question_id, document_id=document.id,
        current_revision_id=revision.id, current_snapshot_id=revision.id))
    db.flush()
    return dict(question_id=question.question_id, reader_part_id=question_id + '.a', source_id=source.id)
