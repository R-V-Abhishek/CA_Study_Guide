"""Pinned full-paper inputs and validated files for direct Luna paper workers."""

import json
import hashlib
from pathlib import Path

import pymupdf

from caf_l2.revisions import digest
from caf_l3.batches import validated_mappings, validate_manifest, write_json
from caf_l3.review_markdown import render_review_markdown


def prepare_record(record: dict, catalog: list[dict], sources: dict) -> dict:
    """Expand lexical retrieval explicitly and give the changed evidence a new hash."""
    expanded = {**record, "original_input_hash": record["input_hash"],
        "candidates": catalog, "candidate_scope": "full_paper_taxonomy",
        "source_catalog_hash": digest(sources)}
    expanded["input_hash"] = digest({k: v for k, v in expanded.items() if k != "input_hash"})
    return expanded


def load_record(directory: Path, question_id: str) -> dict:
    index = json.loads((directory / "index.json").read_text())
    if question_id not in {item["question_id"] for item in index}:
        raise ValueError("Question does not belong to this paper")
    record = json.loads((directory / "records" / (question_id + ".json")).read_text())
    catalog = json.loads((directory / "full-taxonomy.json").read_text())
    sources = json.loads((directory / "sources.json").read_text())
    return prepare_record(record, catalog, sources)


def save_result(directory: Path, question_id: str, result: dict, *,
                source_evidence: list[dict] | None = None) -> None:
    record = load_record(directory, question_id)
    validated_mappings(record, result)
    destination = directory / "results-direct"
    destination.mkdir(exist_ok=True)
    path = destination / (question_id + ".json")
    saved = dict(result=result, execution=dict(model_id="gpt-6-luna", method="luna_worker_direct",
        candidate_scope="full_paper_taxonomy", candidate_catalog_hash=digest(record["candidates"]),
        original_input_hash=record["original_input_hash"], source_catalog_hash=record["source_catalog_hash"],
        source_evidence=source_evidence or []))
    if path.exists():
        raise ValueError("Result already exists; preserve it and write a separately named correction")
    write_json(path, saved)


def load_review(directory: Path, *, result_ids: set[str] | None = None) -> tuple[dict, dict]:
    """Return (manifest, results_by_question_id), raising on invalid saved output.

    Cited original PDF text is recovered into each result's source evidence.
    """
    original = json.loads((directory / "batch.json").read_text())
    validate_manifest(original)
    catalog = json.loads((directory / "full-taxonomy.json").read_text())
    sources = json.loads((directory / "sources.json").read_text())
    records = [prepare_record(record, catalog, sources) for record in original["records"]]
    manifest = {**original, "records": records,
        "classifier": {**original["classifier"], "method": "luna_worker_direct", "retrieval": "full-paper-taxonomy"}}
    catalog_hash = digest(catalog)
    # Hash the shared catalog once instead of serializing it for every root.
    manifest["batch_key"] = digest(dict(original_batch_key=original["batch_key"],
        candidate_catalog_hash=catalog_hash, source_catalog_hash=digest(sources),
        classifier=manifest["classifier"]))
    results = {}
    source_cache = {}
    for record in records:
        path = directory / "results-direct" / (record["question_id"] + ".json")
        if path.exists() and (result_ids is None or record["question_id"] in result_ids):
            saved = json.loads(path.read_text())
            if saved["execution"]["candidate_catalog_hash"] != catalog_hash:
                raise ValueError("Taxonomy catalog changed since classification")
            validated_mappings(record, saved["result"])
            recovered = []
            for evidence in saved["execution"].get("source_evidence", []):
                document_id = str(evidence["document_id"])
                if document_id not in sources:
                    raise ValueError("Worker cited a document outside the paper source inventory")
                if document_id not in source_cache:
                    source = sources[document_id]
                    path = Path(source["blob_path"])
                    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                        raise ValueError("Original source PDF hash changed")
                    with pymupdf.open(path) as pdf:
                        source_cache[document_id] = [page.get_text(sort=True) for page in pdf]
                texts = source_cache[document_id]
                pages = evidence["pdf_pages"]
                if any(page < 1 or page > len(texts) for page in pages):
                    raise ValueError("Worker cited a source page outside the PDF")
                recovered.append({**evidence, "source_sha256": sources[document_id]["sha256"],
                    "original_pdf_pages": [{"pdf_page": page, "text": texts[page - 1]} for page in pages]})
            saved["execution"]["source_evidence"] = recovered
            results[record["question_id"]] = saved
    return manifest, results


def render_paper(directory: Path, output: Path) -> dict:
    manifest, results = load_review(directory)
    if output.exists():
        raise ValueError("Markdown already exists; preserve student edits and choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        handle.write(render_review_markdown(manifest, results))
    return dict(total=len(manifest["records"]), completed=len(results), pending=len(manifest["records"]) - len(results))
