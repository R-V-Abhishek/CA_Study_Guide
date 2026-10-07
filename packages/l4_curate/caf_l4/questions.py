"""Publish complete source-bound student snapshots without exposing staging tables."""
import copy
import hashlib
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from caf_db.models.classification import QuestionPublication
from caf_db.models.extraction import DocumentPair, ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.questions import CorpusGeneration, PublishedQuestion, PublishedSource, QuestionOccurrence
from caf_db.models.ref import DocType
from caf_l0.hierarchy import ancestors, version_nodes
from caf_l2.revisions import flatten_snapshots, reviewed_quality


def marks_projection(root: dict, question_id: str, mappings: list[dict]) -> dict:
    """Attribute disjoint leaves only; uncertainty never becomes extra marks."""
    nodes = flatten_snapshots([root])
    by_id = {question_id if node is root else question_id + ':' + node['label_path']: node for node in nodes}
    allocations, issues = [], []
    for mapping in mappings:
        node = by_id[mapping['part_id']]
        descendants = flatten_snapshots(node['children'])
        if any(child['is_gradable'] for child in descendants):
            issues.append('overlapping_gradable_parent:' + mapping['part_id'])
            continue
        marks = node['marks']
        label_ids = [mapping['primary_node_id'], *mapping['secondary_node_ids']] if mapping['outcome'] == 'matched' and not mapping['excluded'] else []
        total = 1 + .5 * max(0, len(label_ids) - 1)
        ambiguous = node['choice_role'] == 'unknown' or marks is None
        if marks is None:
            issues.append('unknown_marks:' + mapping['part_id'])
        if node['choice_role'] == 'unknown':
            issues.append('unknown_choice:' + mapping['part_id'])
        allocations.append(dict(part_id=mapping['part_id'], marks=marks,
            allocation_status='ambiguous' if ambiguous else 'reviewed', choice_group=node['or_group'],
            node_shares=[dict(node_id=node_id, share=(1 if index == 0 else .5) / total,
                attributed_marks=None if ambiguous else marks * (1 if index == 0 else .5) / total)
                for index,node_id in enumerate(label_ids)]))
    # A known parent's total bounds its descendants; inconsistent totals are
    # retained visibly but cannot produce an inflated score.
    for parent in nodes:
        if parent['marks'] is None or not parent['children']:
            continue
        labels={child['label_path'] for child in flatten_snapshots(parent['children'])}
        children=[a for a in allocations if by_id[a['part_id']]['label_path'] in labels]
        if children and all(a['marks'] is not None for a in children) and sum(a['marks'] for a in children)>parent['marks']:
            issues.append('parent_child_marks_conflict:' + parent['label_path'])
            for child in children:
                child['allocation_status']='ambiguous'
                for share in child['node_shares']:
                    share['attributed_marks']=None
    # OR alternatives are offered evidence, not additive selectable marks.
    groups: dict[str,list[dict]] = {}
    for allocation in allocations:
        if allocation['choice_group']:
            groups.setdefault(allocation['choice_group'], []).append(allocation)
    for group, options in groups.items():
        issues.append('or_group_allocation_unresolved:' + group)
        for option in options:
            option['allocation_status'] = 'ambiguous'
            for share in option['node_shares']:
                share['attributed_marks'] = None
    offered = sum(a['marks'] for a in allocations) if allocations and all(a['marks'] is not None for a in allocations) else None
    selectable = offered if not groups and all(a['allocation_status'] == 'reviewed' for a in allocations) else None
    return dict(whole_question_marks=root['marks'], offered_marks=offered, selectable_marks=selectable,
        allocations=allocations, issues=issues)


def _source(session, document_id):
    doc = session.get(Document, document_id)
    source = session.scalar(select(PublishedSource).where(PublishedSource.sha256 == doc.sha256))
    if source is None:
        source = PublishedSource(document_id=doc.id, sha256=doc.sha256, title=doc.title,
            doc_type_id=doc.doc_type_id, attempt_id=doc.attempt_id, page_count=doc.page_count,
            approved_blob_path=doc.blob_path, official_url=doc.metadata_evidence.get('official_url'))
        session.add(source)
        session.flush()
    return source


def _occurrence(session, document, content):
    pairs = list(session.scalars(select(DocumentPair).where(DocumentPair.status == 'confirmed',
        ((DocumentPair.question_document_id == document.id) | (DocumentPair.answer_document_id == document.id)))))
    compatible = []
    for pair in pairs:
        paper = session.get(Document, pair.question_document_id)
        answer = session.get(Document, pair.answer_document_id)
        if paper.paper_id == answer.paper_id == content['paper_id'] and paper.attempt_id == answer.attempt_id and paper.series == answer.series:
            compatible.append(pair)
    canonical_id = compatible[0].question_document_id if len(compatible) == 1 else document.id
    # Explicit reviewed pairing and the parsed question label are required to
    # share identity. Reuse in a separate collection retains another identity.
    identity = [canonical_id, content['paper_id'], document.attempt_id, document.series, content['label_path']]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    row = session.scalar(select(QuestionOccurrence).where(QuestionOccurrence.identity_key == key))
    if row is None:
        kind = session.get(DocType, document.doc_type_id) if document.doc_type_id else None
        row = QuestionOccurrence(identity_key=key, question_id=content['question_id'], paper_id=content['paper_id'],
            attempt_id=document.attempt_id, source_family=content['source_family'],
            signal_class=kind.signal_class if kind else 'practice', series=document.series,
            identity_status='ambiguous' if len(pairs) != len(compatible) or len(compatible)>1 or (document.doc_type_id in {'suggested_answer','mtp_answer','model_answer'} and not compatible) else 'confirmed',
            pairing_evidence={'pair_ids':[pair.id for pair in compatible], 'canonical_document_id':canonical_id,
                'question_label':content['label_path'], 'source_document_ids':content['source_document_ids']})
        session.add(row)
        session.flush()
    return row


def project_question(session: Session, suggestion, revision, publication: QuestionPublication) -> PublishedQuestion:
    """Called inside the classification transaction after all publication gates."""
    extraction = session.get(ExtractionRevision, revision.extraction_revision_id)
    document = session.get(Document, suggestion.document_id)
    content = copy.deepcopy(revision.context)
    content.pop('classification_part_ids', None)
    root = next(node for node in extraction.parsed_units if node['stable_question_id'] == revision.question_id)
    occurrence = _occurrence(session, document, content)
    nodes = {node.id:node for node in version_nodes(session, revision.taxonomy_version_id)}
    covered = []
    ids = {node_id for mapping in revision.mappings if mapping['outcome'] == 'matched' and not mapping['excluded']
        for node_id in [mapping['primary_node_id'], *mapping['secondary_node_ids']]}
    for node_id in sorted(ids):
        node = nodes[node_id]
        covered.append(dict(node_id=node_id, name=node.name,
            path=[dict(id=ancestor.id,name=ancestor.name,level=ancestor.level) for ancestor in ancestors(node_id,nodes)]))
    source_map = {document_id:_source(session, document_id) for document_id in content['source_document_ids']}
    assets=[]
    for index, asset in enumerate(content.get('assets', [])):
        source=source_map.get(asset['document_id'])
        if source:
            assets.append({**asset, 'id':f'{revision.id}:{index}', 'source_id':source.id})
    state=session.scalar(select(CorpusGeneration).where(CorpusGeneration.id == 1).with_for_update())
    if state is None:
        state=CorpusGeneration(id=1,generation=0);session.add(state);session.flush()
    state.generation += 1
    search_text=' '.join([content['display_label'],content['common_stem'],content['question_text'],
        *[part['question_text'] for part in flatten_content_parts(content['parts'])],
        *[' '.join(node['name'] for node in topic['path']) for topic in covered],
        *[' '.join(filter(None,[source.title,source.doc_type_id,source.attempt_id])) for source in source_map.values()],
        document.series or '', document.collection_id or '',
        content['source_family'],content['paper_id'],content.get('source_attempt_id') or ''])
    row=PublishedQuestion(id=revision.id,question_id=revision.question_id,extraction_revision_id=extraction.id,
        taxonomy_version_id=revision.taxonomy_version_id,occurrence_id=occurrence.id,publication_generation=state.generation,
        content=content,mappings=revision.mappings,covered_subtopics=covered,marks=marks_projection(root,revision.question_id,revision.mappings),
        quality=reviewed_quality(session,extraction),source_ids=[source.id for source in source_map.values()],assets=assets,search_text=search_text)
    session.add(row);session.flush()
    publication.current_snapshot_id=row.id
    publication.current_revision_id=revision.id
    return row


def flatten_content_parts(parts):
    return [node for part in parts for node in [part,*flatten_content_parts(part['parts'])]]


def backfill_publications(session: Session) -> dict:
    """Materialize existing reviewed pointers; never creates review or approval."""
    from caf_db.models.classification import ClassificationRevision, SuggestionRevision
    from caf_db.models.core import Appearance
    publications=list(session.scalars(select(QuestionPublication).where(
        QuestionPublication.current_revision_id.is_not(None),QuestionPublication.current_snapshot_id.is_(None)).with_for_update()))
    created,skipped=0,[]
    for publication in publications:
        revision=session.get(ClassificationRevision,publication.current_revision_id)
        suggestion=session.get(SuggestionRevision,revision.suggestion_revision_id)
        if revision.blind or suggestion.experimental:
            skipped.append(publication.question_id)
            continue
        snapshot=session.get(PublishedQuestion,revision.id)
        if snapshot is None:
            snapshot=project_question(session,suggestion,revision,publication)
        else:
            publication.current_snapshot_id=snapshot.id
        # Bind only matching unit revision fingerprints, never similar text.
        from caf_db.models.ingest import Unit
        units=list(session.scalars(select(Unit).where(Unit.revision_id==revision.extraction_revision_id,
            Unit.stable_question_id==revision.question_id)))
        for unit in units:
            appearance=session.scalar(select(Appearance).where(Appearance.unit_fingerprint==unit.fingerprint,
                Appearance.status=='published'))
            if appearance:
                appearance.question_id=revision.question_id
                appearance.part_id=revision.question_id if unit.parent_unit_id is None else revision.question_id+':'+unit.label_path
                appearance.occurrence_id=snapshot.occurrence_id
        created+=1
    session.flush()
    return {'created':created,'skipped_experimental_or_blind':skipped}
