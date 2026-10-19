"""Read-only live corpus inspection and source-backed successor preparation."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import sqlalchemy as sa
from sqlalchemy.orm import Session
import typer
import fitz
from caf_db.engine import get_engine
from caf_db.models.classification import ClassificationRevision, SuggestionRevision
from caf_db.models.extraction import ExtractionRevision, ExtractionReview
from caf_db.models.ingest import Document
from caf_db.models.intel import AttemptTaxonomyBinding, CorpusCoverage, ReviewedPrior
from caf_db.models.questions import PublishedQuestion
from caf_db.models.taxonomy import TaxonomyRelease, NodeSourceSpan, DescriptorApproval

app = typer.Typer()


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@app.command()
def inspect(repo: Path, report: Path, successor: Path):
    os.chdir(repo)
    batch = json.loads(Path('artifacts/phase5/independent30.json').read_text())
    selected = batch['records'][24]
    with Session(get_engine('operations')) as session, session.begin():
        session.execute(sa.text('SET TRANSACTION READ ONLY'))
        counts = {model.__tablename__: session.scalar(sa.select(sa.func.count()).select_from(model))
                  for model in (ClassificationRevision, SuggestionRevision, PublishedQuestion,
                                AttemptTaxonomyBinding, CorpusCoverage, ReviewedPrior, ExtractionReview,
                                DescriptorApproval)}
        reviewed_bindings = session.scalar(sa.select(sa.func.count()).select_from(AttemptTaxonomyBinding).where(
            AttemptTaxonomyBinding.status == 'reviewed', AttemptTaxonomyBinding.reviewed_by.is_not(None)))
        reviewed_spans = session.scalar(sa.select(sa.func.count()).select_from(NodeSourceSpan).where(
            NodeSourceSpan.review_status == 'reviewed', NodeSourceSpan.reviewed_by.is_not(None)))
        unknown_inventory = session.scalar(sa.select(sa.func.count()).select_from(CorpusCoverage).where(
            CorpusCoverage.expected_slots.is_(None)))
        releases = [{'version_id':r.version_id,'status':r.status,'manifest_hash':r.manifest_hash,'approved_by':r.approved_by}
                    for r in session.scalars(sa.select(TaxonomyRelease).order_by(TaxonomyRelease.taxonomy_version_id))]
        document = session.get(Document,selected['document_id'])
        revision = session.get(ExtractionRevision,selected['extraction_revision_id'])
        if document.sha256 != selected['document_sha256'] or revision.content_digest != selected['extraction_digest']:
            raise ValueError('Frozen investigation inputs no longer match their exact database revision')
        path = Path(document.blob_path)
        if not path.is_absolute():
            path = repo / path
        if checksum(path) != document.sha256:
            raise ValueError('Source bytes differ from frozen recorded evidence')
        with fitz.open(path) as pdf:
            text = pdf[0].get_text()
            if 'compulsory' not in text.lower() or 'question paper' not in text.lower():
                raise ValueError('Source page does not support the instruction-only correction')
            page_image = report.parent / 'Phase7_Instruction_Source.png'
            pdf[0].get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(page_image)
        units = deepcopy(revision.parsed_units)
        label = selected['context']['label_path']
        changed = []
        def exclude_instructions(nodes):
            for node in nodes:
                if node['label_path'] == label:
                    if node['children']:
                        raise ValueError('Instruction correction must not silently remove descendant questions')
                    if 'compulsory' not in node['question_text'].lower():
                        raise ValueError('Frozen instruction node changed')
                    node['is_gradable'] = False
                    changed.append(label)
                exclude_instructions(node['children'])
        exclude_instructions(units)
        if changed != [label]:
            raise ValueError('Expected exactly one instruction-only node')
        draft = {'status':'prepared_unreviewed_successor', 'document_id':document.id,
            'document_sha256':document.sha256,'base_revision_id':revision.id,
            'base_content_digest':revision.content_digest,'question_id':selected['question_id'],
            'source_page':1, 'reason':'Page 1 exam instructions were incorrectly classified as a gradable unit.',
            'change':{'label_path':label,'is_gradable':False},'parsed_units':units,
            'required_next_action':'Create an audited successor extraction candidate, review full root accounting, then promote as an authenticated administrator. Do not edit the historical revision.',
            'human_approvals_created':0}
        successor.write_text(json.dumps(draft,indent=2)+'\n')
        result = {'observed_at':datetime.now(timezone.utc).isoformat(), 'transaction_read_only':True,
            'counts':counts,'reviewed_bindings':reviewed_bindings,'reviewed_source_spans':reviewed_spans,
            'unknown_expected_inventory_rows':unknown_inventory,'releases':releases,
            'frozen_batch_sha256':checksum(Path('artifacts/phase5/independent30.json')),
            'instruction_successor':{'document_id':document.id,'revision_id':revision.id,
                'revision_status':revision.status,'current_revision_id':document.current_revision_id,
                'source_sha256':document.sha256,'label_path':label,'source_page':1,
                'source_image_sha256':checksum(page_image),'prepared_path':str(successor)},
            'writes_to_database':0,'human_approvals_created':0}
        report.write_text(json.dumps(result,indent=2)+'\n')
        typer.echo(json.dumps({'counts':counts,'instruction_draft':str(successor),'writes_to_database':0},indent=2))


if __name__ == '__main__':
    app()
