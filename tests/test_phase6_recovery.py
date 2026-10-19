"""Phase 6 reader, personal data and jobs survive a real isolated restore."""

import json

from caf_common.backup import create_backup, verify_backup
from caf_db.models.app import Note
from caf_l5.jobs import enqueue_recompute
from caf_l5.scoring import recompute_scores
from test_phase5_publication import suggestion
from test_phase6_intelligence import manifest, reviewed_context


def test_reader_context_jobs_and_personal_data_survive_restore(session, reviewed_context, tmp_path):
    suggestion, target = reviewed_context
    node_id = suggestion.mappings[0]['primary_node_id']
    session.add(Note(user_id=1, node_id=node_id, body='Private recovery fixture'))
    session.commit()
    recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    enqueue_recompute(session, target, suggestion.taxonomy_version_id)
    checkpoint = create_backup(backup_dir=tmp_path)
    manifest_data = json.loads(checkpoint.manifest_file.read_text())
    for table in ('core.published_question', 'core.published_source', 'core.question_occurrence',
                  'core.question_publication', 'core.classification_revision',
                  'intel.attempt_taxonomy_binding', 'intel.score_run', 'intel.subtopic_score',
                  'intel.recompute_job', 'app.note', 'app.settings'):
        assert manifest_data['tables'][table]['count'] > 0, table
    restored = verify_backup(dump_file=checkpoint.dump_file)
    assert restored.verified, restored.message
    assert restored.restored_counts == restored.live_counts
    report = json.loads(restored.report_file.read_text())
    assert report['baseline_schema_drift'] == {}
