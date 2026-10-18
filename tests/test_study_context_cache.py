"""Read request caching preserves account and transaction boundaries."""
import sqlalchemy as sa

from caf_db.models.app import Settings
from caf_l5.context import resolve_context, _unresolved_applicability
from caf_l0.releases import source_contexts
from test_phase6_intelligence import manifest, reviewed_context
from test_phase5_publication import suggestion


def test_read_context_reuses_queries_and_keeps_accounts_separate(session):
    session.info["cache_study_context"] = True
    first = resolve_context(session, 1)
    statements = []
    def track(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    sa.event.listen(session.bind, "before_cursor_execute", track)
    try:
        assert resolve_context(session, 1) is first
        assert statements == []
        missing = resolve_context(session, 999999)
        assert missing.readiness == "profile_settings_unavailable"
        assert missing is not first
    finally:
        sa.event.remove(session.bind, "before_cursor_execute", track)


def test_read_context_does_not_survive_transaction_or_session(session):
    session.info["cache_study_context"] = True
    first = resolve_context(session, 1)
    session.commit()
    assert resolve_context(session, 1) is not first
    second = resolve_context(session, 1)
    session.rollback()
    assert resolve_context(session, 1) is not second


def test_mutation_context_is_not_cached(session):
    first = resolve_context(session, 1)
    settings = session.get(Settings, 1)
    settings.target_attempt_id = None
    assert resolve_context(session, 1).target_attempt_id is None
    assert first.target_attempt_id is not None


def test_lightweight_applicability_matches_source_contexts(session, reviewed_context):
    suggestion, _ = reviewed_context
    version = suggestion.taxonomy_version_id
    sources = source_contexts(session, version)
    expected = {node_id for node_id, spans in sources.items()
                if any(span.get("fallback") and span.get("target_applicability") not in
                       {"verified", "applicable"} for span in spans)}
    assert set(_unresolved_applicability(session, version)) == expected
