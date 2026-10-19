"""Audited adoption of a frozen corpus, separate from student verification.

Preparation and activation are separate caller-owned transactions. No model calls,
extraction promotions, review approvals or personal-progress migrations occur here.
"""
from datetime import datetime, timezone
import copy
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.app import Settings
from caf_db.models.classification import (BaselineAdoption, CandidateCatalog,
    ClassificationRevision, QuestionPublication, SuggestionRevision)
from caf_db.models.core import ChangeLog
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.intel import AttemptTaxonomyBinding
from caf_db.models.ops import Run
from caf_db.models.ref import Attempt, Node, TaxonomyVersion
from caf_db.models.taxonomy import (DescriptorRevision, NodeSourceSpan, TaxonomyMember,
    TaxonomyRelease, TextbookArtifact)
from caf_l2.revisions import digest


def _lock(session):
    session.execute(sa.text('SELECT pg_advisory_xact_lock(731306)'))


def _pin_locks(session, row, version):
    for document_id in sorted(int(key) for key in row.pins['sources']):
        session.execute(sa.text('SELECT pg_advisory_xact_lock(:key)'),{'key':document_id})
    session.execute(sa.select(Document.id).where(Document.id.in_(
        [int(key) for key in row.pins['sources']])).with_for_update()).all()
    session.execute(sa.select(ExtractionRevision.id).where(ExtractionRevision.id.in_(
        [int(key) for key in row.pins['extractions']])).with_for_update()).all()
    session.execute(sa.select(NodeSourceSpan.id).where(NodeSourceSpan.taxonomy_version_id==version)
        .with_for_update()).all()


def _admin(session, actor_id):
    from caf_l4.revisions import _actor
    _actor(session, actor_id, administrator=True)


def source_pin(document: Document) -> dict:
    fields = ('sha256', 'paper_id', 'paper_page_ranges', 'catalog_status', 'course_level',
              'scheme_id', 'provenance_status', 'current_revision_id', 'superseded',
              'attempt_id', 'doc_type_id', 'series', 'collection_id', 'blob_path', 'page_count')
    return {field: document.__dict__[field] for field in fields}


def extraction_pin(revision: ExtractionRevision) -> str:
    return digest(dict(content_digest=revision.content_digest, status=revision.status,
        questions=revision.questions, parsed_units=revision.parsed_units, quality=revision.quality,
        configuration=revision.configuration))


def taxonomy_pin(session: Session, version: int) -> str:
    """Include mutable evidence content, not merely caller-supplied hash columns."""
    values = {}
    for model, fields, order in (
        (TaxonomyMember, ('node_id','parent_id','paper_id','level','name','seq','heading_origin'), ('node_id',)),
        (DescriptorRevision, ('node_id','revision','content_hash','content'), ('node_id','revision')),
        (TextbookArtifact, ('id','sha256','edition','availability','metadata_json'), ('id',)),
        (NodeSourceSpan, ('node_id','artifact_id','pdf_page_start','pdf_page_end','review_status'), ('node_id','artifact_id','pdf_page_start','id')),
    ):
        columns = [model.__table__.c[field] for field in fields]
        rows = session.execute(sa.select(*columns).where(model.taxonomy_version_id == version)
            .order_by(*[model.__table__.c[field] for field in order]))
        values[model.__tablename__] = [list(row) for row in rows]
    # The serving hierarchy reads Node as well as release membership.
    values['nodes'] = [list(row) for row in session.execute(sa.select(Node.id, Node.paper_id,
        Node.parent_id, Node.level, Node.name, Node.seq, Node.status).join(TaxonomyMember,
        TaxonomyMember.node_id == Node.id).where(TaxonomyMember.taxonomy_version_id == version).order_by(Node.id))]
    return digest(values)


def _taxonomy(session, frozen):
    manifest_hash = frozen['manifest_hash']
    version = TaxonomyVersion(yaml_hash=manifest_hash, notes=f"Adopted corpus {frozen['release_id']}")
    session.add(version)
    session.flush()
    manifest = copy.deepcopy(frozen['manifest'])
    manifest.update(version_id=frozen['release_id'], target_attempt=frozen['target_attempt'],
        adoption_scope='study_and_review', applicability='Source evidence retained; adoption is not applicability approval')
    release = TaxonomyRelease(version_id=frozen['release_id'], taxonomy_version_id=version.id,
        target_attempt=frozen['target_attempt'], manifest_hash=manifest_hash, manifest=manifest, status='draft')
    session.add(release)
    existing = {n.id:n for n in session.scalars(sa.select(Node))}
    old_artifacts = {a.id:a for a in session.scalars(sa.select(TextbookArtifact))}
    candidates = {c['node_id']:c for catalog in frozen['catalogs'].values() for c in catalog}
    members, references = {}, {}
    for candidate in candidates.values():
        for index, node in enumerate(candidate['path']):
            leaf = node['id'] == candidate['node_id']
            parent = candidate['path'][index-1]['id'] if index else None
            old = existing.get(node['id'])
            fields = dict(paper_id=node['paper_id'], parent_id=parent,
                level='subtopic' if leaf else node['level'], name=node['name'],
                seq=old.seq if old else members[node['id']]['seq'] if node['id'] in members else len(members)+1)
            if old and (old.paper_id, old.parent_id, old.level, old.name) != (
                    fields['paper_id'], parent, fields['level'], fields['name']):
                raise ValueError('Incompatible existing node identity: ' + node['id'])
            if node['id'] in members and members[node['id']] != fields:
                raise ValueError('Inconsistent catalog hierarchy: ' + node['id'])
            members[node['id']] = fields
            references.setdefault(node['id'], {})
            for ref in candidate['textbook_references']:
                references[node['id']][(ref['artifact_id'],ref['pdf_page_start'],ref['pdf_page_end'])] = ref
    # Insert parents before children to satisfy the immutable global hierarchy FK.
    pending = dict(members)
    while pending:
        ready = [key for key, fields in pending.items() if fields['parent_id'] not in pending]
        if not ready:
            raise ValueError('Catalog hierarchy contains a cycle')
        for key in ready:
            fields = pending.pop(key)
            if key not in existing:
                session.add(Node(id=key, **fields, status='active', created_in=version.id, updated_in=version.id))
        session.flush()
    for key, fields in members.items():
        candidate = candidates.get(key, {})
        session.add(TaxonomyMember(taxonomy_version_id=version.id, node_id=key, **fields,
            heading_origin=candidate.get('heading_origin', 'official')))
    artifacts = {}
    for refs in references.values():
        for ref in refs.values():
            artifacts[ref['artifact_id']] = ref
    for key, ref in artifacts.items():
        old = old_artifacts.get(key)
        metadata = copy.deepcopy(old.metadata_json if old else ref)
        if not old:
            metadata.update(id=key, fallback=True, target_applicability='unresolved',
                source_context='Index heading evidence; target applicability requires review')
        session.add(TextbookArtifact(taxonomy_version_id=version.id, id=key,
            paper_id=old.paper_id if old else next(c['paper_id'] for c in candidates.values()
                if any(r['artifact_id']==key for r in c['textbook_references'])),
            course_level=old.course_level if old else 'Final', edition=ref['edition'],
            availability=ref['availability'], sha256=ref.get('sha256'),
            page_count=old.page_count if old else None, metadata_json=metadata))
    session.flush()
    for key, refs in references.items():
        for ref in refs.values():
            session.add(NodeSourceSpan(taxonomy_version_id=version.id, node_id=key,
                artifact_id=ref['artifact_id'], pdf_page_start=ref['pdf_page_start'],
                pdf_page_end=ref['pdf_page_end'], review_status=ref.get('review_status','pending')))
    for key, candidate in candidates.items():
        # Store index descriptors verbatim, without coercing them into textbook prose.
        session.add(DescriptorRevision(taxonomy_version_id=version.id, node_id=key, revision=1,
            content=candidate['descriptor'], content_hash=candidate['descriptor_hash']))
    session.flush()
    return release


def prepare_baseline(session: Session, frozen: dict, actor_id: int) -> BaselineAdoption:
    _admin(session, actor_id)
    _lock(session)
    if digest(frozen['manifest']) != frozen['manifest_hash']:
        raise ValueError('Frozen manifest hash does not match its content')
    for key,catalog in frozen['catalogs'].items():
        if digest(catalog) != key:
            raise ValueError('Frozen candidate catalog hash mismatch')
    previous = session.get(BaselineAdoption, frozen['release_id'])
    if previous:
        if previous.manifest_hash != frozen['manifest_hash'] or previous.manifest != frozen['manifest']:
            raise ValueError('Baseline identity already pins different inputs')
        suggestions = list(session.scalars(sa.select(SuggestionRevision).where(
            SuggestionRevision.batch_key == frozen['manifest_hash'])))
        records = {r['question_id']:r for r in frozen['records']}
        if len(suggestions) != len(records) or any(s.question_id not in records or
                s.mappings != records[s.question_id]['mappings'] or
                s.context != records[s.question_id]['context'] or
                s.candidate_catalog_hash != records[s.question_id]['catalog_hash'] for s in suggestions):
            raise ValueError('Prepared baseline differs from frozen records')
        for key, catalog in frozen['catalogs'].items():
            if session.get(CandidateCatalog,key).candidates != catalog:
                raise ValueError('Prepared catalog changed')
        return previous
    release = _taxonomy(session, frozen)
    for key, candidates in frozen['catalogs'].items():
        old = session.get(CandidateCatalog, key)
        if old is not None and old.candidates != candidates:
            raise ValueError('Candidate catalog hash collision')
        if old is None:
            session.add(CandidateCatalog(content_hash=key, candidates=candidates))
    session.flush()
    run = Run(stage='baseline-import', status='ok', taxonomy_version_id=release.taxonomy_version_id,
        config_hash=frozen['manifest_hash'], args={'release_id':release.version_id}, stats={'roots':len(frozen['records'])})
    session.add(run)
    session.flush()
    documents = {d.id:d for d in session.scalars(sa.select(Document).where(Document.id.in_(
        {i for r in frozen['records'] for i in r['context']['source_document_ids']})))}
    extractions = {e.id:e for e in session.scalars(sa.select(ExtractionRevision).where(
        ExtractionRevision.id.in_({r['extraction_revision_id'] for r in frozen['records']})))}
    pins = {'sources':{str(key):source_pin(doc) for key,doc in documents.items()},
        'extractions':{str(key):extraction_pin(e) for key,e in extractions.items()}, 'records':{}}
    for record in frozen['records']:
        extraction = extractions[record['extraction_revision_id']]
        doc = documents[record['document_id']]
        if extraction.document_id != doc.id or extraction.content_digest != record['extraction_digest'] or doc.sha256 != record['document_sha256']:
            raise ValueError('Pinned extraction or question source changed')
        original = next(q for q in extraction.questions if q['question_id']==record['question_id'])
        context = {k:v for k,v in record['context'].items() if k!='classification_part_ids'}
        if {k:v for k,v in context.items() if k!='paper_id'} != {k:v for k,v in original.items() if k!='paper_id'}:
            raise ValueError('Frozen context differs from saved extraction beyond corrected paper routing')
        content = dict(question_id=record['question_id'], document_id=doc.id, document_sha256=doc.sha256,
            extraction_revision_id=extraction.id, extraction_digest=extraction.content_digest,
            context=record['context'], candidate_catalog_hash=record['catalog_hash'])
        input_hash = digest(content)
        pins['records'][record['question_id']] = dict(input_hash=input_hash,
            mappings_hash=digest(record['mappings']), catalog_hash=record['catalog_hash'])
        session.add(SuggestionRevision(batch_key=frozen['manifest_hash'], input_hash=input_hash,
            document_id=doc.id, extraction_revision_id=extraction.id, question_id=record['question_id'],
            taxonomy_version_id=release.taxonomy_version_id, run_id=run.id,
            experimental=False, context=record['context'], candidates=[], candidate_catalog_hash=record['catalog_hash'],
            mappings=record['mappings'], provenance=dict(baseline_release_id=release.version_id,
                baseline_manifest_hash=frozen['manifest_hash'], taxonomy_manifest_hash=release.manifest_hash,
                extraction_digest=extraction.content_digest, original_input_hash=record.get('original_input_hash'),
                result_hash=record.get('result_hash'), pack=record.get('pack'), execution=record.get('execution',{}),
                uncalibrated=True, applicability_status='source_evidence_only_target_review_required')))
    session.flush()
    from caf_l4.revisions import validate_mappings
    members = {m.node_id:m for m in session.scalars(sa.select(TaxonomyMember).where(
        TaxonomyMember.taxonomy_version_id==release.taxonomy_version_id))}
    candidate_ids = {key:{c['node_id'] for c in catalog} for key,catalog in frozen['catalogs'].items()}
    for suggestion in session.scalars(sa.select(SuggestionRevision).where(SuggestionRevision.batch_key==frozen['manifest_hash'])):
        validate_mappings(session,suggestion,suggestion.mappings,members=members,
            candidate_ids=candidate_ids[suggestion.candidate_catalog_hash])
        pins['records'][suggestion.question_id]['suggestion_id']=suggestion.id
    pins['taxonomy_hash'] = taxonomy_pin(session, release.taxonomy_version_id)
    row = BaselineAdoption(release_id=release.version_id, manifest_hash=frozen['manifest_hash'],
        manifest=frozen['manifest'], pins=pins, status='prepared', actor_id=actor_id, previous_state={})
    session.add(row)
    session.add(ChangeLog(entity='baseline', entity_id=release.version_id, change='prepare',
        after={'manifest_hash':frozen['manifest_hash'],'roots':len(frozen['records']),'actor_id':actor_id}))
    session.flush()
    return row


def baseline_evidence(session, row, version):
    documents = list(session.scalars(sa.select(Document).where(Document.id.in_([int(k) for k in row.pins['sources']]))))
    extractions = list(session.scalars(sa.select(ExtractionRevision).where(ExtractionRevision.id.in_([int(k) for k in row.pins['extractions']]))))
    catalog_hashes = {pin['catalog_hash'] for pin in row.pins['records'].values()}
    catalogs = list(session.scalars(sa.select(CandidateCatalog).where(CandidateCatalog.content_hash.in_(catalog_hashes))))
    return dict(taxonomy_hash=taxonomy_pin(session,version),
        adoption=row,
        sources={str(d.id):source_pin(d) for d in documents},
        extractions={str(e.id):extraction_pin(e) for e in extractions},
        catalogs={c.content_hash:digest(c.candidates) for c in catalogs},
        resident=(documents,extractions,catalogs))


def baseline_readiness(session, suggestion, evidence=None, *, allow_prepared=False):
    row = evidence['adoption'] if evidence else session.get(BaselineAdoption, suggestion.provenance['baseline_release_id'])
    release = session.get(TaxonomyRelease, row.release_id) if row else None
    blockers = []
    if row is None or row.status not in ({'active','prepared'} if allow_prepared else {'active'}) or release is None:
        return dict(eligible=False, stale=True, experimental=False, blockers=['baseline_not_authorized'])
    evidence = evidence or baseline_evidence(session,row,release.taxonomy_version_id)
    pin = row.pins['records'].get(suggestion.question_id)
    content = dict(question_id=suggestion.question_id, document_id=suggestion.document_id,
        document_sha256=evidence['sources'].get(str(suggestion.document_id),{}).get('sha256'),
        extraction_revision_id=suggestion.extraction_revision_id,
        extraction_digest=suggestion.provenance.get('extraction_digest'),
        context=suggestion.context, candidate_catalog_hash=suggestion.candidate_catalog_hash)
    if (not pin or pin['input_hash'] != suggestion.input_hash or digest(content)!=suggestion.input_hash
            or pin['suggestion_id'] != suggestion.id or suggestion.taxonomy_version_id!=release.taxonomy_version_id
            or suggestion.batch_key!=row.manifest_hash or suggestion.experimental
            or pin['mappings_hash'] != digest(suggestion.mappings)
            or pin['catalog_hash'] != suggestion.candidate_catalog_hash):
        blockers.append('stale_baseline_inputs')
    if release.manifest_hash != row.manifest_hash or suggestion.provenance.get('baseline_manifest_hash') != row.manifest_hash:
        blockers.append('stale_baseline_manifest')
    if evidence['taxonomy_hash'] != row.pins['taxonomy_hash']:
        blockers.append('stale_baseline_taxonomy')
    if evidence['catalogs'].get(suggestion.candidate_catalog_hash) != suggestion.candidate_catalog_hash:
        blockers.append('stale_baseline_catalog')
    for key in set(suggestion.context['source_document_ids']) | {suggestion.document_id}:
        if evidence['sources'].get(str(key)) != row.pins['sources'].get(str(key)):
            blockers.append('stale_baseline_source')
    if evidence['extractions'].get(str(suggestion.extraction_revision_id)) != row.pins['extractions'].get(str(suggestion.extraction_revision_id)):
        blockers.append('stale_baseline_extraction')
    return dict(eligible=not blockers, stale=bool(blockers), experimental=False, blockers=sorted(set(blockers)))


def activate_baseline(session: Session, release_id: str, manifest_hash: str, actor_id: int) -> dict:
    _admin(session, actor_id)
    _lock(session)
    row = session.get(BaselineAdoption, release_id)
    if row is None or row.manifest_hash != manifest_hash:
        raise ValueError('Unknown baseline or conflicting manifest hash')
    release = session.get(TaxonomyRelease,release_id)
    _pin_locks(session,row,release.taxonomy_version_id)
    suggestions = list(session.scalars(sa.select(SuggestionRevision).where(
        SuggestionRevision.batch_key == manifest_hash).order_by(SuggestionRevision.question_id)))
    if len(suggestions) != len(row.pins['records']):
        raise ValueError('Prepared baseline is incomplete')
    evidence = baseline_evidence(session,row,release.taxonomy_version_id)
    for suggestion in suggestions:
        gate = baseline_readiness(session,suggestion,evidence,allow_prepared=True)
        if not gate['eligible']:
            raise ValueError('Changed baseline inputs: '+', '.join(gate['blockers']))
    if row.status == 'active':
        return dict(release_id=release_id,status='active',roots=len(suggestions),idempotent=True)
    if row.status != 'prepared':
        raise ValueError('Rolled-back baseline requires an explicit new adoption')
    old_release = session.scalar(sa.select(TaxonomyRelease).where(TaxonomyRelease.status=='active'))
    publications = {p.question_id:p for p in session.scalars(sa.select(QuestionPublication).where(
        QuestionPublication.question_id.in_([s.question_id for s in suggestions])).with_for_update())}
    old_target = session.scalar(sa.select(Settings.target_attempt_id).where(Settings.user_id==1))
    row.previous_state = dict(release_id=old_release.version_id if old_release else None,
        target_attempt_id=old_target,
        publications={q:dict(revision_id=p.current_revision_id,snapshot_id=p.current_snapshot_id)
            for q,p in publications.items()}, activated_revisions={},
        bindings=[dict(target=b.target_attempt_id,version=b.taxonomy_version_id,status=b.status)
            for b in session.scalars(sa.select(AttemptTaxonomyBinding).where(
                AttemptTaxonomyBinding.target_attempt_id==release.target_attempt))])
    if old_release:
        old_release.status='archived'
        session.flush()
    release.status='active'
    release.approved_by=actor_id
    release.approved_at=release.activated_at=datetime.now(timezone.utc)
    release.approved_review_hash=manifest_hash
    if session.get(Attempt,release.target_attempt) is None:
        year,month=map(int,release.target_attempt.split('-'))
        session.add(Attempt(id=release.target_attempt,exam_year=year,exam_month=month,label='May 2027',verified=False))
        session.flush()
    session.execute(sa.update(AttemptTaxonomyBinding).where(
        AttemptTaxonomyBinding.target_attempt_id==release.target_attempt).values(status='superseded'))
    session.add(AttemptTaxonomyBinding(target_attempt_id=release.target_attempt,
        taxonomy_version_id=release.taxonomy_version_id,status='reviewed',reviewed_by=actor_id,scoring_config={}))
    session.execute(sa.update(Settings).where(Settings.user_id==1).values(target_attempt_id=release.target_attempt))
    revisions=[]
    for suggestion in suggestions:
        publication=publications.get(suggestion.question_id)
        if publication is None:
            publication=QuestionPublication(question_id=suggestion.question_id,document_id=suggestion.document_id)
            session.add(publication)
            publications[suggestion.question_id]=publication
        revision=ClassificationRevision(question_id=suggestion.question_id,suggestion_revision_id=suggestion.id,
            extraction_revision_id=suggestion.extraction_revision_id,taxonomy_version_id=suggestion.taxonomy_version_id,
            previous_revision_id=publication.current_revision_id,mappings=suggestion.mappings,
            context=suggestion.context,input_hash=suggestion.input_hash,actor_id=actor_id,blind=False)
        revisions.append(revision)
    session.add_all(revisions)
    session.flush()
    from caf_l4.questions import project_question
    from caf_l0.hierarchy import version_nodes
    projection = {'nodes':{n.id:n for n in version_nodes(session,release.taxonomy_version_id)},'sources':{}}
    for suggestion, revision in zip(suggestions,revisions,strict=True):
        project_question(session,suggestion,revision,publications[suggestion.question_id],projection)
    state=copy.deepcopy(row.previous_state)
    state['activated_revisions']={r.question_id:r.id for r in revisions}
    row.previous_state=state
    row.status='active'
    row.activated_at=datetime.now(timezone.utc)
    session.add(ChangeLog(entity='baseline',entity_id=release_id,change='activate',
        after={'actor_id':actor_id,'manifest_hash':manifest_hash,'roots':len(revisions),'student_verifications_added':0}))
    session.flush()
    from caf_l5.jobs import enqueue_recompute
    job=enqueue_recompute(session,release.target_attempt,release.taxonomy_version_id,commit=False)
    return dict(release_id=release_id,status='active',roots=len(suggestions),job_id=job.id,idempotent=False)


def rollback_baseline(session: Session, release_id: str, manifest_hash: str, actor_id: int) -> dict:
    _admin(session,actor_id)
    _lock(session)
    row=session.get(BaselineAdoption,release_id)
    if row is None or row.manifest_hash!=manifest_hash or row.status!='active':
        raise ValueError('An active baseline with its exact manifest hash is required')
    release=session.get(TaxonomyRelease,release_id)
    if release.status!='active':
        raise ValueError('Another release is active; resolve its activation before rollback')
    restored=0
    for question_id, activated_id in row.previous_state['activated_revisions'].items():
        publication=session.get(QuestionPublication,question_id)
        # Later corrections stay published and all historical rows remain intact.
        if publication.current_revision_id!=activated_id:
            continue
        previous=row.previous_state['publications'].get(question_id,{})
        publication.current_revision_id=previous.get('revision_id')
        publication.current_snapshot_id=previous.get('snapshot_id')
        restored+=1
    release.status='archived'
    session.flush()
    if row.previous_state['release_id']:
        session.get(TaxonomyRelease,row.previous_state['release_id']).status='active'
    binding=session.get(AttemptTaxonomyBinding,(release.target_attempt,release.taxonomy_version_id))
    binding.status='superseded'
    for prior in row.previous_state['bindings']:
        session.get(AttemptTaxonomyBinding,(prior['target'],prior['version'])).status=prior['status']
    session.execute(sa.update(Settings).where(Settings.user_id==1,
        Settings.target_attempt_id==release.target_attempt).values(target_attempt_id=row.previous_state['target_attempt_id']))
    row.status='inactive'
    from caf_db.models.questions import CorpusGeneration
    generation=session.get(CorpusGeneration,1)
    if generation:
        generation.generation+=1
    session.add(ChangeLog(entity='baseline',entity_id=release_id,change='rollback',
        after={'actor_id':actor_id,'restored_publications':restored,'later_corrections_preserved':True}))
    session.flush()
    return dict(release_id=release_id,status='inactive',restored_publications=restored)
