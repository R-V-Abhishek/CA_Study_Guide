"""Full-paper taxonomy expansion remains pinned and source-scoped."""

from copy import deepcopy

import pytest

from caf_l3.batches import validated_mappings
from caf_l3.paper_workers import prepare_record
from test_phase5_batches import record, output


def test_full_catalog_allows_retrieval_miss_with_distinct_input_identity():
    original = record()
    catalog = [*original["candidates"], dict(node_id="correct-label", paper_id="s2023.P1")]
    prepared = prepare_record(original, catalog, {"1": {"sha256": "pdf"}})
    assert prepared["original_input_hash"] == original["input_hash"]
    assert prepared["input_hash"] != original["input_hash"]
    result = output()
    result["input_hash"] = prepared["input_hash"]
    result["mappings"][0]["primary_node_id"] = "correct-label"
    result["mappings"][0]["evidence"][0]["node_id"] = "correct-label"
    assert validated_mappings(prepared, result)[0]["primary_node_id"] == "correct-label"
    with pytest.raises(ValueError, match="hash mismatch"):
        validated_mappings(original, result)
    assert original["candidates"] == [dict(node_id="label", paper_id="s2023.P1")]


def test_full_scope_hash_changes_when_pdf_or_taxonomy_evidence_changes():
    original = record()
    catalog = deepcopy(original["candidates"])
    initial = prepare_record(original, catalog, {"1": {"sha256": "pdf"}})
    changed_source = prepare_record(original, catalog, {"1": {"sha256": "other"}})
    catalog[0]["descriptor_revision_id"] = 2
    changed_catalog = prepare_record(original, catalog, {"1": {"sha256": "pdf"}})
    assert len({initial["input_hash"], changed_source["input_hash"], changed_catalog["input_hash"]}) == 3
