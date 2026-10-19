"""Read-only historical suggestion audit; never invent review/provenance bindings."""

import json
from pathlib import Path

import sqlalchemy as sa
import typer

from caf_db.engine import get_engine

app = typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
def audit(report: Path = Path("docs/Phase5_Legacy_Audit.json")):
    with get_engine("migration").connect() as connection:
        rows = connection.execute(sa.text("""
            SELECT s.id, s.unit_id, s.run_id, s.node_id, s.method, s.model_id,
                   s.prompt_version, s.taxonomy_version_id, s.descriptor_revision_id,
                   r.stage, r.taxonomy_version_id AS run_taxonomy_version_id,
                   EXISTS(SELECT 1 FROM ops.llm_call c WHERE c.run_id=s.run_id
                          AND c.model_id=s.model_id AND c.status='ok') AS recorded_model_call,
                   EXISTS(SELECT 1 FROM core.decision d JOIN ingest.unit u
                          ON u.fingerprint=d.unit_fingerprint WHERE u.id=s.unit_id
                          AND d.action IN ('accept','accept_alt','edit','bulk_accept')
                          AND d.payload->>'primary_node_id'=s.node_id) AS accepted_label
            FROM ingest.tag_suggestion s JOIN ops.run r ON r.id=s.run_id
            ORDER BY s.run_id,s.id
        """)).mappings().all()
        flagged = []
        runs = {}
        for row in rows:
            key = str(row["run_id"])
            run = runs.setdefault(key, {"stage": row["stage"], "methods": {}, "models": {},
                                       "suggestions": 0, "flagged": 0})
            run["suggestions"] += 1
            run["methods"][row["method"]] = run["methods"].get(row["method"], 0) + 1
            model = row["model_id"] or "unrecorded"
            run["models"][model] = run["models"].get(model, 0) + 1
            reasons = []
            if row["taxonomy_version_id"] is None or row["descriptor_revision_id"] is None:
                reasons.append("missing_revision_evidence")
            if row["run_taxonomy_version_id"] != row["taxonomy_version_id"]:
                reasons.append("run_taxonomy_mismatch")
            if row["method"] == "llm" and (
                not row["model_id"] or not row["prompt_version"] or not row["recorded_model_call"]
            ):
                reasons.append("missing_model_call_provenance")
            if row["method"] == "anchor":
                reasons.append("uncalibrated_anchor_requires_label_support_review")
            if reasons:
                run["flagged"] += 1
                flagged.append({"suggestion_id": row["id"], "unit_id": row["unit_id"],
                                "run_id": row["run_id"], "node_id": row["node_id"],
                                "accepted_label_requires_review": row["accepted_label"],
                                "reasons": reasons, "verification_state": "unknown"})
        accepted = connection.scalar(sa.text("SELECT count(*) FROM core.decision WHERE action IN ('accept','accept_alt','edit','bulk_accept')"))
        published = connection.scalar(sa.text("SELECT count(*) FROM core.appearance WHERE status='published'"))
    result = {"read_only": True, "suggestions": len(rows), "flagged_suggestions": len(flagged),
              "accepted_decisions_preserved": accepted, "published_appearances_preserved": published,
              "reviewer_identities_inferred": False, "runs": runs, "re_review_queue": flagged}
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Audited {len(rows)} suggestions; {len(flagged)} require evidence review: {report}")


if __name__ == "__main__":
    app()
