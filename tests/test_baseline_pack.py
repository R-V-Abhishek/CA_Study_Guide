"""Baseline preparation fails closed and preserves uncertain saved outputs."""

from copy import deepcopy
import hashlib
import json

import pymupdf
import pytest

from caf_l2.revisions import digest
from caf_l3 import baseline_pack
from caf_l3.paper_workers import prepare_record


@pytest.fixture
def pack(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline_pack, "EXPECTED_ROOTS", 1)
    monkeypatch.setattr(baseline_pack, "EXPECTED_CANDIDATES", 1)
    monkeypatch.setattr(baseline_pack, "EXPECTED_SOURCES", 1)
    monkeypatch.setattr(baseline_pack, "EXPECTED_PAPERS", {"P1": (1, 1)})
    monkeypatch.setattr(baseline_pack, "PAPER_PACKS", {"P1": ["P1-corrected"]})
    monkeypatch.setattr(baseline_pack, "ORIGINAL_PACKS", ["P1"])
    monkeypatch.setattr(baseline_pack, "corpus_status", lambda root: dict(total=1, saved=1,
        pending=0, papers={"P1": dict(roots=1, parts=1, saved_parts=1)}))
    root = tmp_path / "data/student_review/luna-papers"
    directory = root / "P1-corrected"
    for child in ("records", "results-direct", "corrections-history"):
        (directory / child).mkdir(parents=True, exist_ok=True)

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    blob = tmp_path / "data/source.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.save(blob)
    sha = hashlib.sha256(blob.read_bytes()).hexdigest()
    write(tmp_path / "taxonomy/textbook_v1/manifest.json", dict(textbook_artifacts=[]))
    sources = {"1": dict(blob_path="data/source.pdf", sha256=sha)}
    catalog = [dict(node_id="label", paper_id="s2023.P1", textbook_references=[])]
    record = dict(question_id="q", document_id=1, document_sha256=sha,
        context=dict(paper_id="s2023.P1", classification_part_ids=["q"],
            source_spans=[dict(page_start=1, page_end=1, document_sha256=sha)],
            answers=[], answer_status="missing", review_status="pending"), candidates=[])
    record["input_hash"] = digest(record)
    original = dict(schema_version=1, records=[record])
    original["batch_key"] = digest(original)
    expanded = prepare_record(record, catalog, sources)
    saved = dict(result=dict(question_id="q", input_hash=expanded["input_hash"], mappings=[
        dict(part_id="q", outcome="none_fits", primary_node_id=None, secondary_node_ids=[],
            evidence=[], note="Unresolved source instruction", confidence=0.9, bucket=None)]),
        execution=dict(candidate_catalog_hash=digest(catalog), source_catalog_hash=digest(sources),
            original_input_hash=record["input_hash"], source_evidence=[dict(document_id=1, pdf_pages=[1])]))
    for name, value in (("batch.json", original), ("sources.json", sources),
                        ("full-taxonomy.json", catalog), ("records/q.json", record),
                        ("results-direct/q.json", saved),
                        ("index.json", [dict(question_id="q", gradable_parts=1)])):
        write(directory / name, value)
    write(root / "P1/index.json", [dict(question_id="q", gradable_parts=1)])
    write(directory / "corrections-history/q.before.json", dict(previous="preserved"))
    return root, directory, write


def test_compact_catalog_hash_matches_worker_input():
    record = dict(question_id="q", input_hash="original", candidates=[], context={"text": "₹ café"})
    catalog = [dict(node_id="é", descriptor={"definition": "₹"})]
    sources = {"1": {"sha256": "abc"}}
    canonical = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert baseline_pack._expanded_hash(record, canonical, digest(sources)) == prepare_record(record, catalog, sources)["input_hash"]


def test_freeze_is_repeatable_compact_and_preserves_unresolved_records(pack):
    root, directory, _ = pack
    before = {str(path): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    frozen = baseline_pack.freeze_pack(root)
    assert frozen == baseline_pack.freeze_pack(root)
    assert frozen["manifest_hash"] == digest(frozen["manifest"])
    record = frozen["records"][0]
    assert "candidates" not in record
    assert record["catalog_hash"] in frozen["catalogs"]
    assert record["context"]["answer_status"] == "missing"
    assert record["mappings"][0]["outcome"] == "none_fits"
    assert record["mappings"][0]["primary_node_id"] is None
    assert any("corrections-history" in name for name in frozen["manifest"]["files"])
    assert before == {str(path): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("field", ["candidate_catalog_hash", "source_catalog_hash", "original_input_hash"])
def test_conflicting_saved_inputs_stop_preparation(pack, field):
    root, directory, write = pack
    path = directory / "results-direct/q.json"
    saved = json.loads(path.read_text())
    saved["execution"][field] = "changed"
    write(path, saved)
    with pytest.raises(ValueError, match="input hashes changed"):
        baseline_pack.freeze_pack(root)


def test_duplicate_candidates_stop_preparation(pack):
    root, directory, write = pack
    path = directory / "full-taxonomy.json"
    catalog = json.loads(path.read_text())
    write(path, [*catalog, deepcopy(catalog[0])])
    with pytest.raises(ValueError, match="candidate node ID"):
        baseline_pack.freeze_pack(root)


def test_changed_pdf_and_invalid_pages_stop_preparation(pack):
    root, directory, write = pack
    path = directory / "results-direct/q.json"
    saved = json.loads(path.read_text())
    saved["execution"]["source_evidence"][0]["pdf_pages"] = [2]
    write(path, saved)
    with pytest.raises(ValueError, match="outside the PDF"):
        baseline_pack.freeze_pack(root)
    (root.parents[1] / "source.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash changed"):
        baseline_pack.freeze_pack(root)


def test_changed_record_stops_preparation(pack):
    root, directory, write = pack
    path = directory / "records/q.json"
    record = json.loads(path.read_text())
    record["context"]["answer_status"] = "complete"
    write(path, record)
    with pytest.raises(ValueError, match="Record differs"):
        baseline_pack.freeze_pack(root)


def test_interrupted_preparation_without_checkpoint_cannot_succeed(pack):
    root, directory, _ = pack
    (directory / "results-direct/q.json").unlink()
    with pytest.raises(FileNotFoundError):
        baseline_pack.freeze_pack(root)


@pytest.mark.parametrize("branch", ["parts", "answers"])
@pytest.mark.parametrize("invalid", ["page", "source"])
def test_nested_context_sources_are_validated(pack, branch, invalid):
    root, directory, write = pack
    record_path = directory / "records/q.json"
    record = json.loads(record_path.read_text())
    span = deepcopy(record["context"]["source_spans"][0])
    if invalid == "page":
        span["page_end"] = 2
        error = "outside the PDF"
    else:
        span["document_sha256"] = "unknown-source"
        error = "outside the paper source inventory"
    record["context"][branch] = [dict(source_spans=[], parts=[dict(source_spans=[span], parts=[])])]
    record["input_hash"] = digest({key: value for key, value in record.items() if key != "input_hash"})
    write(record_path, record)
    batch_path = directory / "batch.json"
    batch = json.loads(batch_path.read_text())
    batch["records"] = [record]
    batch["batch_key"] = digest({key: value for key, value in batch.items() if key != "batch_key"})
    write(batch_path, batch)
    with pytest.raises(ValueError, match=error):
        baseline_pack.freeze_pack(root)
