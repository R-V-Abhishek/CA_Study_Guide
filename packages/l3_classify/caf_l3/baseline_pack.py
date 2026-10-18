"""Read-only validation and content-addressed freezing of the accepted corpus.

The original worker inputs and correction files remain evidence. The returned
records reference shared catalogs and preserve unresolved classification outcomes.
"""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import pymupdf

from caf_l2.revisions import digest
from caf_l3.batches import validate_manifest, validated_mappings
from caf_l3.corpus_review import ORIGINAL_PACKS, PAPER_PACKS, corpus_status


EXPECTED_PAPERS = {
    "P1": (414, 1164), "P2": (193, 880), "P3": (505, 1030),
    "P4": (649, 1327), "P5": (428, 1158), "P6": (820, 2219),
}
EXPECTED_ROOTS = 3009
EXPECTED_CANDIDATES = 3300
EXPECTED_SOURCES = 94


def _json(path: Path):
    return json.loads(path.read_text())


def _file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _expanded_hash(record: dict, catalog_json: str, sources_hash: str) -> str:
    """Hash prepare_record's exact canonical JSON without serializing its catalog again."""
    expanded = {**record, "original_input_hash": record["input_hash"],
        "candidate_scope": "full_paper_taxonomy", "source_catalog_hash": sources_hash}
    expanded.pop("input_hash")
    expanded["candidates"] = None
    encoder = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    hashed = hashlib.sha256()
    hashed.update(b"{")
    for index, key in enumerate(sorted(expanded)):
        if index:
            hashed.update(b",")
        hashed.update((encoder(key) + ":").encode())
        hashed.update((catalog_json if key == "candidates" else encoder(expanded[key])).encode())
    hashed.update(b"}")
    return hashed.hexdigest()


def freeze_pack(root: Path) -> dict:
    """Validate every canonical input before returning an importable frozen snapshot.

    No database or filesystem writes occur. Any changed source, missing checkpoint,
    incompatible catalog, or incomplete coverage prevents preparation succeeding.
    """
    root = root.resolve()
    project = next((parent for parent in [root, *root.parents]
        if (parent / "taxonomy/textbook_v1/manifest.json").is_file()), Path.cwd())
    status = corpus_status(root)
    if status["total"] != EXPECTED_ROOTS or status["saved"] != EXPECTED_ROOTS or status["pending"]:
        raise ValueError("Baseline requires exactly 3009 completed roots")
    for paper, (roots, parts) in EXPECTED_PAPERS.items():
        counts = status["papers"][paper]
        if (counts["roots"], counts["parts"], counts["saved_parts"]) != (roots, parts, parts):
            raise ValueError(f"Baseline coverage differs for {paper}")

    files, source_files, catalogs, records, nodes, source_ids = {}, {}, {}, [], {}, {}
    pdf_cache = {}

    def pin(path: Path) -> None:
        # Relative identifiers keep the release portable between checkouts.
        try:
            name = str(path.relative_to(project))
        except ValueError:
            name = str(path.relative_to(root))
        files[name] = _file_hash(path)

    def pdf(path: Path, expected_hash: str) -> int:
        path = path if path.is_absolute() else project / path
        if expected_hash not in pdf_cache:
            if not path.is_file() or _file_hash(path) != expected_hash:
                raise ValueError(f"Source PDF missing or hash changed: {path}")
            with pymupdf.open(path) as document:
                pdf_cache[expected_hash] = len(document)
            source_files[expected_hash] = dict(path=str(path.relative_to(project)),
                sha256=expected_hash, pages=pdf_cache[expected_hash])
        return pdf_cache[expected_hash]

    def pages(start: int, end: int, total: int) -> None:
        if start < 1 or end < start or end > total:
            raise ValueError("Cited source page outside the PDF")

    def context_pages(context: dict, inventory_hashes: set[str]) -> None:
        def visit(part: dict) -> None:
            for span in part["source_spans"]:
                sha = span["document_sha256"]
                if sha not in inventory_hashes or sha not in pdf_cache:
                    raise ValueError("Context cites a source outside the paper source inventory")
                pages(span["page_start"], span["page_end"], pdf_cache[sha])
            for child in part.get("parts", []):
                visit(child)

        visit(context)
        for answer in context["answers"]:
            visit(answer)

    taxonomy_path = project / "taxonomy/textbook_v1/manifest.json"
    taxonomy = _json(taxonomy_path)
    pin(taxonomy_path)
    artifacts = {item["id"]: item for item in taxonomy["textbook_artifacts"]}
    for name in ORIGINAL_PACKS:
        pin(root / name / "index.json")
    # Preserve routing and saved semantic QA reports, without importing interim outputs.
    for path in sorted(root.glob("*.json")):
        pin(path)
    for name in ("QUESTIONS_AND_AI_CLASSIFICATIONS_2026-10-16.md",
                 "QUESTIONS_AND_AI_CLASSIFICATIONS_2026-10-16.zip", "LUNA_ALL_PAPERS.md",
                 "taxonomy-index-review.json", "p5-index-expansion.json"):
        if (root.parent / name).is_file():
            pin(root.parent / name)

    for paper, packs in PAPER_PACKS.items():
        for name in packs:
            directory = root / name
            original = _json(directory / "batch.json")
            validate_manifest(original)
            catalog = _json(directory / "full-taxonomy.json")
            sources = _json(directory / "sources.json")
            catalog_hash, sources_hash = digest(catalog), digest(sources)
            inventory_hashes = {source["sha256"] for source in sources.values()}
            catalog_json = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            catalogs[catalog_hash] = catalog
            local_ids = set()
            for candidate in catalog:
                node_id = candidate["node_id"]
                if node_id in local_ids or (node_id in nodes and nodes[node_id] != candidate):
                    raise ValueError("Duplicate or conflicting candidate node ID")
                local_ids.add(node_id)
                nodes[node_id] = candidate
                for reference in candidate["textbook_references"]:
                    sha = reference["sha256"]
                    artifact = artifacts.get(reference["artifact_id"])
                    if artifact and artifact["sha256"] != sha:
                        raise ValueError("Taxonomy artifact hash mismatch")
                    blob = project / "data/blobs" / sha[:2] / sha[2:4] / (sha + ".pdf")
                    if not blob.exists():
                        blob = project / artifact["local_path"] if artifact else root.parent / Path(urlparse(reference["download_url"]).path).name
                    total = pdf(blob, sha)
                    pages(reference["pdf_page_start"], reference["pdf_page_end"], total)
            for document_id, source in sources.items():
                identity = (source["sha256"], source["blob_path"])
                if document_id in source_ids and source_ids[document_id] != identity:
                    raise ValueError("Conflicting question source identity")
                source_ids[document_id] = identity
                pdf(Path(source["blob_path"]), source["sha256"])
            index = _json(directory / "index.json")
            by_id = {record["question_id"]: record for record in original["records"]}
            if set(by_id) != {item["question_id"] for item in index}:
                raise ValueError("Pack index and batch records differ")
            for filename in ("batch.json", "index.json", "full-taxonomy.json", "sources.json"):
                pin(directory / filename)
            for path in sorted(directory.glob("*.md")):
                pin(path)
            for path in sorted((directory / "corrections-history").rglob("*")):
                if path.is_file():
                    pin(path)
            for item in index:
                question_id = item["question_id"]
                path = directory / "records" / (question_id + ".json")
                record = _json(path)
                if record != by_id[question_id] or record["context"]["paper_id"] != f"s2023.{paper}":
                    raise ValueError("Record differs from batch or corrected paper")
                source = sources[str(record["document_id"])]
                if source["sha256"] != record["document_sha256"]:
                    raise ValueError("Question source hash mismatch")
                context_pages(record["context"], inventory_hashes)
                saved_path = directory / "results-direct" / (question_id + ".json")
                saved = _json(saved_path)
                execution = saved["execution"]
                if (execution["candidate_catalog_hash"], execution["source_catalog_hash"], execution["original_input_hash"]) != (catalog_hash, sources_hash, record["input_hash"]):
                    raise ValueError("Saved execution input hashes changed")
                expanded = {**record, "candidates": catalog,
                    "input_hash": _expanded_hash(record, catalog_json, sources_hash)}
                mappings = validated_mappings(expanded, saved["result"])
                if len(mappings) != item["gradable_parts"]:
                    raise ValueError("Record part count differs from pack index")
                for evidence in execution["source_evidence"]:
                    source = sources[str(evidence["document_id"])]
                    for page in evidence["pdf_pages"]:
                        pages(page, page, pdf_cache[source["sha256"]])
                compact = {key: value for key, value in record.items() if key != "candidates"}
                compact.update(catalog_hash=catalog_hash, mappings=mappings, execution=execution,
                    pack=name, result_hash=digest(saved["result"]), original_input_hash=record["input_hash"])
                compact["input_hash"] = digest({key: value for key, value in compact.items() if key != "input_hash"})
                records.append(compact)
                pin(path)
                pin(saved_path)
    if len(records) != EXPECTED_ROOTS or len(nodes) != EXPECTED_CANDIDATES or len(source_ids) != EXPECTED_SOURCES:
        raise ValueError("Baseline requires 3300 catalog nodes and 94 question sources")
    manifest = dict(release_id="baseline-2026-10-16", target_attempt="2027-05",
        roots=len(records), parts=sum(len(record["mappings"]) for record in records),
        papers=status["papers"], candidate_count=len(nodes), question_source_count=len(source_ids),
        files=files, sources=source_files, catalogs={key: len(value) for key, value in catalogs.items()})
    return dict(release_id=manifest["release_id"], target_attempt=manifest["target_attempt"],
        manifest_hash=digest(manifest), manifest=manifest, catalogs=catalogs, records=records)
