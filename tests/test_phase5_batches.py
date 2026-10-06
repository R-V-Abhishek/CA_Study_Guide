"""Whole root batch integrity, honest unresolved outcomes and frozen evaluation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from caf_l2.revisions import digest
from caf_l3.batches import validated_mappings, validate_manifest, run_operator_batch
from caf_l3.evaluate import evaluate_revision_pairs
from caf_l3.sampling import stratified_sample


def record(paper='s2023.P1'):
    context = dict(question_id='root', paper_id=paper, common_stem='Discount cash flows',
        question_text='', parts=[dict(id='root:Q1.a', question_text='Calculate NPV', parts=[])],
        answers=[], mcq=[], answer_status='missing', source_family='rtp', source_attempt_id='2026-01',
        classification_part_ids=['root:Q1.a'])
    return dict(question_id='root', input_hash='hash', document_id=1,
        extraction_revision_id=1, context=context,
        candidates=[dict(node_id='label', paper_id='s2023.P1')])


def output():
    return dict(question_id='root', input_hash='hash', mappings=[dict(part_id='root:Q1.a',
        outcome='matched', primary_node_id='label', secondary_node_ids=[],
        evidence=[dict(node_id='label', support='Cash flows are explicitly discounted')],
        note='NPV task', confidence=.9, bucket='A')])


@pytest.mark.parametrize('mutation', ['unknown_label', 'missing_part', 'wrong_hash', 'unsupported_outcome', 'missing_evidence'])
def test_import_rejects_incoherent_output(mutation):
    result = output()
    if mutation == 'unknown_label':
        result['mappings'][0]['primary_node_id'] = 'unknown'
    if mutation == 'missing_part':
        result['mappings'] = []
    if mutation == 'wrong_hash':
        result['input_hash'] = 'stale'
    if mutation == 'unsupported_outcome':
        result['mappings'][0]['outcome'] = 'technical_failure'
    if mutation == 'missing_evidence':
        result['mappings'][0]['evidence'] = []
    with pytest.raises(ValueError):
        validated_mappings(record(), result)


def test_paper_restrictions_and_ibs_cross_paper():
    wrong = record('s2023.P2')
    with pytest.raises(ValueError, match='paper'):
        validated_mappings(wrong, output())
    assert validated_mappings(record('s2023.P6'), output())[0]['primary_node_id'] == 'label'


@pytest.mark.parametrize('outcome', ['needs_review', 'none_fits'])
def test_unresolved_has_no_invented_primary(outcome):
    result = output()
    result['mappings'][0].update(outcome=outcome, primary_node_id=None,
        secondary_node_ids=[], evidence=[])
    assert validated_mappings(record(), result)[0]['primary_node_id'] is None


def test_sample_duplicate_groups_never_cross_holdout():
    roots = []
    for index in range(24):
        item = record()
        item['question_id'] = str(index)
        item['context']['parts'][0]['question_text'] = 'NPV ' + str(index // 2)
        roots.append(item)
    sample = stratified_sample(roots, per_paper=20)
    assert len(sample['roots']) == 12
    assert len({r['duplicate_group'] for r in sample['roots']}) == 12
    assert all(len(r['duplicate_occurrences']) == 2 for r in sample['roots'])
    assert stratified_sample(roots, per_paper=20) == sample


def test_revision_evaluation_ignores_stale_and_duplicate_adjudications():
    item = record()
    mappings = validated_mappings(item, output())
    suggestion = SimpleNamespace(input_hash='hash', context=item['context'], mappings=mappings,
        candidates=item['candidates'], taxonomy_version_id=1, experimental=False)
    reviewed = SimpleNamespace(input_hash='hash', context=item['context'], mappings=mappings, taxonomy_version_id=1, blind=True)
    stale = SimpleNamespace(input_hash='changed', context=item['context'], mappings=mappings, taxonomy_version_id=1, blind=True)
    report = evaluate_revision_pairs([(reviewed, suggestion), (reviewed, suggestion), (stale, suggestion)])
    assert report.total_reviewed == 1
    assert report.multilabel_precision == report.multilabel_recall == 1
    assert not report.passed


def test_calibration_requires_thirty_independent_adjudicated_roots():
    pairs = []
    for index in range(30):
        item = record()
        item['context']['parts'][0]['question_text'] = f'Independent NPV case {index}'
        model = validated_mappings(item, output())
        human = deepcopy(model)
        if index >= 24:
            human[0]['primary_node_id'] = 'other-label'
        suggestion = SimpleNamespace(input_hash='hash', context=item['context'], mappings=model,
            candidates=item['candidates'], taxonomy_version_id=1, experimental=False)
        review = SimpleNamespace(input_hash='hash', context=item['context'], mappings=human,
            taxonomy_version_id=1, blind=True)
        pairs.append((review, suggestion))
    assert not evaluate_revision_pairs(pairs[:29], min_samples=3).passed
    report = evaluate_revision_pairs(pairs)
    assert report.passed and report.bucket_a_root_samples == 30
    assert report.top1_agreement == report.bucket_metrics['A'].precision == .8
    assert report.candidate_retrieval_misses == 6
    assert not evaluate_revision_pairs(pairs, threshold=.81).passed
    assert not evaluate_revision_pairs(pairs, provisional=True).passed
    pairs[0][0].blind = False
    pairs[1][0].taxonomy_version_id = 2
    assert evaluate_revision_pairs(pairs).bucket_a_root_samples == 28


def test_unresolved_agreement_never_supplies_primary_accuracy_or_calibration():
    item = record()
    result = output()
    result['mappings'][0].update(outcome='needs_review', primary_node_id=None, evidence=[])
    mapping = validated_mappings(item, result)
    suggestion = SimpleNamespace(input_hash='hash', context=item['context'], mappings=mapping,
        candidates=item['candidates'], taxonomy_version_id=1, experimental=False)
    review = SimpleNamespace(input_hash='hash', context=item['context'], mappings=mapping,
        taxonomy_version_id=1, blind=True)
    report = evaluate_revision_pairs([(review, suggestion)])
    assert report.outcome_agreement == 1
    assert report.primary_labeled_samples == report.bucket_a_root_samples == 0
    assert report.bucket_metrics['A'].total == 0
    assert report.top1_agreement == 0 and not report.passed
    suggestion.mappings = validated_mappings(item, output())
    pending_truth = evaluate_revision_pairs([(review, suggestion)])
    assert pending_truth.bucket_a_root_samples == pending_truth.bucket_metrics['A'].total == 0


def test_corrupt_manifest_refuses_operator_execution(tmp_path):
    manifest = dict(schema_version=1, records=[], batch_key='bad')
    with pytest.raises(ValueError, match='hash'):
        run_operator_batch(manifest, tmp_path)


def test_overlapping_operator_coordinator_is_rejected(tmp_path):
    import fcntl
    with (tmp_path/'.operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='still running'):
            run_operator_batch(operator_manifest(), tmp_path)


def test_failed_operator_attempt_retains_response_usage_and_retry_history(tmp_path, monkeypatch):
    import json
    import subprocess
    from pathlib import Path
    attempts = []
    def execute(command, *, input, **kwargs):
        item = json.loads(input.split('\n', 1)[1])
        result = output()
        result.update(question_id=item['question_id'], input_hash=item['input_hash'])
        if not attempts:
            result['mappings'][0]['primary_node_id'] = 'unsupported'
        attempts.append(result)
        Path(command[command.index('--output-last-message')+1]).write_text(json.dumps(result))
        return subprocess.CompletedProcess(command, 0, json.dumps(dict(type='turn.completed',
            usage=dict(input_tokens=10, output_tokens=5))) + '\n', '')
    monkeypatch.setattr(subprocess, 'run', execute)
    manifest = operator_manifest()
    failed = run_operator_batch(manifest, tmp_path, limit=1)
    assert failed['execution_failed'] and not failed['completed']
    failure = failed['failures'][0]
    assert failure['usage'] == [dict(input_tokens=10, output_tokens=5)]
    evidence = Path(failure['evidence_prefix'] + '.response.json')
    assert json.loads(evidence.read_text())['mappings'][0]['primary_node_id'] == 'unsupported'
    resumed = run_operator_batch(manifest, tmp_path, limit=1)
    assert not resumed['execution_failed'] and len(resumed['completed']) == 1
    assert len(resumed['failures']) == 1 and evidence.exists()
    assert len(list(tmp_path.glob('*.attempt-*.response.json'))) == 2


def operator_manifest():
    records = []
    for index in range(2):
        item = record()
        item.pop('input_hash')
        item['question_id'] = 'root' + str(index)
        item['input_hash'] = digest(item)
        records.append(item)
    value = dict(schema_version=1, records=records, classifier={'model_id': 'gpt-6-luna'})
    value['batch_key'] = digest(value)
    return value


def test_operator_bounded_jobs_no_db_credentials_and_crash_resume(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    import subprocess
    calls = []
    monkeypatch.setenv('DATABASE_URL', 'never-enter-model-process')
    def execute(command, *, input, env, **kwargs):
        assert 'DATABASE_URL' not in env
        assert command[command.index('--sandbox')+1] == 'read-only'
        assert 'shell_tool' in command and 'apps' in command
        item = json.loads(input.split('\n', 1)[1])
        result = output()
        result.update(question_id=item['question_id'], input_hash=item['input_hash'])
        Path(command[command.index('--output-last-message')+1]).write_text(json.dumps(result))
        calls.append(item['question_id'])
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed","usage":{"input_tokens":10}}', stderr='')
    monkeypatch.setattr(subprocess, 'run', execute)
    manifest = operator_manifest()
    first = run_operator_batch(manifest, tmp_path, workers=2)
    assert len(first['completed']) == 2 and not first['pending']
    # A crash after durable root outputs but before aggregate state is recoverable.
    state = json.loads((tmp_path/'state.json').read_text())
    state['completed'] = []
    (tmp_path/'state.json').write_text(json.dumps(state))
    resumed = run_operator_batch(manifest, tmp_path, workers=2)
    assert len(resumed['completed']) == 2 and len(calls) == 2


def test_operator_failure_preserves_completed_jobs(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    import subprocess
    def execute(command, *, input, **kwargs):
        item = json.loads(input.split('\n', 1)[1])
        if item['question_id'] == 'root1':
            return SimpleNamespace(returncode=1, stdout='', stderr='quota interruption')
        result = output()
        result.update(question_id=item['question_id'], input_hash=item['input_hash'])
        Path(command[command.index('--output-last-message')+1]).write_text(json.dumps(result))
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(subprocess, 'run', execute)
    state = run_operator_batch(operator_manifest(), tmp_path)
    assert state['completed'] == ['root0'] and state['pending'] == ['root1']
    assert state['execution_failed'] and 'quota interruption' in state['failures'][0]['error']
