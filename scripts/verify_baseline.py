"""Verify the adopted persistent corpus through normal read APIs and database roles."""
import json
from pathlib import Path
import time
import sqlalchemy as sa
import typer

from caf_db.engine import get_session_factory
from caf_db.models.classification import BaselineAdoption, SuggestionRevision
from caf_db.models.taxonomy import TaxonomyRelease
from caf_l3.baseline_pack import EXPECTED_PAPERS


def main(output: Path = Path('docs/Baseline_2026_10_16_Verification.json'),
         database_bytes_before: int | None = None):
    from caf_api.auth import Principal
    from caf_api.curate import classification_queue, candidate_catalog
    from caf_api.questions import question, search, source_page, source_file
    from caf_contracts.classification import ClassificationQueueItem
    from caf_l4.baseline import rollback_baseline
    from caf_l5.context import resolve_context, context_nodes
    from caf_common.settings import get_settings
    from caf_l2.revisions import digest
    account=Principal(1,'Administrator',None,'administrator','active')
    report={}
    with get_session_factory()() as db:
        adoption=db.get(BaselineAdoption,'baseline-2026-10-16')
        assert adoption.status=='active'
        release=db.get(TaxonomyRelease,adoption.release_id)
        report.update(release_id=adoption.release_id,manifest_hash=adoption.manifest_hash,
            taxonomy_version_id=release.taxonomy_version_id)
        report['database_bytes']=db.scalar(sa.text('select pg_database_size(current_database())'))
        report['database_bytes_before']=database_bytes_before
        report['database_growth_bytes']=report['database_bytes']-database_bytes_before if database_bytes_before is not None else None
        report['roots']=db.scalar(sa.text('select count(*) from core.question_publication where current_snapshot_id is not null'))
        report['parts']=db.scalar(sa.text('select sum(jsonb_array_length(mappings)) from core.published_question'))
        report['prior_suggestions']=db.scalar(sa.select(sa.func.count()).select_from(SuggestionRevision).where(
            SuggestionRevision.taxonomy_version_id!=release.taxonomy_version_id))
        report['student_verifications']=db.scalar(sa.text('select count(*) from core.classification_verification'))
        report['catalog_nodes']=db.scalar(sa.text("select count(distinct c->>'node_id') from ref.candidate_catalog, jsonb_array_elements(candidates) c"))
        report['hierarchy_nodes']=db.scalar(sa.text('select count(*) from ref.taxonomy_member where taxonomy_version_id=:version'),{'version':release.taxonomy_version_id})
        report['question_sources']=db.scalar(sa.text('select count(*) from core.published_source'))
        report['per_paper']={paper:dict(roots=roots,parts=parts) for paper,roots,parts in db.execute(sa.text(
            "select content->>'paper_id', count(*), sum(jsonb_array_length(mappings)) from core.published_question group by 1 order by 1"))}
        report['mapping_outcomes']={status:count for status,count in db.execute(sa.text(
            "select mapping->>'outcome',count(*) from core.published_question, jsonb_array_elements(mappings) mapping group by 1"))}
        report['answer_statuses']={status:count for status,count in db.execute(sa.text(
            "select content->>'answer_status',count(*) from core.published_question group by 1"))}
        report['corrected_paper_roots']=db.scalar(sa.text("""select count(*) from core.published_question p
            join ingest.extraction_revision e on e.id=p.extraction_revision_id,
            jsonb_array_elements(e.questions) q where q->>'question_id'=p.question_id
            and q->>'paper_id'<>p.content->>'paper_id'"""))
        assert (report['roots'],report['parts'],report['catalog_nodes'],report['question_sources'],
            report['corrected_paper_roots'],report['prior_suggestions'],report['student_verifications'])==(3009,7778,3300,94,691,120,0)
        for paper,(roots,parts) in EXPECTED_PAPERS.items():
            assert report['per_paper']['s2023.'+paper]==dict(roots=roots,parts=parts)
        samples=list(db.execute(sa.text("select distinct on (content->>'answer_status') question_id,content->>'answer_status' from core.published_question order by content->>'answer_status',question_id")))
        node_id=db.scalar(sa.text("select c->>'node_id' from ref.candidate_catalog,jsonb_array_elements(candidates) c where c->>'paper_id'='s2023.P5' limit 1"))
    with get_session_factory('student')() as db:
        context=resolve_context(db,1)
        assert context.target_attempt_id=='2027-05'
        assert node_id in {node.id for node in context_nodes(db,context,study=True)}
        report['study_target']=context.target_attempt_id
        report['uncertain_applicability_nodes']=len(context.unresolved_node_ids)
        report['reader_samples']=[]
        for question_id,status in samples:
            result=question(question_id,db)
            assert result.content.answer_status==status and result.verification_count==0
            assert result.extraction_quality['baseline']['release_id']==report['release_id']
            source=result.sources[0]
            page=next((span.page_start for span in result.content.source_spans
                if span.document_sha256==source.sha256),1)
            image=source_page(source.id,page,db)
            pdf=source_file(source.id,db)
            assert image.media_type=='image/png' and len(image.body)>1000
            assert pdf.media_type=='application/pdf' and bytes(pdf.body).startswith(b'%PDF')
            report['reader_samples'].append(dict(question_id=question_id,answer_status=status,
                source_id=source.id,page=page,page_bytes=len(image.body),pdf_bytes=len(pdf.body)))
        started=time.perf_counter()
        result=search(q='audit',page=1,page_size=25,paper_id=None,subtopic_id=None,
            attempt_id=None,source_family=None,answer_status=None,include_notes=False,account=account,db=db)
        report['search']=dict(seconds=round(time.perf_counter()-started,4),total=result.total,returned=len(result.items))
        assert result.total>0
    with get_session_factory('curation')() as db:
        started=time.perf_counter()
        rows=classification_queue(paper_id=None,source=None,outcome=None,question_id=None,
            taxonomy_version_id=report['taxonomy_version_id'],experimental=None,ready=None,disputed=None,
            blind=False,benchmark_only=False,limit=100,offset=0,session=db,account=account)
        encoded=[ClassificationQueueItem.model_validate(row).model_dump(mode='json') for row in rows]
        report['review_queue']=dict(seconds=round(time.perf_counter()-started,4),roots=len(rows),
            json_bytes=len(json.dumps(encoded).encode()),shared_catalogs=len({r['candidate_catalog_hash'] for r in rows}))
        assert len(rows)==100 and all(r['publication_ready'] and not r['candidates'] for r in rows)
        catalog=candidate_catalog(rows[0]['candidate_catalog_hash'],db)
        assert catalog and digest(catalog)==rows[0]['candidate_catalog_hash']
    # Exercise the actual release rollback in a transaction, then discard this
    # drill so the accepted release and all personal records remain unchanged.
    with get_session_factory()() as db:
        result=rollback_baseline(db,report['release_id'],report['manifest_hash'],1)
        assert result['restored_publications']==3009
        assert db.scalar(sa.text('select count(*) from core.question_publication where current_snapshot_id is not null'))==0
        db.rollback()
        assert db.get(BaselineAdoption,report['release_id']).status=='active'
        assert db.scalar(sa.text('select count(*) from core.question_publication where current_snapshot_id is not null'))==3009
        report['rollback_drill']='passed; transaction discarded, active baseline retained'
    before=Path('data/backups/pre-baseline-2026-10-16/caf_20261016_172904_002212_a19cd0fb/blobs')
    after=Path(get_settings().storage.blob_dir)
    def inventory(root):
        files=[p for p in root.rglob('*') if p.is_file()]
        return dict(files=len(files),bytes=sum(p.stat().st_size for p in files))
    report['source_storage']={'before':inventory(before),'after':inventory(after)}
    report['source_storage']['growth_bytes']=report['source_storage']['after']['bytes']-report['source_storage']['before']['bytes']
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    typer.run(main)
