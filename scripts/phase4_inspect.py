"""Read-only extraction coverage, contract fidelity and preservation evidence."""
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import Session
import typer
from caf_common.backup import file_checksum
from caf_contracts.extraction import ExtractedQuestion
from caf_db.engine import get_engine
from caf_db.models.ingest import Document
from caf_db.models.extraction import ExtractionRevision, ExtractionReview
from caf_db.models.taxonomy import TaxonomyRelease
from caf_l0.releases import eligible_candidates
from caf_l2.revisions import family, reviewed_quality, flatten_snapshots

app=typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
def inspect(coverage:Path=Path('docs/Phase4_Extraction_Coverage.json'),
            checkpoint:Path=Path('data/backups/caf_20261004_065300_623687_62ed5893/manifest.json'),
            report:Path=Path('docs/Phase4_Runtime_Inspection.json')):
    source=json.loads(Path('docs/Phase4_Source_Coverage.json').read_text())
    extracted=json.loads(coverage.read_text())
    by_source={row['inventory_id']:row for row in extracted['records']}
    counts=Counter(); states=Counter(); contracts=Counter(); issues=[]; candidates=[]; seen_revisions=set()
    with get_engine('backup').connect() as connection,connection.begin():
        connection.execute(sa.text('SET TRANSACTION READ ONLY'))
        db=Session(bind=connection)
        for row in source['records']:
            outcome=by_source.get(row['inventory_id'])
            state=outcome['outcome'] if outcome else row['outcome']
            if row['artifact_acquired'] and outcome is None:
                state='not_selected_for_extraction'
            profile=outcome.get('profile') if outcome else None
            counts[(row['paper_id'] or 'combined_or_unresolved',row['attempt_id'] or row.get('collection_id') or 'undated',
                row['source_family'],profile or 'unresolved',state)]+=1
            if outcome and outcome['outcome']=='candidate':
                if outcome['revision_id'] in seen_revisions:
                    continue
                seen_revisions.add(outcome['revision_id'])
                revision=db.get(ExtractionRevision,outcome['revision_id'])
                doc=db.get(Document,revision.document_id)
                quality=reviewed_quality(db,revision)
                for dimension in ('metadata','questions','answers','pairing','ordering','marks_choices','readability','human_review'):
                    states[(dimension,quality.get(dimension,'pending'))]+=1
                for question in revision.questions:
                    ExtractedQuestion.model_validate(question)
                    if question['common_stem'] and question['common_stem']==question['question_text']:
                        raise ValueError('Assembled question duplicates its shared stem')
                    contracts['questions_validated']+=1
                    contracts['answer_'+question['answer_status']]+=1
                    contracts['pairing_'+question['pairing_status']]+=1
                    source_docs={db.get(Document,key).sha256:db.get(Document,key) for key in question['source_document_ids']}
                    def check_parts(parts):
                        for part in parts:
                            for span in part['source_spans']:
                                source_doc=source_docs.get(span['document_sha256'])
                                if source_doc is None or not 1<=span['page_start']<=span['page_end']<=source_doc.page_count:
                                    raise ValueError('Assembled part has an invalid source span')
                            check_parts(part['parts'])
                    check_parts(question['parts']);check_parts(question['answers'])
                candidates.append({'document_id':doc.id,'revision_id':revision.id,'profile':revision.profile_id,
                    'paper_id':doc.paper_id,'attempt_id':doc.attempt_id,'family':family(doc.doc_type_id),
                    'root_count':len(revision.questions),'part_count':sum(n['is_gradable'] for n in flatten_snapshots(revision.parsed_units)),
                    'quality':{key:value for key,value in quality.items() if key!='issues'}})
        baseline=json.loads(checkpoint.read_text())
        original=baseline['tables']
        preserved_names=[name for name in original if name.startswith(('app.','core.')) or name in {
            'ref.node','ref.node_version_link','ref.taxonomy_release','ref.taxonomy_member','ref.textbook_artifact',
            'ref.node_source_span','ref.descriptor_revision','ref.descriptor_approval','ref.taxonomy_crosswalk',
            'ingest.unit','ingest.unit_answer','ingest.tag_suggestion','ingest.unit_gist'}]
        tables={}
        connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
        quote=connection.dialect.identifier_preparer.quote
        for table in preserved_names:
            schema,name=table.split('.')
            columns=','.join(quote(column['name']) for column in baseline['schema'][table]['columns'])
            query=f'SELECT to_jsonb(t)::text FROM (SELECT {columns} FROM {quote(schema)}.{quote(name)}) t ORDER BY to_jsonb(t)::text COLLATE "C"'
            hasher=hashlib.sha256();count=0
            for row in connection.execute(sa.text(query)):
                hasher.update(row[0].encode()+b'\n');count+=1
            tables[table]={'count':count,'sha256':hasher.hexdigest()}
        mismatches=[name for name in preserved_names if original[name]!=tables[name]]
        if mismatches:
            issues.append({'code':'preservation_mismatch','tables':mismatches})
        releases=[{'version_id':r.version_id,'status':r.status,'target_attempt':r.target_attempt,
            'eligible_by_paper':{f's2023.P{i}':len(eligible_candidates(db,r.taxonomy_version_id,f's2023.P{i}')) for i in range(1,7)}}
            for r in db.scalars(sa.select(TaxonomyRelease).order_by(TaxonomyRelease.version_id)) if r.status!='legacy']
        review_count=db.scalar(sa.select(sa.func.count()).select_from(ExtractionReview))
    fixtures=[]
    for path in sorted(Path('profiles/fixtures').glob('*.json')):
        fixture=json.loads(path.read_text())
        fixtures.append({'fixture':str(path),'paper_id':fixture['paper'],'doc_type':fixture['doc_type'],
            'source_sha256':fixture['source_sha256'],'source_pages':fixture['source_pages'],
            'source_hash_verified':file_checksum(Path(fixture['source_file']))==fixture['source_sha256'],
            'expected_tree':'agent_checked_regression','authenticated_human_review':'pending'})
    expected=[]
    for paper in [f's2023.P{i}' for i in range(1,7)]:
        for kind in ('rtp','mtp_question','mtp_answer','model_question','model_answer','question_paper','suggested_answer','ibs_case_study','case_scenarios'):
            if kind in ('ibs_case_study','case_scenarios') and paper!='s2023.P6':
                continue
            examples=[f['fixture'] for f in fixtures if f['paper_id']==paper and f['doc_type']==kind]
            expected.append({'paper_id':paper,'doc_type':kind,'fixtures':examples,
                'status':'agent_checked_human_review_pending' if examples else 'authentic_fixture_gap'})
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'database_writes':False,
        'completion_gate_passed':False,'source_inventory_count':len(source['records']),
        'acquired_artifact_associations':sum(row['artifact_acquired'] for row in source['records']),
        'distinct_acquired_hashes':len({row['sha256'] for row in source['records'] if row['artifact_acquired']}),
        'extraction_outcomes':dict(Counter(row['outcome'] for row in extracted['records'])),
        'coverage':[{'paper_id':key[0],'attempt_or_collection':key[1],'family':key[2],'profile':key[3],'state':key[4],'count':count}
            for key,count in sorted(counts.items())],
        'quality_states':[{'dimension':key[0],'state':key[1],'count':count} for key,count in sorted(states.items())],
        'whole_question_contracts':dict(contracts),'candidates':candidates,'actual_extraction_reviews':review_count,
        'preservation':{'checkpoint':str(checkpoint),'tables_checked':len(preserved_names),'all_original_values_preserved':not mismatches,
            'tables':{name:tables[name] for name in preserved_names}},
        'taxonomy_classification_readiness':releases,'authentic_fixtures':fixtures,'authentic_fixture_matrix':expected,'issues':issues}
    report.write_text(json.dumps(result,indent=2)+'\n')
    typer.echo(json.dumps({'report':str(report),'candidates':len(candidates),'contracts':dict(contracts),'issues':issues}))
    if issues:raise typer.Exit(1)


if __name__=='__main__':app()
