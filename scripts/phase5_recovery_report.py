"""Summarize a verified Phase 5 checkpoint and original-data preservation."""

import json
from pathlib import Path
import typer
from caf_common.backup import file_checksum


def main(checkpoint: Path, verification: Path):
    manifest = json.loads(checkpoint.read_text())
    restored = json.loads(verification.read_text())
    original = json.loads(Path('docs/Phase5_Normal_Migration.json').read_text())['preserved']
    expected = {table: values for table, values in original.items() if table not in {'ops.run','ops.event'}}
    mismatches = [table for table, values in expected.items() if manifest['tables'].get(table) != values]
    dump = checkpoint.parent/manifest['dump_file']
    if (not restored['verified'] or restored['mismatches'] or restored['baseline_schema_drift']
            or file_checksum(dump) != manifest['dump_sha256'] or mismatches):
        raise ValueError('Verified dump, unchanged schema and preserved original data are required')
    histories = {table: values['count'] for table, values in manifest['tables'].items()
        if table in {'ingest.suggestion_revision','core.classification_revision','core.classification_event',
                     'core.classification_verification','core.classification_dispute','core.question_publication'}}
    result = dict(verified=True, verified_at=restored['verified_at'],
        database_revision=manifest['database_revision'], checkpoint=str(checkpoint),
        dump_file=str(dump), dump_sha256=manifest['dump_sha256'], detailed_report=str(verification),
        table_digests_checked=len(restored['restored_counts']), archived_files_checked=len(manifest['files']),
        mismatches=[], baseline_schema_drift={}, classification_history_counts=histories,
        original_data_preservation=dict(report='docs/Phase5_Normal_Migration.json',
            tables_checked=len(expected), all_original_values_preserved=True,
            operational_append_only_tables=['ops.run','ops.event']),
        authenticated_review_history='Covered by disposable-database publication/API/recovery tests; live student reviews are not fabricated',
        recovery_storage='Owned disposable PostgreSQL disk volume; persistent Compose data was not modified')
    Path('docs/Phase5_Recovery_Verification.json').write_text(json.dumps(result, indent=2) + '\n')
    typer.echo(f'Verified {len(expected)} unchanged original tables and {len(histories)} classification history tables')


if __name__ == '__main__':
    typer.run(main)
