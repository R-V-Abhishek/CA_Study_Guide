"""Resume frozen Phase 5 experiments and report provisional model comparisons."""

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import statistics

import sqlalchemy as sa
import typer
from caf_db.engine import get_session_factory
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.ref import DocType
from caf_db.models.classification import SuggestionRevision, ClassificationRevision, ClassificationVerification, QuestionPublication
from caf_contracts.extraction import ExtractedQuestion
from caf_l2.revisions import flatten_snapshots
from caf_l3.batches import validated_mappings, validate_manifest
from caf_l3.evaluate import evaluate_revision_pairs
from caf_l3.sampling import duplicate_key

app = typer.Typer(pretty_exceptions_show_locals=False)
ROOT = Path('artifacts/phase5')


@dataclass
class FrozenReview:
    input_hash: str
    context: dict
    mappings: list[dict]
    taxonomy_version_id: int
    blind: bool = True


@dataclass
class FrozenSuggestion:
    input_hash: str
    context: dict
    mappings: list[dict]
    taxonomy_version_id: int
    candidates: list[dict]
    experimental: bool = True


def comparison_metrics(pairs: list[tuple]) -> dict:
    report = asdict(evaluate_revision_pairs(pairs, provisional=True))
    report['evaluated_at'] = report['evaluated_at'].isoformat()
    label_matches = total = 0
    for reviewed, suggestion in pairs:
        by_part = {mapping['part_id']: mapping for mapping in reviewed.mappings}
        for model in suggestion.mappings:
            human = by_part[model['part_id']]
            model_labels = set(filter(None, [model['primary_node_id'], *model['secondary_node_ids']]))
            human_labels = set(filter(None, [human['primary_node_id'], *human['secondary_node_ids']]))
            label_matches += model_labels == human_labels
            total += 1
    report['exact_part_label_set_agreement'] = label_matches/total if total else 0
    return report


@app.command()
def seed():
    """Reuse validated pilot completions for the identical frozen sample inputs."""
    manifest = json.loads((ROOT/'sample120.json').read_text())
    validate_manifest(manifest)
    output = ROOT/'luna-sample120'
    output.mkdir(exist_ok=True)
    copied = 0
    for record in manifest['records']:
        source = ROOT/'luna-pilot-v2'/(record['question_id'] + '.json')
        target = output/source.name
        if not source.exists():
            continue
        saved = json.loads(source.read_text())
        validated_mappings(record, saved['result'])
        if target.exists() and json.loads(target.read_text()) != saved:
            raise ValueError('A different immutable sample completion already exists')
        if not target.exists():
            shutil.copy2(source, target)
            events = source.with_suffix('.events.jsonl')
            if events.exists():
                shutil.copy2(events, output/events.name)
            copied += 1
    typer.echo(f'Reused {copied} validated completions without new model calls')


@app.command()
def report():
    """Compare frozen independent agent labels with validated Luna results."""
    manifest = json.loads((ROOT/'sample120.json').read_text())
    independent = json.loads((ROOT/'independent30_labels.json').read_text())
    sample = json.loads((ROOT/'sample.json').read_text())
    partitions = {root['question_id']: root['partition'] for root in sample['roots']}
    validate_manifest(manifest)
    records = {r['question_id']: r for r in manifest['records']}
    pairs, completed, seconds, usage = [], [], [], Counter()
    outcomes, paper_roots, partition_roots = Counter(), Counter(), Counter()
    for question_id, record in records.items():
        path = ROOT/'luna-sample120'/(question_id + '.json')
        if not path.exists():
            continue
        saved = json.loads(path.read_text())
        mappings = validated_mappings(record, saved['result'])
        completed.append(question_id)
        outcomes.update(m['outcome'] for m in mappings)
        paper_roots[record['context']['paper_id']] += 1
        partition_roots[partitions[question_id]] += 1
        seconds.append(saved['execution']['seconds'])
        for item in saved['execution']['usage']:
            if item:
                usage.update(item)
        records[question_id]['validated_mappings'] = mappings
    for result in independent['results']:
        record = records[result['question_id']]
        if 'validated_mappings' not in record:
            continue
        human = validated_mappings(record, result)
        version = manifest['taxonomy_version_id']
        pairs.append((FrozenReview(record['input_hash'], record['context'], human, version),
            FrozenSuggestion(record['input_hash'], record['context'], record['validated_mappings'],
                version, record['candidates'])))
    comparison = comparison_metrics(pairs)
    result = dict(batch_key=manifest['batch_key'], requested_roots=len(records),
        completed_roots=len(completed), pending_roots=len(records)-len(completed),
        roots_by_paper=dict(paper_roots), outcomes_by_part=dict(outcomes),
        roots_by_partition=dict(partition_roots),
        comparison_roots=len(pairs), independent_method=independent['method'],
        independent_model_id=independent['model_id'], student_adjudicated=False,
        provisional=True, comparison=comparison, successful_call_usage=dict(usage),
        comparison_by_paper={paper: comparison_metrics([pair for pair in pairs if pair[0].context['paper_id'] == paper])
            for paper in sorted(paper_roots)},
        comparison_by_partition={partition: comparison_metrics([pair for pair in pairs
            if partitions[pair[0].context['question_id']] == partition]) for partition in ('development','holdout')},
        successful_root_seconds_total=sum(seconds),
        successful_root_seconds_median=statistics.median(seconds) if seconds else None,
        notes=['Agent agreement is diagnostic evidence, not ground truth.',
               'Usage and latency include reused pilot completions once; failed calls are retained separately.'])
    (ROOT/'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    typer.echo(json.dumps({k: result[k] for k in ('completed_roots','pending_roots','comparison_roots')}))


@app.command()
def audit_import():
    """Verify real imported context, answers, mappings and nonpublication status."""
    manifest = json.loads((ROOT/'sample120.json').read_text())
    records = {record['question_id']: record for record in manifest['records']}
    with get_session_factory('operations')() as session:
        rows = list(session.scalars(sa.select(SuggestionRevision).where(SuggestionRevision.batch_key == manifest['batch_key'])))
        if {row.question_id for row in rows} != set(records):
            raise ValueError('Imported root coverage differs from the frozen batch')
        answers = Counter()
        for row in rows:
            record = records[row.question_id]
            output = json.loads((ROOT/'luna-sample120'/(row.question_id + '.json')).read_text())
            if (row.context != record['context'] or row.candidates != record['candidates']
                    or row.mappings != validated_mappings(record, output['result'])
                    or row.provenance['model_id'] != output['execution']['model_id'] or not row.experimental):
                raise ValueError('Imported immutable evidence differs from the validated execution')
            ExtractedQuestion.model_validate({key: value for key, value in row.context.items() if key != 'classification_part_ids'})
            answers[row.context['answer_status']] += 1
        publications = session.scalar(sa.select(sa.func.count()).select_from(QuestionPublication).where(QuestionPublication.question_id.in_(records)))
        verifications = session.scalar(sa.select(sa.func.count()).select_from(ClassificationVerification).join(
            ClassificationRevision).where(ClassificationRevision.question_id.in_(records)))
        if publications or verifications:
            raise ValueError('Experimental suggestions unexpectedly contributed publication or verification')
    result = dict(batch_key=manifest['batch_key'], roots_checked=len(rows),
        complete_context_candidates_mappings_preserved=True, answer_states=dict(answers),
        published_roots=publications, student_verifications=verifications, experimental=True)
    (ROOT/'import-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    typer.echo(f'Verified complete imported evidence for {len(rows)} experimental roots')


@app.command()
def coverage():
    """Record available and omitted strata without changing the frozen sample."""
    sample = json.loads((ROOT/'sample.json').read_text())
    selected_by_paper = Counter((root['paper_id'], *root['stratum']) for root in sample['roots'])
    available, families, seen = Counter(), {}, set()
    with get_session_factory('operations')() as session:
        latest = sa.select(sa.func.max(ExtractionRevision.id)).group_by(ExtractionRevision.document_id)
        revisions = session.scalars(sa.select(ExtractionRevision).join(Document,
            ExtractionRevision.document_id == Document.id).join(DocType, DocType.id == Document.doc_type_id)
            .where(ExtractionRevision.id.in_(latest), ExtractionRevision.status != 'failed',
                Document.superseded.is_(False), Document.course_level == 'final', DocType.has_questions.is_(True))
            .order_by(ExtractionRevision.document_id, ExtractionRevision.id))
        for revision in revisions:
            snapshots = {r['stable_question_id']: r for r in revision.parsed_units}
            for context in revision.questions:
                count = sum(n['is_gradable'] for n in flatten_snapshots([snapshots[context['question_id']]]))
                if not count:
                    continue
                key = duplicate_key(context)
                if key in seen:
                    continue
                seen.add(key)
                paper = context['paper_id']
                difficulty = 'case' if count > 2 else context['answer_status']
                available[(paper, context['source_family'], context.get('source_attempt_id'), difficulty)] += 1
                families.setdefault(paper, set()).add(context['source_family'])
    rows = [dict(paper_id=key[0], source_family=key[1], attempt=key[2], difficulty=key[3],
        available_unique_roots=count, sampled_roots=selected_by_paper[key])
        for key, count in sorted(available.items(), key=lambda item: str(item[0]))]
    report = dict(frozen_seed=sample['seed'], available_unique_roots=len(seen),
        available_strata=rows, available_but_unsampled=[r for r in rows if not r['sampled_roots']],
        unavailable_expected_sources=[dict(paper_id=f's2023.P{i}', source_family=family)
            for i in range(1, 7) for family in ('examination','rtp','mock','model')
            if family not in families.get(f's2023.P{i}', set())],
        sample_unchanged=True, note='Unavailable means absent from these latest extracted draft snapshots; no coverage is fabricated.')
    (ROOT/'coverage.json').write_text(json.dumps(report, indent=2) + '\n')
    typer.echo(f'Coverage recorded for {len(rows)} available strata')


if __name__ == '__main__':
    app()
