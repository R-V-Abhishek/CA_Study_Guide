"""Read-only, evidence-based corpus provenance baseline.

The report is diagnostic. It never repairs records or attributes legacy decisions
without an authenticated reviewer field. Database values share one repeatable-read
snapshot; filesystem checks are observations made during that transaction.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from caf_common.backup import database_content


CATEGORIES = (
    "confirmed synthetic", "suspected synthetic", "authentic source identified",
    "unresolved provenance",
)


def _rows(conn: Connection, sql: str) -> list[dict]:
    return [dict(row) for row in conn.execute(text(sql)).mappings()]


def _file_evidence(path: Path, expected_sha: str) -> dict:
    result = {"path": str(path), "exists": path.is_file(), "expected_sha256": expected_sha}
    if not result["exists"]:
        result["status"] = "missing"
        return result
    try:
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        result.update(actual_sha256=actual, status="match" if actual == expected_sha else "checksum_mismatch")
    except OSError as exc:
        result.update(status="unreadable", error=str(exc))
    return result


def _official(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return urlparse(url).scheme in {"http", "https"} and (host == "icai.org" or host.endswith(".icai.org"))


def _document_provenance(doc: dict) -> tuple[str, list[str]]:
    """Use exact fixture producer signatures, never a test filename alone."""
    evidence: list[str] = []
    fixture_pairs = (
        ("test_classify_", "/tmp/fake_classify.pdf", "tests/test_milestone4.py:test_classification_pipeline_persistence"),
        ("test_curate_", "/tmp/fake_curate.pdf", "tests/test_milestone4.py:test_curation_api_and_publishing"),
        ("test_bulk_", "/tmp/fake_bulk.pdf", "tests/test_milestone4.py:test_bulk_accept_bucket_a"),
    )
    for prefix, path, producer in fixture_pairs:
        if doc["sha256"].startswith(prefix) and doc["blob_path"] == path and doc["origin"] == "manual":
            return "confirmed synthetic", [f"Fixture hash prefix and blob path match {producer}"]
    if doc["depth_fixture"] and doc["blob_path"].startswith("/test/"):
        return "confirmed synthetic", ["Exact 'Draft test question for depth gate' text and /test/ blob path match tests/test_milestone7.py"]
    if doc["eval_fixture"] and doc["sha256"].startswith("eval_test_"):
        return "confirmed synthetic", ["eval_test_ hash and exact Eval test question pattern match tests/test_milestone8.py"]
    if doc["precision_fixture"] and doc["sha256"].startswith("prec_test_"):
        return "confirmed synthetic", ["prec_test_ hash and exact Prec test Q… uid=… pattern match tests/test_contracts.py"]
    if not re.fullmatch(r"[0-9a-fA-F]{64}", doc["sha256"]):
        evidence.append("Stored document checksum is not a SHA-256 hex digest")
    if doc["depth_fixture"] or doc["eval_fixture"] or doc["precision_fixture"]:
        evidence.append("Extracted question matches a repository fixture signature")
    if doc["synthetic_pdf_matches"] >= 3:
        evidence.append("At least three exact question fragments match the generated Suggested Answer fixture in tests/test_milestone3.py")
    if evidence:
        return "suspected synthetic", evidence
    source_urls = [url for url in doc["source_urls"] if _official(url)]
    if source_urls and doc["source_file"]["status"] == "match":
        return "authentic source identified", ["Official ICAI source URL identified and stored blob checksum matches", *source_urls]
    if source_urls:
        evidence.append("Official ICAI source URL identified, but source bytes are missing, unreadable, or disagree with stored checksum")
    if not doc["source_urls"]:
        evidence.append("No discovered-link source lineage")
    if doc["source_file"]["status"] != "match":
        evidence.append(f"Source file: {doc['source_file']['status']}")
    evidence.append("Available evidence does not establish authenticity")
    return "unresolved provenance", evidence


def collect_baseline(engine: Engine, project_root: Path = Path.cwd()) -> dict:
    """Collect all database observations without writable transactions or run logs."""
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            snapshot = _rows(conn, "SELECT txid_current_snapshot()::text AS snapshot, current_setting('transaction_read_only') AS read_only, current_setting('transaction_isolation') AS isolation, current_setting('TimeZone') AS timezone, current_setting('DateStyle') AS date_style")[0]
            revision = conn.execute(text("SELECT version_num FROM ops.alembic_version ORDER BY version_num")).scalars().all()
            tables = _rows(conn, "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('app','core','ref','ingest','intel','ops') AND table_type='BASE TABLE' ORDER BY table_schema, table_name")
            # Identifiers originate from PostgreSQL's catalog and are quoted by its dialect.
            quote = conn.dialect.identifier_preparer.quote
            counts = {
                f"{t['table_schema']}.{t['table_name']}": conn.execute(text(f"SELECT count(*) FROM {quote(t['table_schema'])}.{quote(t['table_name'])}")).scalar_one()
                for t in tables
            }
            groups = _rows(conn, "SELECT paper_id, attempt_id, doc_type_id, catalog_status, extract_status, count(*) AS count FROM ingest.document GROUP BY paper_id, attempt_id, doc_type_id, catalog_status, extract_status ORDER BY paper_id, attempt_id, doc_type_id, catalog_status, extract_status")
            documents = _rows(conn, """
                SELECT d.id, d.sha256, d.blob_path, d.origin, d.title, d.paper_id,
                       d.attempt_id, d.doc_type_id, d.catalog_status, d.extract_status,
                       d.created_run_id, d.extract_run_id,
                       ARRAY(SELECT l.url FROM ingest.discovered_link l WHERE l.document_id=d.id ORDER BY l.url) AS source_urls,
                       EXISTS(SELECT 1 FROM ingest.unit u WHERE u.document_id=d.id AND u.question_text='Draft test question for depth gate') AS depth_fixture,
                       EXISTS(SELECT 1 FROM ingest.unit u WHERE u.document_id=d.id AND u.question_text ~ '^Eval test question [0-9]+$') AS eval_fixture,
                       EXISTS(SELECT 1 FROM ingest.unit u WHERE u.document_id=d.id AND u.question_text ~ '^Prec test Q[0-9]+ uid=[0-9a-f]+$') AS precision_fixture,
                       (SELECT count(DISTINCT CASE
                           WHEN u.question_text LIKE '%Explain the recognition criteria under Ind AS 115 with reference to contract modifications.%' THEN 1
                           WHEN u.question_text LIKE '%XYZ Ltd faces a legal claim. Assess whether provision is required under Ind AS 37.%' THEN 2
                           WHEN u.question_text LIKE '%Discuss the professional ethics requirements under CA Act 1949.%' THEN 3
                           END) FROM ingest.unit u WHERE u.document_id=d.id) AS synthetic_pdf_matches
                FROM ingest.document d ORDER BY d.id
            """)
            for doc in documents:
                path = Path(doc["blob_path"])
                doc["source_file"] = _file_evidence(path if path.is_absolute() else project_root / path, doc["sha256"])
                doc["category"], doc["provenance_evidence"] = _document_provenance(doc)
            classification_groups = _rows(conn, "SELECT method, model_id, prompt_version, run_id, bucket, is_shadow, count(*) AS count FROM ingest.tag_suggestion GROUP BY method, model_id, prompt_version, run_id, bucket, is_shadow ORDER BY run_id, method, model_id, bucket")
            confidence_groups = _rows(conn, """
                SELECT method, model_id, run_id, confidence_bucket, count(*) AS count
                FROM (
                    SELECT method, model_id, run_id, CASE
                        WHEN evidence->'confidence' IS NULL OR evidence->'confidence'='null'::jsonb THEN 'absent'
                        WHEN jsonb_typeof(evidence->'confidence')<>'number' THEN 'invalid_type'
                        WHEN (evidence->>'confidence')::numeric NOT BETWEEN 0 AND 1 THEN 'out_of_range'
                        WHEN (evidence->>'confidence')::numeric<0.50 THEN '[0.00,0.50)'
                        WHEN (evidence->>'confidence')::numeric<0.80 THEN '[0.50,0.80)'
                        WHEN (evidence->>'confidence')::numeric<0.95 THEN '[0.80,0.95)'
                        ELSE '[0.95,1.00]'
                    END AS confidence_bucket FROM ingest.tag_suggestion
                ) confidence GROUP BY method, model_id, run_id, confidence_bucket
                ORDER BY run_id, method, model_id, confidence_bucket
            """)
            suggestions = _rows(conn, """
                SELECT s.id, s.unit_id, u.document_id, u.fingerprint, s.run_id, s.node_id,
                       s.model_id, s.method, s.bucket, s.is_shadow,
                       s.evidence, d.paper_id AS source_paper_id, n.paper_id AS node_paper_id
                FROM ingest.tag_suggestion s JOIN ingest.unit u ON u.id=s.unit_id
                JOIN ingest.document d ON d.id=u.document_id JOIN ref.node n ON n.id=s.node_id
                WHERE s.model_id='agent-semantic-v1' OR d.paper_id IS DISTINCT FROM n.paper_id
                ORDER BY s.id
            """)
            questionable: dict[tuple[str, int, str], list[dict]] = {}
            for suggestion in suggestions:
                reasons = []
                if suggestion["model_id"] == "agent-semantic-v1":
                    reasons.append("Rule/anchor classifier labelled as llm in scripts/annotate_batch.py; not an external semantic model call")
                    if suggestion["node_id"] == "P1-PZR6WV" and suggestion["bucket"] == "C" and suggestion["evidence"].get("core_concept") == "General financial reporting concept" and suggestion["evidence"].get("confidence") == 0.60:
                        reasons.append("Forced default identified by exact node, bucket, confidence and concept provenance from scripts/annotate_batch.py")
                source_paper = suggestion["source_paper_id"]
                cross = source_paper != suggestion["node_paper_id"]
                suggestion["cross_paper"] = cross
                suggestion["expected_integrated_paper_mapping"] = cross and source_paper is not None and source_paper.endswith(".P6")
                if cross and not suggestion["expected_integrated_paper_mapping"]:
                    reasons.append("Unexpected cross-paper mapping; source paper is not integrated Paper 6")
                suggestion["questionable_reasons"] = reasons
                if reasons:
                    questionable.setdefault((suggestion["fingerprint"], suggestion["run_id"], suggestion["node_id"]), []).append(suggestion)
            published_links = _rows(conn, """
                SELECT a.id AS appearance_id, a.unit_fingerprint, t.node_id, t.decision_id,
                       d.suggestion_run_id, d.action
                FROM core.appearance a JOIN core.appearance_tag t ON t.appearance_id=a.id
                LEFT JOIN core.decision d ON d.id=t.decision_id
                WHERE a.status='published' ORDER BY a.id, t.node_id
            """)
            questionable_published = []
            for link in published_links:
                linked = questionable.get((link["unit_fingerprint"], link["suggestion_run_id"], link["node_id"]), [])
                if linked:
                    questionable_published.append({**link, "suggestion_ids": [s["id"] for s in linked], "evidence": sorted({r for s in linked for r in s["questionable_reasons"]}), "association": "matching fingerprint, decision suggestion run and published node; does not prove curator relied on suggestion"})
            lineage = {
                "documents_without_source_links": [d["id"] for d in documents if not d["source_urls"]],
                "documents_without_created_run": [d["id"] for d in documents if d["created_run_id"] is None],
                "current_gradable_units_without_answers": _rows(conn, "SELECT u.id AS unit_id, u.document_id FROM ingest.unit u LEFT JOIN ingest.unit_answer a ON a.unit_id=u.id WHERE u.current AND u.is_gradable AND a.unit_id IS NULL ORDER BY u.id"),
                "empty_paired_answers": _rows(conn, "SELECT unit_id, answer_document_id, pairing_method FROM ingest.unit_answer WHERE nullif(btrim(answer_text),'') IS NULL AND mcq_correct_option IS NULL ORDER BY unit_id"),
                "answer_pairing_methods": _rows(conn, "SELECT pairing_method, count(*) AS count FROM ingest.unit_answer GROUP BY pairing_method ORDER BY pairing_method"),
                "published_reference_issues": _rows(conn, """
                    SELECT a.id AS appearance_id, a.source_unit_id,
                           (u.id IS NULL) AS missing_unit,
                           (d.id IS NULL) AS missing_document,
                           (u.id IS NOT NULL AND u.fingerprint<>a.unit_fingerprint) AS fingerprint_mismatch,
                           (ud.id IS NOT NULL AND ud.sha256<>a.doc_sha256) AS source_document_mismatch
                    FROM core.appearance a LEFT JOIN ingest.unit u ON u.id=a.source_unit_id
                    LEFT JOIN ingest.document d ON d.sha256=a.doc_sha256
                    LEFT JOIN ingest.document ud ON ud.id=u.document_id
                    WHERE a.status='published' AND (u.id IS NULL OR d.id IS NULL OR u.fingerprint<>a.unit_fingerprint OR ud.sha256<>a.doc_sha256)
                    ORDER BY a.id
                """),
                "published_tags_without_decisions": _rows(conn, "SELECT t.appearance_id, t.node_id, t.decision_id FROM core.appearance_tag t LEFT JOIN core.decision d ON d.id=t.decision_id WHERE d.id IS NULL ORDER BY t.appearance_id, t.node_id"),
            }
            synthetic_appearances = _rows(conn, """
                SELECT id, unit_fingerprint, doc_sha256, gist FROM core.appearance
                WHERE unit_fingerprint LIKE 'prac_fp_%' AND doc_sha256 LIKE 'practice_sha_%'
                      AND gist='Practice test case on lease modifications' ORDER BY id
            """)
            for appearance in synthetic_appearances:
                appearance.update(category="confirmed synthetic", provenance_evidence=["Combined fingerprint, document checksum and exact gist match tests/test_milestone6.py:test_practice_signal_scoring"])
            published_cross_paper = _rows(conn, """
                SELECT a.id AS appearance_id, a.source_paper_id, t.node_id,
                       n.paper_id AS node_paper_id, t.decision_id
                FROM core.appearance a JOIN core.appearance_tag t ON t.appearance_id=a.id
                JOIN ref.node n ON n.id=t.node_id
                WHERE a.status='published' AND a.source_paper_id<>n.paper_id
                ORDER BY a.id, t.node_id
            """)
            for mapping in published_cross_paper:
                mapping["expected_integrated_paper_mapping"] = mapping["source_paper_id"].endswith(".P6")
            appearances = _rows(conn, "SELECT id, source_unit_id, doc_sha256, status FROM core.appearance ORDER BY id")
            docs_by_sha = {d["sha256"]: d for d in documents}
            known_synthetic = {a["id"]: a for a in synthetic_appearances}
            for appearance in appearances:
                doc = docs_by_sha.get(appearance["doc_sha256"])
                if appearance["id"] in known_synthetic:
                    evidence = known_synthetic[appearance["id"]]
                    appearance["category"] = evidence["category"]
                    appearance["provenance_evidence"] = evidence["provenance_evidence"]
                elif doc:
                    appearance["category"] = doc["category"]
                    appearance["document_id"] = doc["id"]
                    appearance["provenance_evidence"] = [f"Document {doc['id']} provenance: {item}" for item in doc["provenance_evidence"]]
                elif not re.fullmatch(r"[0-9a-fA-F]{64}", appearance["doc_sha256"]):
                    appearance["category"] = "suspected synthetic"
                    appearance["provenance_evidence"] = ["No matching source document; stored checksum is not a SHA-256 hex digest"]
                else:
                    appearance["category"] = "unresolved provenance"
                    appearance["provenance_evidence"] = ["No matching source document"]
            score_context = _rows(conn, "SELECT id, scoring_version, config_hash, target_attempt_id, shadow, is_current, status, started_at, finished_at FROM intel.score_run ORDER BY id")
            taxonomy = _rows(conn, "SELECT id, git_sha, yaml_hash, loaded_at, notes FROM ref.taxonomy_version ORDER BY id")
            taxonomy_completeness = {
                "nodes_by_paper_level": _rows(conn, "SELECT paper_id, level, status, count(*) AS count FROM ref.node GROUP BY paper_id, level, status ORDER BY paper_id, level, status"),
                "descriptors_by_approval_source": _rows(conn, "SELECT approved, source, count(*) AS count FROM ref.descriptor GROUP BY approved, source ORDER BY approved, source"),
                "subtopics_missing_descriptors": _rows(conn, "SELECT n.id AS node_id, n.paper_id, n.status FROM ref.node n LEFT JOIN ref.descriptor d ON d.node_id=n.id WHERE n.level='subtopic' AND d.node_id IS NULL ORDER BY n.paper_id, n.id"),
            }
            classification_runs = _rows(conn, "SELECT DISTINCT r.id, r.stage, r.git_sha, r.config_hash, r.args, r.status FROM ops.run r JOIN ingest.tag_suggestion s ON s.run_id=r.id ORDER BY r.id")
            protected_content = database_content(conn, ("app", "core"))
    return {
        "report_version": "phase0.provenance.v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_revision": revision, "database_transaction": snapshot,
        "source_database_policy": "All database reads share one PostgreSQL-enforced read-only transaction. Audit creates no run, event, or other source record.",
        "filesystem_consistency": "Source-file checks are observations, not a PostgreSQL snapshot of filesystem state.",
        "limitations": ["Legacy core.decision has no reliable reviewer identity. No decision is attributed to a student.", "Official URL plus matching bytes identifies source provenance; it does not validate extracted text or classification.", "Synthetic signatures cover known repository fixture producers; absence of a signature is not proof of authenticity.", "scripts/classify_worker.py substitutes the first available node for invalid model outputs without recording that fallback; those forced defaults cannot be reliably identified retrospectively.", "Reports identify concerns only; no corpus records were changed."],
        "table_counts": counts, "personal_data_counts": {k: v for k, v in counts.items() if k.startswith("app.")},
        "protected_table_content": protected_content,
        "document_processing_groups": groups, "documents": documents,
        "provenance_category_counts": {category: Counter(d["category"] for d in documents)[category] for category in CATEGORIES},
        "confirmed_synthetic_appearances": synthetic_appearances,
        "appearance_provenance": appearances,
        "published_cross_paper_mappings": published_cross_paper,
        "classification_groups": classification_groups, "classification_runs": classification_runs,
        "confidence_groups": confidence_groups,
        "confidence_scale": "Numeric evidence.confidence uses a 0–1 scale. Local cascade and secondary suggestions often omit it; absence is reported explicitly, never inferred from A–D classification buckets.",
        "audited_suggestions": suggestions, "questionable_published_appearances": questionable_published,
        "lineage": lineage, "taxonomy_versions": taxonomy,
        "taxonomy_completeness": taxonomy_completeness, "score_context": score_context,
    }


def render_markdown(report: dict) -> str:
    counts = report["provenance_category_counts"]
    files = Counter(d["source_file"]["status"] for d in report["documents"])
    confidence_counts = Counter()
    for group in report["confidence_groups"]:
        confidence_counts[group["confidence_bucket"]] += group["count"]
    lines = ["# Phase 0 provenance baseline", "", f"Created: {report['created_at']}",
             f"Schema revision: {', '.join(report['schema_revision'])}",
             f"Database transaction: {report['database_transaction']['isolation']}, read-only={report['database_transaction']['read_only']}",
             "", "| Document category | Count |", "| --- | ---: |"]
    lines.extend(f"| {category} | {counts[category]} |" for category in CATEGORIES)
    lines.extend(["", f"Source files: {dict(files)}.",
                  f"Published appearances associated with questionable suggestions: {len(report['questionable_published_appearances'])}.",
                  f"Confirmed synthetic standalone appearances: {len(report['confirmed_synthetic_appearances'])}.",
                  f"Current gradable units without paired answers: {len(report['lineage']['current_gradable_units_without_answers'])}.",
                  f"Published source-reference issues: {len(report['lineage']['published_reference_issues'])}.",
                  f"Subtopics without descriptors: {len(report['taxonomy_completeness']['subtopics_missing_descriptors'])}.",
                  f"Numeric confidence groups: {dict(sorted(confidence_counts.items()))}.",
                  "", "Personal-data counts:", ""])
    lines.extend(f"- {table}: {count}" for table, count in report["personal_data_counts"].items())
    lines.extend(["", "Limitations:", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend([f"- {report['filesystem_consistency']}", f"- {report['source_database_policy']}", f"- {report['confidence_scale']}", "", "See baseline.json for processing groups, exact IDs, evidence, taxonomy/descriptor completeness, classification runs and score version/target contexts.", ""])
    return "\n".join(lines)


def write_baseline(report: dict, output_root: Path) -> Path:
    """Create a unique report directory; never overwrite an earlier audit."""
    folder = output_root / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "baseline.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    (folder / "baseline.md").write_text(render_markdown(report), encoding="utf-8")
    return folder
