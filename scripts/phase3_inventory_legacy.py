"""Preserve legacy priors and inventory historical sources without transferring tags."""

import hashlib
import json
from pathlib import Path

import sqlalchemy as sa
import typer
import yaml

from caf_db.engine import get_engine

app = typer.Typer()


@app.command()
def inventory(audit_path: Path, output: Path = Path("taxonomy/textbook_v1")):
    audit = json.loads(audit_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for doc in audit["documents"]:
        authentic = doc["category"] == "authentic source identified"
        records.append({"document_id": doc["id"], "sha256": doc["sha256"],
            "paper_id": doc["paper_id"], "source_attempt_id": doc["attempt_id"],
            "doc_type_id": doc["doc_type_id"], "provenance_category": doc["category"],
            "source_urls": doc["source_urls"], "historical_labels_policy": "retained in legacy history",
            "queue_status": "awaiting_final_level_and_scheme_verification" if authentic else "preserved_outside_verified_queue",
            "extraction_reclassification_phase": 4})
    result = {"audit_created_at": audit["created_at"], "provenance_counts": audit["provenance_category_counts"],
              "genuine_new_taxonomy_coverage": 0, "records": records}
    (output / "existing_corpus_inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    crosswalk = []
    with get_engine("backup").connect() as connection:
        for node in connection.execute(sa.text("SELECT id,name,paper_id,level FROM ref.node ORDER BY paper_id,id")).mappings():
            crosswalk.append({"old_node_id": node["id"], "new_node_id": None, "relation": "unresolved",
                "evidence": {"legacy_name": node["name"], "legacy_paper_id": node["paper_id"],
                             "legacy_level": node["level"],
                             "review_note": "No reviewed equivalence; independently constructed textbook nodes require source-based crosswalk review"}})
    (output / "crosswalk.json").write_text(json.dumps(crosswalk, indent=2) + "\n")
    priors = {"status": "archived_generated_legacy", "official_prior_verified": False, "files": []}
    for paper in range(1, 7):
        path = Path(f"taxonomy/weightage/P{paper}.yaml")
        priors["files"].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "data": yaml.safe_load(path.read_text())})
    Path("taxonomy/legacy_weightages.json").write_text(json.dumps(priors, indent=2) + "\n")
    typer.echo(f"Preserved {len(records)} source identities and {len(crosswalk)} unresolved legacy mappings; archived six generated priors")


if __name__ == "__main__":
    app()
