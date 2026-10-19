"""Whole-question assembly and transactional, conservative extraction promotion."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session
from caf_contracts.extraction import ExtractedQuestion
from caf_db.models.ingest import Document, Unit, UnitAnswer, DiscoveredLink
from caf_db.models.extraction import ExtractionRevision, ReconciliationLink, DocumentPair
from caf_db.models.core import Appearance
from caf_l2.segmenter import ParsedUnit
from caf_l2.pairing import PairedAnswer, flatten_units


class RevisionConflict(ValueError):
    """Current content changed since this candidate was built."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def family(doc_type: str | None) -> str:
    return {'mtp_question':'mock','mtp_answer':'mock','model_question':'model','model_answer':'model',
            'exam':'examination','question_paper':'examination','suggested_answer':'examination',
            'case_scenarios':'ibs'}.get(doc_type, doc_type or 'unknown')


def pair_identity(doc: Document) -> tuple:
    return (doc.course_level, doc.scheme_id, doc.paper_id, family(doc.doc_type_id),
            doc.attempt_id, doc.collection_id, doc.series, doc.part)


def confirm_pair(session: Session, question_id: int, answer_id: int, actor_id: int, evidence: str) -> DocumentPair:
    for document_id in sorted({question_id, answer_id}):
        session.execute(sa.text('SELECT pg_advisory_xact_lock(:document_id)'), {'document_id': document_id})
    # The question row serialises competing confirmations with extraction promotion.
    q = session.scalar(sa.select(Document).where(Document.id==question_id).with_for_update().execution_options(populate_existing=True))
    a = session.get(Document, answer_id, populate_existing=True)
    if q is None or a is None:
        raise ValueError('Pair documents must exist')
    if question_id == answer_id or pair_identity(q) != pair_identity(a):
        raise ValueError('Document identities conflict (level, scheme, paper, family, attempt/collection, series, part)')
    if q.catalog_status != 'confirmed' or a.catalog_status != 'confirmed':
        raise ValueError('Confirm both document metadata records first')
    q_papers = {span['paper_id'] for span in q.paper_page_ranges} if q.paper_page_ranges else {q.paper_id}
    a_papers = {span['paper_id'] for span in a.paper_page_ranges} if a.paper_page_ranges else {a.paper_id}
    if None in q_papers or q_papers!=a_papers:
        raise ValueError('Combined document pairs require matching confirmed paper ranges')
    if not q.attempt_id and not q.collection_id:
        raise ValueError('Undated pairs require a collection identity')
    if q.doc_type_id not in {'mtp_question','model_question','exam','question_paper'} or a.doc_type_id not in {'mtp_answer','model_answer','suggested_answer'}:
        raise ValueError('Unsupported question/answer document roles')
    row = session.scalar(sa.select(DocumentPair).where(DocumentPair.question_document_id == question_id, DocumentPair.answer_document_id == answer_id))
    if row is None:
        row = DocumentPair(question_document_id=question_id, answer_document_id=answer_id)
        session.add(row)
    competing = session.scalar(sa.select(DocumentPair.id).where(DocumentPair.question_document_id == question_id, DocumentPair.answer_document_id != answer_id, DocumentPair.status == 'confirmed'))
    if competing:
        raise ValueError('A competing answer document is confirmed; resolve it before pairing')
    row.status, row.confirmed_by, row.confirmed_at = 'confirmed', actor_id, datetime.now(timezone.utc)
    row.evidence = {'identity': list(pair_identity(q)), 'administrator_note': evidence}
    session.flush()
    return row


def unit_snapshot(unit: ParsedUnit, answers: dict[str, PairedAnswer], paper_id: str, context_text: str = '') -> dict[str, Any]:
    value = asdict(unit)
    value.pop('line_blocks', None)
    value['question_text'] = unit.question_text
    value['text_origin'] = 'ocr' if any(block.origin=='ocr' for block in unit.line_blocks) else 'pdf'
    value['answer'] = asdict(answers[unit.label_path]) if unit.label_path in answers else None
    value['paper_id'] = paper_id
    value['context_text'] = context_text
    value['raw_content_digest'] = digest([(block.raw_text or block.text, block.page, block.bbox, block.origin) for block in unit.line_blocks])
    value['children'] = [unit_snapshot(child, answers, paper_id, '\n'.join(filter(None, [context_text, unit.question_text]))) for child in unit.children]
    value['content_digest'] = digest({k: value[k] for k in ('label_path','kind','question_text','context_text','raw_content_digest','page_start','page_end','block_start','block_end','marks','choice_role','or_group','mcq_options','mcq_correct_option','answer','children')})
    return value


def refresh_snapshot_digests(roots: list[dict], context: str = '') -> None:
    for node in roots:
        node['context_text'] = context
        refresh_snapshot_digests(node['children'], '\n'.join(filter(None, [context, node['question_text']])))
        node['content_digest'] = digest({k:node[k] for k in ('label_path','kind','question_text','context_text','raw_content_digest','page_start','page_end','block_start','block_end','marks','choice_role','or_group','mcq_options','mcq_correct_option','answer','children')})


def flatten_snapshots(roots: list[dict]) -> list[dict]:
    return [node for root in roots for node in [root, *flatten_snapshots(root['children'])]]


def assemble_questions(session: Session, doc: Document, roots: list[dict], revision_digest: str, expects_answers: bool) -> list[dict]:
    ancestor = doc
    seen = {doc.id}
    while ancestor.supersedes_document_id:
        previous = session.get(Document, ancestor.supersedes_document_id)
        if previous is None or previous.id in seen:
            break
        ancestor = previous
        seen.add(ancestor.id)
    source_ids = {doc.id, *[(node.get('answer') or {}).get('answer_doc_id') or doc.id for node in flatten_snapshots(roots)]}
    source_urls = dict(session.execute(sa.select(DiscoveredLink.document_id,DiscoveredLink.url).where(DiscoveredLink.document_id.in_(source_ids)).order_by(DiscoveredLink.id)).all())

    def span(node, answer=False):
        answer_data = node.get('answer') or {}
        answer_id = answer_data.get('answer_doc_id') or doc.id
        source_doc = session.get(Document, answer_id) if answer else doc
        return dict(document_sha256=source_doc.sha256,
            official_url=source_urls.get(source_doc.id),
            page_start=(answer_data.get('page_start') or node['page_start']) if answer else node['page_start'],
            page_end=(answer_data.get('page_end') or node['page_end']) if answer else node['page_end'],
            block_start=answer_data.get('block_start') if answer else node['block_start'],
            block_end=answer_data.get('block_end') if answer else node['block_end'])

    result = []
    for root in roots:
        question_id = digest({'source': ancestor.id, 'identity': list(pair_identity(doc)), 'paper': root['paper_id'], 'label': root['label_path']})
        flat = flatten_snapshots([root])
        ids = {n['label_path']: question_id if n is root else question_id + ':' + n['label_path'] for n in flat}
        def part(node, sequence):
            return dict(id=ids[node['label_path']], label=node['display_label'], label_path=node['label_path'], sequence=sequence,
                question_text=node['question_text'], marks=node['marks'], source_spans=[span(node)],
                parts=[part(c, i) for i, c in enumerate(node['children'])])
        def answer_part(node, sequence):
            children = [answer_part(child,i) for i,child in enumerate(node['children'])]
            children = [child for child in children if child is not None]
            answer_data = node.get('answer') or {}
            available = bool(answer_data.get('answer_text') or answer_data.get('mcq_correct_option'))
            if not available and not children:
                return None
            return dict(id=ids[node['label_path']] + ':answer', question_part_id=ids[node['label_path']],
                sequence=sequence, answer_text=answer_data.get('answer_text') or '',
                source_spans=[span(node, True)] if available else children[0]['source_spans'], parts=children)
        answer_root = answer_part(root,0)
        answers = [answer_root] if answer_root else []
        leaves = [n for n in flat if n['is_gradable']]
        available = [n for n in leaves if n.get('answer') and (n['answer']['answer_text'] or n['answer']['mcq_correct_option'])]
        ambiguous = any(n.get('answer') and n['answer'].get('status') == 'ambiguous' for n in flat)
        status = 'missing' if not answers else 'complete' if leaves and len(available) == len(leaves) else 'partial'
        root['stable_question_id'] = question_id
        for node in flat:
            node['stable_question_id'] = question_id
        result.append(ExtractedQuestion(question_id=question_id, content_revision=revision_digest,
            course_level=doc.course_level, scheme_id=doc.scheme_id or '', paper_id=root['paper_id'],
            source_family=family(doc.doc_type_id), source_attempt_id=doc.attempt_id, source_collection_id=doc.collection_id,
            display_label=root['display_label'], label_path=root['label_path'], common_stem=root['question_text'] if root['children'] else '',
            question_text='' if root['children'] else root['question_text'],
            parts=[part(c, i) for i,c in enumerate(root['children'])], answers=answers, answer_status=status,
            question_status='unknown' if leaves else 'partial', pairing_status='ambiguous' if ambiguous else ('not_expected' if not expects_answers else 'matched' if status == 'complete' else status),
            source_spans=[span(root)], source_document_ids=sorted({doc.id, *[(n.get('answer') or {}).get('answer_doc_id') or doc.id for n in flat]}),
            choices=[{'label':n['label_path'],'role':n['choice_role'],'or_group':n['or_group'],'marks':n['marks']} for n in flat],
            mcq=[{'part_id':ids[n['label_path']], 'options': n['mcq_options'], 'key':(n.get('answer') or {}).get('mcq_correct_option')} for n in flat if n['kind']=='mcq'],
            pairing_candidates=[{'part_id':ids[n['label_path']], 'label_path':n['label_path'],
                'status':n['answer']['status'], 'candidates':n['answer'].get('candidates',[])} for n in flat if n.get('answer')],
        ).model_dump(mode='json'))
    return result


def reconcile(session: Session, revision: ExtractionRevision) -> None:
    previous_source = revision.configuration.get('predecessor_document_id')
    source_ids = [revision.document_id, *([previous_source] if previous_source else [])]
    old = list(session.scalars(sa.select(Unit).where(Unit.document_id.in_(source_ids), Unit.current.is_(True)).order_by(Unit.id)))
    new = flatten_snapshots(revision.parsed_units)
    old_by_label = {u.label_path:u for u in old}
    # Exact ordered text partitions provide split/merge evidence, never review inheritance.
    # Restrict candidates to one paper and parent scope; repeated matches remain ambiguous.
    old_pending = [u for u in old if u.is_gradable and not any(
        n['label_path']==u.label_path and n['content_digest']==u.content_digest for n in new)]
    new_pending = [n for n in new if n['is_gradable'] and not (
        n['label_path'] in old_by_label and old_by_label[n['label_path']].content_digest==n['content_digest'])]
    def text_key(text):
        text = re.sub(r'^\s*\((?:[a-zA-Z]|i{1,3}|iv|v|vi{0,3}|ix|x)\)\s*','',text)
        return re.sub(r'\s+',' ',text).strip()
    def partitions(target, candidates):
        found = []
        for start in range(len(candidates)):
            combined = ''
            for end in range(start,len(candidates)):
                combined = ' '.join(filter(None,[combined,text_key(candidates[end][1])]))
                if len(combined)>len(target):
                    break
                if end>start and combined==target:
                    found.append([row[0] for row in candidates[start:end+1]])
        return found
    old_scopes = {}
    for unit in old_pending:
        parent = session.get(Unit,unit.parent_unit_id) if unit.parent_unit_id else None
        scope = (unit.extraction_data.get('paper_id'), parent.label_path if parent else None)
        old_scopes.setdefault(scope,[]).append((unit.id,unit.question_text))
    new_scopes = {}
    for node in new_pending:
        new_scopes.setdefault((node['paper_id'],node['parent_label_path']),[]).append((node['label_path'],node['question_text']))
    proposals = []
    for scope, candidates in old_scopes.items():
        for old_id, text in candidates:
            if text_key(text):
                proposals.extend(('split',[old_id],labels) for labels in partitions(text_key(text),new_scopes.get(scope,[])))
    for scope, candidates in new_scopes.items():
        for label,text in candidates:
            if text_key(text):
                proposals.extend(('merged',ids,[label]) for ids in partitions(text_key(text),old_scopes.get(scope,[])))
    structural = {}
    for relation,old_ids,labels in proposals:
        unique = all(sum(old_id in p[1] for p in proposals)==1 for old_id in old_ids) and all(
            sum(label in p[2] for p in proposals)==1 for label in labels)
        for label in labels:
            structural.setdefault(label,[]).append((relation if unique else 'ambiguous',old_ids,labels))
    used = set()
    published = set(session.scalars(sa.select(Appearance.source_unit_id).where(Appearance.source_unit_id.in_([u.id for u in old])))) if old else set()
    for node in new:
        if node['label_path'] in structural:
            for relation,old_ids,labels in structural[node['label_path']]:
                for old_id in old_ids:
                    used.add(old_id)
                    session.add(ReconciliationLink(revision_id=revision.id,old_unit_id=old_id,
                        new_label=node['label_path'],relation=relation,evidence={
                            'match':'exact_ordered_text_partition','old_unit_ids':old_ids,'new_labels':labels,
                            'full_digest':node['content_digest'],'requires_fresh_review':True,
                            'published_review_required':old_id in published}))
            continue
        previous = old_by_label.get(node['label_path'])
        relation = 'new'
        if previous:
            used.add(previous.id)
            relation = 'unchanged' if previous.content_digest == node['content_digest'] else 'changed'
        else:
            matches = [u for u in old if u.content_digest == node['content_digest']]
            if len(matches) > 1:
                relation = 'ambiguous'
        session.add(ReconciliationLink(revision_id=revision.id, old_unit_id=previous.id if previous else None,
            new_label=node['label_path'], relation=relation,
            evidence={'full_digest':node['content_digest'], 'published_review_required': previous is not None and previous.id in published and relation != 'unchanged'}))
    for previous in old:
        if previous.id not in used:
            session.add(ReconciliationLink(revision_id=revision.id, old_unit_id=previous.id, new_label=None,
                relation='missing', evidence={'published_review_required':previous.id in published}))


def promote_revision(session: Session, revision_id: int, expected_current_revision_id: int | None) -> dict:
    revision = session.get(ExtractionRevision, revision_id)
    if revision is None:
        raise ValueError('Revision not found')
    document_ids = {revision.document_id, *[pair['answer_document_id'] for pair in revision.configuration.get('pairing', [])]}
    if revision.configuration.get('predecessor_document_id'):
        document_ids.add(revision.configuration['predecessor_document_id'])
    for document_id in sorted(document_ids):
        session.execute(sa.text('SELECT pg_advisory_xact_lock(:document_id)'), {'document_id': document_id})
    doc = session.scalar(sa.select(Document).where(Document.id == revision.document_id).with_for_update().execution_options(populate_existing=True))
    if doc.catalog_status != 'confirmed':
        raise ValueError('Administrator must confirm document metadata before promotion')
    if revision.configuration.get('metadata_identity') != list(pair_identity(doc)) or revision.configuration.get('paper_ranges') != (doc.paper_page_ranges or [{'paper_id':doc.paper_id,'page_start':1,'page_end':doc.page_count}]):
        raise RevisionConflict('Document metadata changed after extraction; build a new candidate')
    for evidence in revision.configuration.get('pairing',[]):
        pair = session.scalar(sa.select(DocumentPair).where(DocumentPair.id==evidence['pair_id']).with_for_update().execution_options(populate_existing=True))
        answer_doc = session.scalar(sa.select(Document).where(Document.id==evidence['answer_document_id']).with_for_update().execution_options(populate_existing=True))
        if pair is None or answer_doc is None or pair.status!='confirmed' or pair.question_document_id!=doc.id or pair.answer_document_id!=answer_doc.id:
            raise RevisionConflict('Document pair changed after extraction; build a new candidate')
        answer_ranges = answer_doc.paper_page_ranges or [{'paper_id':answer_doc.paper_id,'page_start':1,'page_end':answer_doc.page_count}]
        if answer_doc.catalog_status!='confirmed' or answer_doc.superseded or pair_identity(answer_doc)!=pair_identity(doc) or answer_doc.sha256!=evidence['answer_sha256'] or answer_ranges!=evidence['answer_ranges']:
            raise RevisionConflict('Answer document metadata changed after extraction; build a new candidate')
    if doc.current_revision_id == revision_id:
        return dict(id=revision.id, document_id=doc.id, status='current', current_revision_id=revision.id,
                    units=session.scalar(sa.select(sa.func.count(Unit.id)).where(Unit.document_id==doc.id, Unit.current.is_(True))))
    if doc.current_revision_id != expected_current_revision_id or revision.base_revision_id != expected_current_revision_id:
        raise RevisionConflict('Stale candidate: current revision changed; extract against the current revision')
    if revision.status != 'candidate' or revision.quality.get('outcome') in {'failed','unsupported_profile','ocr_unavailable'}:
        raise ValueError('Only parsed candidate revisions can be promoted')
    previous = session.get(ExtractionRevision, doc.current_revision_id) if doc.current_revision_id else None
    if previous:
        previous.status = 'superseded'
        session.flush()
    current = list(session.scalars(sa.select(Unit).where(Unit.document_id==doc.id, Unit.current.is_(True))))
    source_previous = None
    if revision.configuration.get('predecessor_document_id'):
        source_previous = session.scalar(sa.select(Document).where(Document.id==revision.configuration['predecessor_document_id']).with_for_update().execution_options(populate_existing=True))
        if source_previous is None or source_previous.current_revision_id != revision.configuration.get('predecessor_revision_id'):
            raise RevisionConflict('Previous artifact revision changed; build a new candidate')
        current.extend(session.scalars(sa.select(Unit).where(Unit.document_id==source_previous.id,Unit.current.is_(True))))
    old_map = {u.label_path:u for u in current}
    session.execute(sa.update(Unit).where(Unit.document_id==doc.id, Unit.current.is_(True)).values(current=False))
    if source_previous:
        session.execute(sa.update(Unit).where(Unit.document_id==source_previous.id,Unit.current.is_(True)).values(current=False))
        source_previous.superseded = True
    db_units = {}
    snapshots = [] if revision.configuration.get('profile', {}).get('document_role') == 'answers' else flatten_snapshots(revision.parsed_units)
    for node in snapshots:
        old = old_map.get(node['label_path'])
        parent = db_units.get(node['parent_label_path'])
        # Reuse exact unchanged units only when ancestry is also unchanged.
        if old and old.document_id == doc.id and old.content_digest == node['content_digest'] and old.parent_unit_id == (parent.id if parent else None):
            unit = old
            unit.current = True
        else:
            unit = Unit(document_id=doc.id, extract_run_id=revision.run_id, revision_id=revision.id,
                parent_unit_id=parent.id if parent else None,
                label_path=node['label_path'], display_label=node['display_label'], kind=node['kind'],
                is_gradable=node['is_gradable'], marks=node['marks'], marks_source=node['marks_source'],
                choice_role=node['choice_role'], or_group=node['or_group'], page_start=node['page_start'],
                page_end=node['page_end'], block_start=node['block_start'], block_end=node['block_end'],
                question_text=node['question_text'], text_origin=node.get('text_origin','pdf'),
                fingerprint=hashlib.sha1((node['stable_question_id'] + ':' + node['label_path'] + ':' + node['content_digest']).encode()).hexdigest(),
                content_digest=node['content_digest'], stable_question_id=node['stable_question_id'],
                extraction_data={'mcq_options':node['mcq_options'], 'paper_id':node['paper_id']},
                parse_confidence=node['parse_confidence'], validation_flags=node['validation_flags'], current=True)
            session.add(unit)
            session.flush()
            answer = node.get('answer')
            if answer and (answer['answer_text'] or answer['mcq_correct_option']):
                session.add(UnitAnswer(unit_id=unit.id, answer_document_id=answer.get('answer_doc_id') or doc.id,
                    answer_text=answer['answer_text'], page_start=answer['page_start'], page_end=answer['page_end'],
                    mcq_correct_option=answer['mcq_correct_option'], pairing_method=answer['pairing_method']))
        db_units[node['label_path']] = unit
    revision.status, revision.promoted_at = 'current', datetime.now(timezone.utc)
    doc.current_revision_id, doc.extract_run_id = revision.id, revision.run_id
    doc.extract_status = revision.quality['outcome']
    session.flush()
    return dict(id=revision.id,document_id=doc.id,status='current',current_revision_id=revision.id,units=len(db_units))


def reviewed_quality(session: Session, revision: ExtractionRevision) -> dict:
    """Project actual revision-bound reviews without mutating machine evidence."""
    from caf_db.models.extraction import ExtractionReview
    quality = dict(revision.quality)
    doc = session.get(Document,revision.document_id)
    if revision.status!='failed':
        metadata_matches = revision.configuration.get('metadata_identity')==list(pair_identity(doc)) and revision.configuration.get('paper_ranges')==(doc.paper_page_ranges or [{'paper_id':doc.paper_id,'page_start':1,'page_end':doc.page_count}])
        quality['metadata']='passed' if doc.catalog_status=='confirmed' and metadata_matches else 'pending'
    for review in session.scalars(sa.select(ExtractionReview).where(ExtractionReview.revision_id==revision.id,
            ExtractionReview.content_digest==revision.content_digest).order_by(ExtractionReview.id)):
        quality[review.dimension] = review.status
    if revision.status!='failed' and (doc.catalog_status!='confirmed' or not metadata_matches):
        quality['metadata']='pending'
    for evidence in revision.configuration.get('pairing',[]):
        pair=session.get(DocumentPair,evidence['pair_id'])
        answer=session.get(Document,evidence['answer_document_id'])
        if pair is None or answer is None or pair.status!='confirmed' or answer.catalog_status!='confirmed' or answer.superseded or pair_identity(answer)!=pair_identity(doc) or answer.sha256!=evidence['answer_sha256'] or evidence.get('answer_ranges')!=(answer.paper_page_ranges or [{'paper_id':answer.paper_id,'page_start':1,'page_end':answer.page_count}]):
            quality['pairing']='concern'
    return quality


def extraction_ready(session: Session, revision: ExtractionRevision) -> bool:
    quality = reviewed_quality(session,revision)
    dimensions = ('metadata','questions','answers','pairing','ordering','marks_choices','readability','human_review')
    return all(quality.get(key) in {'passed','not_applicable'} for key in dimensions)


def complete_answer_text(question: dict) -> str:
    def texts(parts):
        return [text for part in parts for text in [part['answer_text'], *texts(part['parts'])] if text]
    return '\n'.join([*texts(question['answers']), *[
        f"MCQ key ({mcq['part_id']}): {mcq['key']}" for mcq in question['mcq'] if mcq['key']]])
