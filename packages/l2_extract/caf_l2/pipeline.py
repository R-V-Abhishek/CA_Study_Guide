"""Native/OCR extraction into immutable candidates; current content changes on promotion."""
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import pymupdf as fitz
import sqlalchemy as sa
from sqlalchemy.orm import Session
from caf_common.blob_store import BlobStore
from caf_db.models.ingest import Document
from caf_db.models.ref import Paper
from caf_db.models.extraction import ExtractionRevision, ContentBlock, ExtractionAsset, DocumentPair
from caf_l2.blocks import build_block_stream
from caf_l2.overrides import apply_override, load_override
from caf_l2.pairing import flatten_units, pair_answers, pair_cross_doc_answers
from caf_l2.preflight import preflight_check
from caf_l2.profiles import load_profile, resolve_profile
from caf_l2.render import render_debug_html
from caf_l2.segmenter import Segmenter
from caf_l2.validators import DocumentValidator
from caf_l2.revisions import digest, unit_snapshot, assemble_questions, reconcile, promote_revision, pair_identity


class MetadataConflictError(ValueError):
    """Document content contradicts a navigation identity."""


@dataclass
class ExtractionSummary:
    document_id: int
    sha256: str
    extract_status: str
    page_count: int
    has_text_layer: bool
    total_units: int
    gradable_units: int
    validation_issues: list[dict[str, str]]
    debug_html_path: str | None = None
    revision_id: int | None = None
    revision_status: str = 'candidate'


class ExtractionPipeline:
    def __init__(self, blob_store: BlobStore, profiles_dir: Path, overrides_dir: Path,
                 debug_dir: Path | None = None, ocr_config=None):
        self.blob_store, self.profiles_dir = blob_store, profiles_dir
        self.overrides_dir, self.debug_dir, self.ocr_config = overrides_dir, debug_dir, ocr_config

    def _profile(self, doc, override=None):
        if override is not None:
            if not override.is_file():
                raise ValueError(f'Profile override does not exist: {override}')
            return load_profile(override)
        if not doc.scheme_id or not doc.doc_type_id:
            raise ValueError('unsupported_profile: scheme and document role metadata required')
        return resolve_profile(self.profiles_dir, doc.scheme_id, doc.doc_type_id, doc.paper_id)

    def extract_document(self, session: Session, document_id: int, run_id: int,
                         profile_override_path: Path | None = None, *, promote: bool = False,
                         allow_unconfirmed: bool = False) -> ExtractionSummary:
        doc = session.get(Document, document_id)
        if doc is None:
            raise ValueError(f'Document {document_id} not found')
        if doc.catalog_status != 'confirmed' and not allow_unconfirmed:
            raise ValueError('Confirm document metadata before extraction')
        if allow_unconfirmed and (promote or not doc.metadata_evidence.get('content_checked') or doc.metadata_evidence.get('conflicts')):
            raise ValueError('Draft extraction requires checked, nonconflicting metadata and cannot promote')
        if doc.course_level in {'foundation','intermediate'}:
            raise ValueError('Lower-level documents are outside the Final corpus')
        base_id = doc.current_revision_id
        try:
            profile = self._profile(doc, profile_override_path)
            supported_hashes = profile.raw_data.get('supported_source_hashes')
            if supported_hashes and doc.sha256 not in supported_hashes:
                raise ValueError('unsupported_profile: this source layout has no verified paper-specific profile')
            with fitz.open(stream=self.blob_store.read(doc.sha256), filetype='pdf') as pdf:
                preflight = preflight_check(pdf)
                content_start = profile.raw_data.get('source_page_start', 1)
                content_end = profile.raw_data.get('source_page_end', len(pdf))
                if content_start < 1 or content_end > len(pdf) or content_end < content_start:
                    raise ValueError('unsupported_profile: content page bounds outside source')
                ignored_pages = set(range(1,content_start)) | set(range(content_end+1,len(pdf)+1))
                lines = build_block_stream(pdf, ocr_config=self.ocr_config, source_hash=doc.sha256,
                    cache_dir=self.blob_store.base_dir / 'ocr', ignored_pages=ignored_pages)
                if any(line.page==1 and line.origin=='ocr' for line in lines):
                    heading='\n'.join(line.text for line in lines if line.page==1 and line.bbox[1]<pdf[0].rect.height*0.4)
                    normalized=re.sub(r'[^a-z0-9]','',heading.lower().replace('&','and'))
                    observed=[paper for paper in session.scalars(sa.select(Paper).where(Paper.scheme_id==doc.scheme_id))
                        if re.sub(r'[^a-z0-9]','',paper.name.lower().replace('&','and')) in normalized]
                    if len(observed)==1 and doc.paper_id and observed[0].id!=doc.paper_id:
                        doc.metadata_evidence={**doc.metadata_evidence,'ocr_heading':heading,
                            'conflicts':[*doc.metadata_evidence.get('conflicts',[]),
                                {'field':'paper_id','navigation':doc.paper_id,'content':observed[0].id,'origin':'ocr_header'}]}
                        doc.catalog_status='needs_curation'
                        session.commit()
                        raise MetadataConflictError(f'metadata_conflict: navigation assigns {doc.paper_id}; OCR source heading identifies {observed[0].id}')
                assets = []
                for number, page in enumerate(pdf, 1):
                    if page.get_images() or page.get_drawings():
                        assets.append({'page':number,'kind':'source_page','bbox':list(page.rect),
                            'concerns':['non_text_layout_requires_review']})
            doc.page_count, doc.has_text_layer = preflight.page_count, preflight.has_text_layer
            ranges = doc.paper_page_ranges or [{'paper_id':doc.paper_id,'page_start':1,'page_end':preflight.page_count}]
            covered = set()
            roots, all_answers, parsed_groups = [], {}, []
            paper_pages = {}
            for span in ranges:
                paper = span['paper_id']
                start, end = span['page_start'], span['page_end']
                if not paper or start < 1 or end < start or end > preflight.page_count:
                    raise ValueError('Invalid confirmed paper page range')
                pages = set(range(start, end + 1))
                if pages & covered:
                    raise ValueError('Overlapping paper ranges require source review')
                covered |= pages
                paper_pages.setdefault(paper,set()).update(pages)
            for paper, pages in paper_pages.items():
                range_lines = [line for line in lines if line.page in pages]
                segmenter = Segmenter(profile, doc.sha256)
                units = segmenter.segment(range_lines)
                override = load_override(self.overrides_dir, doc.sha256)
                if override:
                    units = apply_override(units, override)
                answers = pair_answers(units, mode=profile.mode, key_patterns=profile.patterns)
                # Prefix combined-paper labels before persistence and pairing.
                if len(paper_pages) > 1:
                    for unit in flatten_units(units):
                        old_label = unit.label_path
                        unit.label_path = f'{paper}/{old_label}'
                        if unit.parent_label_path:
                            unit.parent_label_path = f'{paper}/{unit.parent_label_path}'
                        if old_label in answers:
                            answer = answers.pop(old_label)
                            answer.label_path = unit.label_path
                            answers[unit.label_path] = answer
                all_answers.update(answers)
                parsed_groups.append((paper, units, segmenter.optional_pick))
            # A separate answer PDF is usable only through an administrator-confirmed pair.
            pairs = list(session.scalars(sa.select(DocumentPair).where(DocumentPair.question_document_id==doc.id, DocumentPair.status=='confirmed')))
            if len(pairs) > 1:
                raise ValueError('Ambiguous confirmed answer document pairs')
            pair_evidence = []
            if pairs:
                pair = pairs[0]
                answer_doc = session.get(Document, pair.answer_document_id)
                if pair_identity(doc) != pair_identity(answer_doc) or answer_doc.catalog_status != 'confirmed':
                    raise ValueError('Confirmed pair metadata changed; administrator review required')
                answer_profile = self._profile(answer_doc)
                if answer_profile.document_role not in {'answers','mixed'}:
                    raise ValueError('Paired document profile has no answer role')
                with fitz.open(stream=self.blob_store.read(answer_doc.sha256), filetype='pdf') as answer_pdf:
                    supported_hashes = answer_profile.raw_data.get('supported_source_hashes')
                    if supported_hashes and answer_doc.sha256 not in supported_hashes:
                        raise ValueError('unsupported_profile: paired answer source requires a verified layout profile')
                    answer_start = answer_profile.raw_data.get('source_page_start',1)
                    answer_end = answer_profile.raw_data.get('source_page_end',len(answer_pdf))
                    if answer_start<1 or answer_end>len(answer_pdf) or answer_end<answer_start:
                        raise ValueError('unsupported_profile: paired answer content page bounds outside source')
                    answer_lines = build_block_stream(answer_pdf, ocr_config=self.ocr_config, source_hash=answer_doc.sha256,
                        cache_dir=self.blob_store.base_dir / 'ocr',
                        ignored_pages=set(range(1,answer_start)) | set(range(answer_end+1,len(answer_pdf)+1)))
                    answer_doc.page_count = len(answer_pdf)
                answer_ranges = answer_doc.paper_page_ranges or [{'paper_id':answer_doc.paper_id,'page_start':1,'page_end':answer_doc.page_count}]
                answer_pages, covered_answers = {}, set()
                for span in answer_ranges:
                    pages=set(range(span['page_start'],span['page_end']+1))
                    if not pages or span['page_start']<1 or span['page_end']>answer_doc.page_count or pages & covered_answers:
                        raise ValueError('Invalid or overlapping confirmed answer paper ranges')
                    covered_answers |= pages
                    answer_pages.setdefault(span['paper_id'],set()).update(pages)
                if answer_pages.keys()!=paper_pages.keys():
                    raise ValueError('Confirmed pair requires matching paper-scoped question and answer ranges')
                all_answers = {}
                for paper,question_units,_ in parsed_groups:
                    answer_units = Segmenter(answer_profile,answer_doc.sha256).segment([
                        line for line in answer_lines if line.page in answer_pages[paper]])
                    answer_override=load_override(self.overrides_dir,answer_doc.sha256)
                    if answer_override:
                        answer_units=apply_override(answer_units,answer_override)
                    if len(paper_pages)>1:
                        for unit in flatten_units(answer_units):
                            unit.label_path=f'{paper}/{unit.label_path}'
                            if unit.parent_label_path:
                                unit.parent_label_path=f'{paper}/{unit.parent_label_path}'
                    all_answers.update(pair_cross_doc_answers(question_units,answer_units,answer_doc.id))
                pair_evidence = [{'pair_id':pair.id,'answer_document_id':answer_doc.id,'answer_sha256':answer_doc.sha256,
                    'answer_ranges':answer_ranges,'answer_profile':answer_profile.raw_data,
                    'answer_override':load_override(self.overrides_dir,answer_doc.sha256)}]
            expects_answers = profile.expects_answers or bool(pairs)
            # Validate each paper separately; answer-only sources retain blocks but do not create question duplicates.
            validators, issues, outcomes = [], [], []
            for paper, parsed, pick in parsed_groups:
                validation = DocumentValidator(profile, has_answers=expects_answers, optional_pick=pick).validate(parsed, all_answers)
                issues.extend({'code':i.code,'severity':i.severity,'message':i.message} for i in validation.issues)
                outcomes.append(validation.outcome)
                validators.append((parsed, validation))
                roots.extend(unit_snapshot(unit, all_answers, paper) for unit in parsed)
            if not roots:
                issues.append({'code':'empty_extraction','severity':'error','message':'No scoped question/answer anchors found; select a supported profile'})
            elif profile.document_role!='answers' and not any(unit.is_gradable for _,parsed,_ in parsed_groups for unit in flatten_units(parsed)):
                issues.append({'code':'missing_question_parts','severity':'error','message':'Case context was preserved but no attemptable question parts were found; check companion documents or layout'})
            if assets:
                issues.append({'code':'layout_review','severity':'warning','message':'Tables, formulas or diagrams require original-page review'})
            outcome = 'needs_review' if any(issue['severity']=='error' for issue in issues) or 'needs_review' in outcomes else 'ok_with_warnings' if issues else 'ok'
            issue_codes={issue['code'] for issue in issues}
            question_concerns={'empty_extraction','missing_question_parts','V5_UNIT_EMPTY','V6_MCQ_OPTIONS_MISSING'}
            answer_concerns={'V4_MISSING_ANSWER','V4_MISSING_ANSWERS_ERROR','V4_AMBIGUOUS_ANSWER','V6_MCQ_KEY_MISSING'}
            ordering_concerns={'AMBIGUOUS_REPEATED_LABEL','V1_QUESTION_GAP','V1_PART_GAP','V7_PAGE_SPAN_INVALID'}
            quality = {'outcome':outcome,'issues':issues,'metadata':'passed' if doc.catalog_status=='confirmed' else 'pending',
                'questions':'not_applicable' if profile.document_role=='answers' else 'concern' if issue_codes & question_concerns else 'pending',
                'answers':('concern' if issue_codes & answer_concerns else 'pending') if expects_answers else 'not_applicable',
                'pairing':('concern' if issue_codes & answer_concerns else 'pending') if expects_answers else 'not_applicable',
                'ordering':'concern' if issue_codes & ordering_concerns else 'pending',
                'marks_choices':'concern' if any(code.startswith(('V2_','V3_')) for code in issue_codes) else 'pending',
                'readability':'concern' if assets or any(line.origin=='ocr' for line in lines) else 'pending','human_review':'pending'}
            configuration = {'assembly_version':'phase4.complete-question.v5',
                'profile':profile.raw_data,'source_hash':doc.sha256,'paper_ranges':ranges,
                'pairing':pair_evidence,'ocr':str(self.ocr_config),'override':load_override(self.overrides_dir,doc.sha256),
                'excluded_frontmatter_pages':sorted(ignored_pages), 'metadata_identity':list(pair_identity(doc))}
            if doc.supersedes_document_id:
                predecessor = session.get(Document,doc.supersedes_document_id)
                configuration.update(predecessor_document_id=predecessor.id,predecessor_revision_id=predecessor.current_revision_id)
            payload_digest = digest({'configuration':configuration,'units':roots,'blocks':[(l.block_id,l.raw_text,l.bbox,l.origin) for l in lines]})
            existing = session.scalar(sa.select(ExtractionRevision).where(ExtractionRevision.document_id==doc.id,ExtractionRevision.content_digest==payload_digest))
            current = session.get(ExtractionRevision,base_id) if base_id else None
            if current and {k:v for k,v in current.configuration.items() if k!='revision_context'}==configuration and [r['content_digest'] for r in current.parsed_units]==[r['content_digest'] for r in roots]:
                existing=current
            elif existing and existing.base_revision_id!=base_id and existing.id!=base_id:
                # A previously superseded parse can be proposed again against the new current
                # revision, while keeping its old immutable lineage and reviews intact.
                configuration['revision_context']=base_id
                payload_digest = digest({'configuration':configuration,'units':roots,'blocks':[(l.block_id,l.raw_text,l.bbox,l.origin) for l in lines]})
                existing=session.scalar(sa.select(ExtractionRevision).where(ExtractionRevision.document_id==doc.id,ExtractionRevision.content_digest==payload_digest))
            if existing:
                revision = existing
            else:
                # Serialise candidate creation for a document; check again after lock for competing workers.
                session.execute(sa.select(Document.id).where(Document.id==doc.id).with_for_update())
                revision = session.scalar(sa.select(ExtractionRevision).where(ExtractionRevision.document_id==doc.id,ExtractionRevision.content_digest==payload_digest))
                if revision is None:
                    questions = [] if profile.document_role=='answers' else assemble_questions(session,doc,roots,payload_digest,expects_answers)
                    for question, root in zip(questions, roots):
                        question['assets'] = [{**asset, 'document_id':doc.id} for asset in assets
                            if root['page_start'] <= asset['page'] <= root['page_end']]
                    revision = ExtractionRevision(document_id=doc.id,run_id=run_id,base_revision_id=base_id,
                        content_digest=payload_digest,profile_id=profile.id,configuration=configuration,quality=quality,
                        questions=questions,parsed_units=roots)
                    session.add(revision)
                    session.flush()
                    for order,line in enumerate(lines):
                        session.add(ContentBlock(revision_id=revision.id,block_key=line.block_id,sequence=order,page=line.page,
                            bbox=list(line.bbox),raw_text=line.raw_text or line.text,normalized_text=line.text,origin=line.origin))
                    for asset in assets:
                        session.add(ExtractionAsset(revision_id=revision.id,**asset))
                    reconcile(session,revision)
            debug_path = None
            if self.debug_dir and validators:
                debug_path = str(render_debug_html(doc.sha256,lines,validators[0][0],validators[0][1],self.debug_dir))
            # Candidate creation never overwrites current status/content. Initial state can report parse outcome.
            if doc.current_revision_id is None:
                doc.extract_status = outcome
            session.commit()
            if promote:
                promote_revision(session,revision.id,base_id)
                session.commit()
            from caf_l2.revisions import flatten_snapshots
            flat = flatten_snapshots(roots)
            return ExtractionSummary(doc.id,doc.sha256,outcome,preflight.page_count,preflight.has_text_layer,
                len(flat),sum(u['is_gradable'] for u in flat),issues,debug_path,revision.id,revision.status)
        except Exception as exc:
            session.rollback()
            # Current content remains available even when parsing fails.
            failed = session.get(Document,document_id)
            error_code = 'metadata_conflict' if type(exc) is MetadataConflictError else 'unsupported_profile' if 'profile' in str(exc).lower() else 'ocr_unavailable' if 'ocr' in str(exc).lower() else 'failed'
            failure_digest = digest({'source_hash':failed.sha256,'error':str(exc),'base':base_id})
            if session.scalar(sa.select(ExtractionRevision.id).where(ExtractionRevision.document_id==document_id,ExtractionRevision.content_digest==failure_digest)) is None:
                session.add(ExtractionRevision(document_id=document_id,run_id=run_id,base_revision_id=base_id,
                    status='failed',content_digest=failure_digest,profile_id='unresolved',configuration={'source_hash':failed.sha256},
                    quality={'outcome':error_code,'issues':[{'code':error_code,'severity':'error','message':str(exc)}]},questions=[],parsed_units=[]))
            if failed.current_revision_id is None:
                failed.extract_status = 'failed'
            session.commit()
            raise
