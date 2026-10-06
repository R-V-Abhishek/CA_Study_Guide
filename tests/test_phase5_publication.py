"""Root publication, account verification, revision conflicts and recovery history."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from caf_db.engine import get_engine
from caf_db.models.app import UserAccount
from caf_db.models.classification import (SuggestionRevision, ClassificationRevision,
    ClassificationEvent, ClassificationVerification, QuestionPublication)
from caf_db.models.core import Appearance, AppearanceTag, Decision
from caf_db.models.extraction import ExtractionRevision, ExtractionReview
from caf_db.models.taxonomy import NodeSourceSpan, TaxonomyRelease, TextbookArtifact
from caf_l0.releases import eligible_candidates, import_release
from caf_l2.revisions import promote_revision
from caf_l3.batches import export_batch, import_batch
from caf_l4.revisions import (review_classification, verify_classification, submit_dispute,
    resolve_dispute, readiness, history, RevisionConflict, ReadinessError, validate_mappings, verification_count)
from test_phase3_release import manifest, authenticated_actors, review_all
from test_phase4_revisions import source, extract


@pytest.fixture
def suggestion(session, manifest, tmp_path):
    authenticated_actors(session)
    session.add(UserAccount(id=2, name='Second authenticated student', role='student', status='active'))
    import_release(session, manifest, dry_run=False)
    review_all(session, manifest['version_id'])
    release = session.get(TaxonomyRelease, manifest['version_id'])
    release.status, release.approved_by = 'active', 9
    session.commit()
    document, pipeline = source(session, tmp_path)
    document.attempt_id = '2026-05'
    session.commit()
    extracted = extract(session, pipeline, document)
    promote_revision(session, extracted.revision_id, None)
    revision = session.get(ExtractionRevision, extracted.revision_id)
    for dimension in ('questions','answers','pairing','ordering','marks_choices','readability','human_review'):
        session.add(ExtractionReview(revision_id=revision.id, actor_id=1, content_digest=revision.content_digest,
            dimension=dimension, status='not_applicable' if dimension in {'answers','pairing'} else 'passed', note='Independently compared source fixture'))
    session.commit()
    batch = export_batch(session, manifest['version_id'], [revision.id])
    record = batch['records'][0]
    node_id = record['candidates'][0]['node_id']
    mappings = [dict(part_id=part_id, outcome='matched', primary_node_id=node_id, secondary_node_ids=[],
        evidence={'labels': {node_id: 'Recognition criteria in complete case context'}}, confidence=.8, bucket='B', excluded=False)
        for part_id in record['context']['classification_part_ids']]
    suggestion = SuggestionRevision(batch_key=batch['batch_key'], input_hash=record['input_hash'], document_id=document.id,
        extraction_revision_id=revision.id, question_id=record['question_id'], taxonomy_version_id=release.taxonomy_version_id,
        run_id=1, experimental=False, context=record['context'], candidates=record['candidates'], mappings=mappings,
        provenance={**batch['classifier'], 'taxonomy_manifest_hash': release.manifest_hash, 'extraction_digest': revision.content_digest})
    session.add(suggestion)
    session.commit()
    assert readiness(session, suggestion)['eligible'], readiness(session, suggestion)
    return suggestion


def review(session, suggestion, actor=1, previous=None, key='initial', mappings=None):
    return review_classification(session, suggestion.id, actor, mappings or suggestion.mappings,
        suggestion.id, previous, key, note='Reviewed full question and available answer')


def test_publication_projection_distinct_verification_and_withdrawal(session, suggestion):
    result = review(session, suggestion)
    session.commit()
    assert result['verification_count'] == 1
    assert review(session, suggestion) == result
    session.commit()
    published_id = result['revision_id']
    assert session.scalar(sa.select(sa.func.count(Appearance.id)).where(Appearance.status == 'published')) == len(suggestion.mappings)
    assert session.scalar(sa.select(sa.func.count(AppearanceTag.appearance_id))) == len(suggestion.mappings)
    for key in ('verify-click', 'verify-double-click'):
        response = verify_classification(session, suggestion.question_id, 2, published_id, key,
            expected_suggestion_revision_id=suggestion.id)
        session.commit()
        assert response['verification_count'] == 2
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 2
    response = verify_classification(session, suggestion.question_id, 2, published_id, 'withdraw', withdraw=True)
    session.commit()
    assert response['verification_count'] == 1
    assert session.scalar(sa.select(sa.func.count(ClassificationEvent.id))) == 4
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 2


def test_material_label_revision_resets_verification_and_retains_history(session, suggestion):
    first = review(session, suggestion)
    session.commit()
    verify_classification(session, suggestion.question_id, 2, first['revision_id'], 'verify-original')
    session.commit()
    mappings = [{**mapping, 'outcome': 'none_fits', 'primary_node_id': None} for mapping in suggestion.mappings]
    second = review(session, suggestion, previous=first['revision_id'], key='replacement', mappings=mappings)
    session.commit()
    assert second['verification_count'] == 1
    assert second['revision_id'] != first['revision_id']
    assert [row['verification_count'] for row in history(session, suggestion.question_id)] == [1, 2]
    assert session.scalar(sa.select(sa.func.count(Appearance.id)).where(Appearance.status == 'published')) == 0
    with pytest.raises(RevisionConflict):
        verify_classification(session, suggestion.question_id, 2, first['revision_id'], 'stale-verify')
    session.rollback()


def test_correction_preserves_publication_until_explicit_admin_resolution(session, suggestion):
    first = review(session, suggestion)
    session.commit()
    mappings = [{**mapping, 'outcome': 'none_fits', 'primary_node_id': None} for mapping in suggestion.mappings]
    disputed = submit_dispute(session, suggestion.question_id, 2, first['revision_id'], 'dispute', 'Complete case does not support recognition topic', mappings, suggestion.id)
    session.commit()
    assert disputed['pending'] and disputed['current_revision_id'] == first['revision_id']
    with pytest.raises(ReadinessError, match='administrator'):
        review(session, suggestion, previous=first['revision_id'], key='blocked-review')
    session.rollback()
    with pytest.raises(ValueError, match='administrator'):
        resolve_dispute(session, disputed['dispute_id'], 2, first['revision_id'], 'unauthorized', 'replace', 'Checked evidence', mappings, suggestion.id)
    session.rollback()
    resolved = resolve_dispute(session, disputed['dispute_id'], 9, first['revision_id'], 'resolve', 'replace', 'Compared original textbook and whole question', mappings, suggestion.id)
    session.commit()
    assert resolved['status'] == 'replaced' and resolved['verification_count'] == 1
    assert resolved['current_revision_id'] != first['revision_id']
    assert len(history(session, suggestion.question_id)) == 3


def test_draft_never_publishes_immutable_evidence_and_partial_mapping_rejected(session, suggestion):
    with pytest.raises(ValueError, match='each gradable part'):
        validate_mappings(session, suggestion, suggestion.mappings[:1])
    with pytest.raises(DBAPIError, match='immutable'):
        session.execute(sa.update(SuggestionRevision).where(SuggestionRevision.id == suggestion.id).values(experimental=True))
    session.rollback()
    draft = SuggestionRevision(batch_key=str(uuid4()), input_hash=suggestion.input_hash, document_id=suggestion.document_id,
        extraction_revision_id=suggestion.extraction_revision_id, question_id=suggestion.question_id,
        taxonomy_version_id=suggestion.taxonomy_version_id, run_id=1, experimental=True, context=suggestion.context,
        candidates=suggestion.candidates, mappings=suggestion.mappings, provenance=suggestion.provenance)
    session.add(draft)
    session.commit()
    with pytest.raises(ReadinessError, match='experimental_suggestion'):
        review(session, draft)
    session.rollback()
    assert session.scalar(sa.select(sa.func.count(ClassificationRevision.id))) == 0
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 0


def test_simultaneous_reviews_publish_once_and_retries_do_not_duplicate(session, suggestion):
    session.commit()
    barrier = Barrier(2)
    suggestion_id, mappings = suggestion.id, suggestion.mappings
    def submit(actor_id):
        with Session(get_engine()) as other:
            barrier.wait(timeout=10)
            try:
                result = review_classification(other, suggestion_id, actor_id, mappings, suggestion_id, None,
                    'concurrent-' + str(actor_id), note='Independent source review')
                other.commit()
                return result
            except RevisionConflict:
                other.rollback()
                return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, [1, 2]))
    assert sum(response == 'conflict' for response in responses) == 1
    assert session.scalar(sa.select(sa.func.count(ClassificationRevision.id))) == 1
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 1
    assert session.scalar(sa.select(sa.func.count(Decision.id))) == len(mappings)


def test_model_rerun_preserves_published_revision_and_can_verify_old_evidence(session, suggestion):
    first = review(session, suggestion)
    session.commit()
    rerun = SuggestionRevision(batch_key=str(uuid4()), input_hash=suggestion.input_hash, document_id=suggestion.document_id,
        extraction_revision_id=suggestion.extraction_revision_id, question_id=suggestion.question_id,
        taxonomy_version_id=suggestion.taxonomy_version_id, run_id=1, experimental=False, context=suggestion.context,
        candidates=suggestion.candidates, mappings=suggestion.mappings, provenance=suggestion.provenance)
    session.add(rerun)
    session.commit()
    verified = verify_classification(session, suggestion.question_id, 2, first['revision_id'], 'verify-frozen', expected_suggestion_revision_id=suggestion.id)
    session.commit()
    assert verified['verification_count'] == 2
    assert session.get(QuestionPublication, suggestion.question_id).current_revision_id == first['revision_id']
    reviewed_again = review(session, rerun, actor=2, previous=first['revision_id'], key='accept-identical-rerun')
    session.commit()
    assert reviewed_again['revision_id'] == first['revision_id']
    assert reviewed_again['verification_count'] == 2
    assert session.scalar(sa.select(sa.func.count(ClassificationRevision.id))) == 1


def test_actual_curator_credentials_publish_without_profile_access(session, suggestion):
    session.commit()
    with Session(get_engine('curation')) as curator:
        selected = curator.get(SuggestionRevision, suggestion.id)
        first = review(curator, selected)
        curator.commit()
        assert first['verification_count'] == 1
        second = verify_classification(curator, selected.question_id, 2, first['revision_id'], 'credential-verify', expected_suggestion_revision_id=selected.id)
        curator.commit()
        assert second['verification_count'] == 2
        with pytest.raises(DBAPIError, match='permission denied'):
            curator.execute(sa.text('SELECT email FROM app.user_account'))
        curator.rollback()


def test_blind_draft_benchmark_is_annotation_without_publication_or_verification(session, suggestion):
    draft = SuggestionRevision(batch_key=str(uuid4()), input_hash=suggestion.input_hash, document_id=suggestion.document_id,
        extraction_revision_id=suggestion.extraction_revision_id, question_id=suggestion.question_id,
        taxonomy_version_id=suggestion.taxonomy_version_id, run_id=1, experimental=True, context=suggestion.context,
        candidates=suggestion.candidates, mappings=suggestion.mappings, provenance=suggestion.provenance)
    session.add(draft)
    session.commit()
    result = review_classification(session, draft.id, 2, draft.mappings, draft.id, None,
        'blind-draft', blind=True, note='Independent provisional benchmark annotation')
    session.commit()
    assert result['pending'] and result['status'] == 'benchmark'
    assert result['current_revision_id'] is None and result['verification_count'] == 0
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 0
    assert session.scalar(sa.select(sa.func.count(Appearance.id))) == 0
    assert history(session, draft.question_id)[0]['status'] == 'benchmark'


def test_new_extraction_with_reused_units_publishes_current_complete_mapping(session, suggestion):
    from copy import deepcopy
    from caf_l2.revisions import digest
    first = review(session, suggestion)
    session.commit()
    prior = session.get(ExtractionRevision, suggestion.extraction_revision_id)
    snapshots = deepcopy(prior.parsed_units)
    # Revision quality/evidence changes; exact part contents and units are reused.
    revision = ExtractionRevision(document_id=prior.document_id, run_id=1, base_revision_id=prior.id,
        status='candidate', content_digest=digest({'fixture': 'new immutable evidence'}), profile_id=prior.profile_id,
        configuration=prior.configuration, quality=prior.quality, questions=deepcopy(prior.questions), parsed_units=snapshots)
    for question in revision.questions:
        question['content_revision'] = revision.content_digest
    session.add(revision)
    session.commit()
    promote_revision(session, revision.id, prior.id)
    for dimension in ('questions','answers','pairing','ordering','marks_choices','readability','human_review'):
        session.add(ExtractionReview(revision_id=revision.id, actor_id=1, content_digest=revision.content_digest,
            dimension=dimension, status='not_applicable' if dimension in {'answers','pairing'} else 'passed', note='Reviewed new evidence revision'))
    session.commit()
    assert readiness(session, suggestion)['stale']
    with pytest.raises(ReadinessError):
        verify_classification(session, suggestion.question_id, 2, first['revision_id'], 'verify-old-content')
    session.rollback()
    release = session.scalar(sa.select(TaxonomyRelease).where(TaxonomyRelease.taxonomy_version_id == suggestion.taxonomy_version_id))
    batch = export_batch(session, release.version_id, [revision.id])
    record = batch['records'][0]
    newer = SuggestionRevision(batch_key=batch['batch_key'], input_hash=record['input_hash'], document_id=record['document_id'],
        extraction_revision_id=revision.id, question_id=record['question_id'], taxonomy_version_id=release.taxonomy_version_id,
        run_id=1, experimental=False, context=record['context'], candidates=record['candidates'], mappings=suggestion.mappings,
        provenance={**batch['classifier'], 'taxonomy_manifest_hash': release.manifest_hash, 'extraction_digest': revision.content_digest})
    session.add(newer)
    session.commit()
    second = review(session, newer, previous=first['revision_id'], key='review-new-content')
    session.commit()
    assert second['verification_count'] == 1
    assert session.scalar(sa.select(sa.func.count(Appearance.id)).where(Appearance.status == 'published')) == len(suggestion.mappings)


def test_reviewed_source_reference_change_invalidates_pinned_evidence(session, suggestion):
    first = review(session, suggestion)
    session.commit()
    node_id = suggestion.candidates[0]['node_id']
    span = session.scalar(sa.select(NodeSourceSpan).where(NodeSourceSpan.taxonomy_version_id == suggestion.taxonomy_version_id,
        NodeSourceSpan.node_id == node_id).limit(1))
    original = session.get(TextbookArtifact, (suggestion.taxonomy_version_id, span.artifact_id))
    replacement = TextbookArtifact(taxonomy_version_id=suggestion.taxonomy_version_id, id='reviewed-replacement-reference',
        paper_id=original.paper_id, course_level=original.course_level, edition='Reviewed replacement source edition',
        availability='verified', sha256=original.sha256, page_count=original.page_count,
        metadata_json={**original.metadata_json, 'edition_evidence': 'Verified replacement reference fixture'})
    session.add(replacement)
    session.flush()
    span.artifact_id = replacement.id
    session.flush()
    # Simulate completed independent review of the changed reference. The
    # current source and descriptors are eligible; the old pinned evidence is not.
    release = session.scalar(sa.select(TaxonomyRelease).where(TaxonomyRelease.taxonomy_version_id == suggestion.taxonomy_version_id).execution_options(populate_existing=True))
    release.status, release.approved_by = 'active', 9
    session.commit()
    assert node_id in {candidate.node_id for candidate in eligible_candidates(session, suggestion.taxonomy_version_id)}
    gates = readiness(session, suggestion)
    assert not gates['eligible'] and gates['stale']
    assert 'stale_source_evidence:' + node_id in gates['blockers']
    with pytest.raises(ReadinessError, match='stale_source_evidence'):
        verify_classification(session, suggestion.question_id, 2, first['revision_id'], 'verify-changed-source')
    session.rollback()
    with pytest.raises(ReadinessError, match='stale_source_evidence'):
        review(session, suggestion, previous=first['revision_id'], key='review-changed-source')
    session.rollback()
    assert session.get(QuestionPublication, suggestion.question_id).current_revision_id == first['revision_id']
    assert session.scalar(sa.select(sa.func.count(ClassificationVerification.id))) == 1


def test_rejected_source_cannot_receive_new_review_or_verification(session, suggestion):
    from caf_l1.catalog import reject_document
    first = review(session, suggestion)
    session.commit()
    reject_document(session, suggestion.document_id)
    gates = readiness(session, suggestion)
    assert not gates['eligible'] and 'source_identity_or_provenance' in gates['blockers']
    with pytest.raises(ReadinessError, match='source_identity_or_provenance'):
        verify_classification(session, suggestion.question_id, 2, first['revision_id'], 'verify-rejected')
    session.rollback()
    with pytest.raises(ReadinessError, match='source_identity_or_provenance'):
        review(session, suggestion, previous=first['revision_id'], key='review-rejected')
    session.rollback()
    assert session.get(QuestionPublication, suggestion.question_id).current_revision_id == first['revision_id']
    assert verification_count(session, first['revision_id']) == 1


def test_validated_import_preserves_complete_context_and_actual_model_idempotently(session, suggestion):
    release = session.scalar(sa.select(TaxonomyRelease).where(TaxonomyRelease.taxonomy_version_id == suggestion.taxonomy_version_id))
    batch = export_batch(session, release.version_id, [suggestion.extraction_revision_id],
        question_ids=[suggestion.question_id], run_label='import-recovery-regression')
    record = batch['records'][0]
    result = dict(question_id=record['question_id'], input_hash=record['input_hash'],
        execution=dict(model_id=batch['classifier']['model_id']), mappings=[dict(
            part_id=mapping['part_id'], outcome=mapping['outcome'], primary_node_id=mapping['primary_node_id'],
            secondary_node_ids=mapping['secondary_node_ids'], note='Tested complete root context',
            confidence=mapping['confidence'], bucket=mapping['bucket'], evidence=[dict(
                node_id=node_id, support=support) for node_id, support in mapping['evidence']['labels'].items()])
            for mapping in suggestion.mappings])
    with pytest.raises(ValueError, match='execution model'):
        import_batch(session, batch, [{**result, 'execution': {'model_id': 'different-provider'}}], 1)
    assert import_batch(session, batch, [result], 1) == 1
    session.commit()
    assert import_batch(session, batch, [result], 1) == 0
    imported = session.scalar(sa.select(SuggestionRevision).where(SuggestionRevision.batch_key == batch['batch_key']))
    assert imported.context == record['context'] and imported.candidates == record['candidates']
    assert {mapping['part_id'] for mapping in imported.mappings} == set(record['context']['classification_part_ids'])
    assert imported.provenance['model_id'] == result['execution']['model_id']
