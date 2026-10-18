"""Prepare, activate or roll back the pinned study corpus."""
import json
from pathlib import Path
import typer
from caf_db.engine import get_session_factory

app = typer.Typer(help='Frozen baseline adoption; never reruns classification')


@app.command('prepare')
def prepare(root: Path = Path('data/student_review/luna-papers'), actor_id: int = 1):
    from caf_l3.baseline_pack import freeze_pack
    from caf_l4.baseline import prepare_baseline
    frozen = freeze_pack(root)
    with get_session_factory()() as session:
        adoption = prepare_baseline(session,frozen,actor_id)
        session.commit()
        print(json.dumps(dict(release_id=adoption.release_id, manifest_hash=adoption.manifest_hash,
            status=adoption.status, manifest=adoption.manifest),indent=2))


@app.command('activate')
def activate(manifest_hash: str, release_id: str = 'baseline-2026-10-16', actor_id: int = 1):
    from caf_l4.baseline import activate_baseline
    with get_session_factory()() as session:
        result=activate_baseline(session,release_id,manifest_hash,actor_id)
        session.commit()
        print(json.dumps(result))


@app.command('rollback')
def rollback(manifest_hash: str, release_id: str = 'baseline-2026-10-16', actor_id: int = 1):
    from caf_l4.baseline import rollback_baseline
    with get_session_factory()() as session:
        result=rollback_baseline(session,release_id,manifest_hash,actor_id)
        session.commit()
        print(json.dumps(result))
