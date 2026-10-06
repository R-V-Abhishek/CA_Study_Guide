"""Freeze the live, draft pilot and evaluation inputs without publishing content."""

import json
from pathlib import Path

import sqlalchemy as sa
from caf_db.engine import get_session_factory
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.ref import DocType
from caf_l2.revisions import flatten_snapshots
from caf_l3.batches import export_batch
from caf_l3.sampling import stratified_sample


def main():
    output = Path('artifacts/phase5')
    output.mkdir(parents=True, exist_ok=True)
    with get_session_factory('operations')() as session:
        latest = sa.select(sa.func.max(ExtractionRevision.id)).group_by(ExtractionRevision.document_id)
        revisions = list(session.scalars(sa.select(ExtractionRevision).join(Document,
            ExtractionRevision.document_id == Document.id).join(DocType,
            DocType.id == Document.doc_type_id).where(ExtractionRevision.id.in_(latest),
                ExtractionRevision.status != 'failed', Document.superseded.is_(False),
                Document.course_level == 'final', DocType.has_questions.is_(True)).order_by(ExtractionRevision.id)))
        records = []
        for revision in revisions:
            snapshots = {n['stable_question_id']: n for n in revision.parsed_units}
            for question in revision.questions:
                root = snapshots[question['question_id']]
                ids = [question['question_id'] if n is root else question['question_id'] + ':' + n['label_path']
                    for n in flatten_snapshots([root]) if n['is_gradable']]
                if ids:
                    records.append(dict(question_id=question['question_id'], document_id=revision.document_id,
                        extraction_revision_id=revision.id, context={**question, 'classification_part_ids': ids}))
        sample = stratified_sample(records)
        (output / 'sample.json').write_text(json.dumps(sample, indent=2))
        roots = sample['roots']
        batch = export_batch(session, 'textbook-v1', sorted({r['extraction_revision_id'] for r in roots}),
            draft=True, question_ids=[r['question_id'] for r in roots])
        (output / 'sample120.json').write_text(json.dumps(batch, ensure_ascii=False, indent=2))
        for name, flag in [('pilot12', 'pilot'), ('independent30', 'blind_comparison')]:
            subset = [r for r in roots if r[flag]]
            frozen = export_batch(session, 'textbook-v1', sorted({r['extraction_revision_id'] for r in subset}),
                draft=True, question_ids=[r['question_id'] for r in subset])
            (output / (name + '.json')).write_text(json.dumps(frozen, ensure_ascii=False, indent=2))
        print(json.dumps({'available_roots': len(records), 'selected': len(roots),
            'pilot': sum(r['pilot'] for r in roots), 'independent': sum(r['blind_comparison'] for r in roots),
            'unavailable': sample['unavailable_strata']}))


if __name__ == '__main__':
    main()
