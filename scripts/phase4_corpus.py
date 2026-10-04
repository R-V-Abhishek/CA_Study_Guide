"""Import verified source bytes and prepare curator candidates without human approvals."""
from calendar import month_name
import json
from pathlib import Path
from collections import Counter
import sqlalchemy as sa
import typer
from caf_common.blob_store import BlobStore
from caf_common.settings import get_settings
from caf_common.run_context import open_run
from caf_db.engine import get_session_factory
from caf_db.models.ingest import Document, DiscoveredLink
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ref import Attempt
from caf_l1.artifacts import validate_pdf, validate_metadata, record_observation
from caf_l2.pipeline import ExtractionPipeline
from caf_l2.blocks import OCRConfig

app=typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
def prepare(coverage:Path=Path('docs/Phase4_Source_Coverage.json'),limit:int=typer.Option(250,min=1,max=1000),
            commit:bool=typer.Option(False,'--commit'),ocr:bool=typer.Option(False,'--ocr'),report:Path=Path('docs/Phase4_Extraction_Coverage.json')):
    sources=json.loads(coverage.read_text())['records']
    selected=[row for row in sources if row.get('artifact_acquired') and row['course_level'].lower()=='final' and row['scheme_id']=='s2023'][:limit]
    if not commit:
        typer.echo(json.dumps({'documents':len(selected),'database_changed':False,
            'sources':[{'inventory_id':r['inventory_id'],'paper_id':r['paper_id'],'attempt_id':r['attempt_id'],'sha256':r.get('sha256')} for r in selected]},indent=2))
        return
    settings=get_settings();store=BlobStore(settings.storage.blob_dir)
    pipeline=ExtractionPipeline(store,Path('profiles'),Path('overrides'),Path('data/debug'),
        ocr_config=OCRConfig() if ocr else None)
    output=[];failures=[]
    with get_session_factory('operations')() as db,open_run(stage='phase4_candidates',args={'coverage':str(coverage),'limit':limit}) as run:
        for row in selected:
            evidence_path=row['blob_path']
            if not evidence_path:
                output.append({'inventory_id':row['inventory_id'],'outcome':'missing_registered_path'});failures.append(row['inventory_id']);continue
            path=Path(evidence_path)
            data=path.read_bytes();sha,blob=store.put(data)
            if sha!=row['sha256']:raise ValueError('Acquisition digest changed; stop import')
            verified=validate_pdf(data)
            metadata=validate_metadata(row['metadata'],verified)
            if metadata['attempt_id'] and db.get(Attempt,metadata['attempt_id']) is None:
                year,month=map(int,metadata['attempt_id'].split('-'))
                db.add(Attempt(id=metadata['attempt_id'],exam_year=year,exam_month=month,label=f'{month_name[month]} {year}',verified=False))
                db.flush()
            link=db.scalar(sa.select(DiscoveredLink).where(DiscoveredLink.url==row['original_url']))
            previous=db.get(Document,link.document_id) if link is not None and link.document_id else None
            doc=db.scalar(sa.select(Document).where(Document.sha256==sha))
            if doc is None:
                doc=Document(sha256=sha,blob_path=str(blob),bytes=len(data),origin='http',provenance_status='verified',
                    course_level='final',scheme_id=metadata['scheme_id'],paper_id=metadata['paper_id'],attempt_id=metadata['attempt_id'],
                    collection_id=metadata['collection_id'],doc_type_id=metadata['doc_type_id'],series=metadata['series'],title=metadata['title'],
                    catalog_status=metadata['catalog_status'],metadata_evidence=metadata['metadata_evidence'],paper_page_ranges=metadata.get('paper_page_ranges') or [],
                    page_count=verified.page_count,has_text_layer=verified.has_text_layer,created_run_id=run.id)
                if previous and previous.sha256!=sha:
                    doc.supersedes_document_id=previous.id
                db.add(doc);db.flush()
            elif not doc.metadata_evidence.get('content_checked'):
                doc.metadata_evidence={**doc.metadata_evidence,**metadata['metadata_evidence']}
            if link is None:
                link=DiscoveredLink(url=row['original_url'],anchor_text=metadata['title'],link_status='downloaded',document_id=doc.id,
                    inferred={'inventory_associations':[row['inventory_id']],'source_metadata':metadata})
                db.add(link)
            elif link.document_id!=doc.id:
                link.document_id=doc.id;link.link_status='downloaded'
            record_observation(store,sha,origin='http',original_url=row['original_url'],final_url=row.get('final_url'),metadata=metadata)
            db.commit()
            result={'inventory_id':row['inventory_id'],'document_id':doc.id,'sha256':sha,'paper_id':doc.paper_id,'attempt_id':doc.attempt_id,
                'family':row['source_family'],'profile':None,'metadata_confirmation':doc.catalog_status,'human_review':'pending'}
            conflicts=doc.metadata_evidence.get('conflicts',[])
            if conflicts or metadata['metadata_evidence']['conflicts'] or not doc.paper_id and not doc.paper_page_ranges:
                result.update(outcome='metadata_review',reason='Confirm conflicting role/identity or combined-paper ranges',
                    conflicts=conflicts or metadata['metadata_evidence']['conflicts'])
            elif doc.provenance_status!='verified':
                result.update(outcome='provenance_review',reason='Existing document source identity requires review')
            else:
                try:
                    summary=pipeline.extract_document(db,doc.id,run.id,allow_unconfirmed=doc.catalog_status!='confirmed')
                    revision=db.get(ExtractionRevision,summary.revision_id)
                    result.update(outcome='candidate',revision_id=summary.revision_id,quality_outcome=summary.extract_status,
                        profile=revision.profile_id,quality=revision.quality,
                        units=summary.total_units,gradable_units=summary.gradable_units,issue_count=len(summary.validation_issues),
                        issue_codes=dict(Counter(issue['code'] for issue in summary.validation_issues)),issues=summary.validation_issues[:20])
                    result['quality']={key:value for key,value in revision.quality.items() if key!='issues'}
                except Exception as exc:
                    result.update(outcome='extraction_failure',reason=str(exc));failures.append(doc.id)
            output.append(result)
            report.write_text(json.dumps({'source_report':str(coverage),'promotions':0,'approvals':0,'records':output},indent=2)+'\n')
        run.stats={'documents':len(output),'candidates':sum(r['outcome']=='candidate' for r in output),'failures':failures}
        if failures:raise RuntimeError(f'{len(failures)} extraction failures; inspect {report}')
    typer.echo(f'Prepared {len(output)} source outcomes without promotions or approvals: {report}')
    if failures:raise typer.Exit(1)


if __name__=='__main__':app()
