"""Render complete pinned questions and AI proposals for independent student review."""

import json
import re

from caf_l3.batches import validated_mappings


def _block(value: object) -> str:
    text = value if type(value) is str else json.dumps(value, ensure_ascii=False, indent=2)
    text = re.sub(r"sk-or-v1-[A-Za-z0-9_-]+", "[REDACTED]", text)
    longest = max((len(match.group()) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}\n"


def render_review_markdown(manifest: dict, results: dict[str, dict],
                           failures: dict[str, str] | None = None) -> str:
    """Produce a review artifact without publishing or modifying classifications."""
    failures = failures or {}
    records = manifest["records"]
    ids = {record["question_id"] for record in records}
    if (set(results) | set(failures)) - ids:
        raise ValueError("Review results contain unknown question IDs")
    if set(results) & set(failures):
        raise ValueError("A question cannot have both a result and a failure")
    mappings = {record["question_id"]: validated_mappings(record, results[record["question_id"]]["result"])
                for record in records if record["question_id"] in results}
    missing = len(ids - set(results) - set(failures))
    lines = ["# Questions and AI classification proposals\n",
        "AI proposals require independent student review. No labels are approved or published by this document. "
        "Confidence scores and buckets are uncalibrated; they are not probabilities of correctness.\n",
        f"Questions: {len(records)} · Classified: {len(results)} · Failed: {len(failures)} · Missing: {missing}\n",
        "## Pinned taxonomy and batch\n", _block({key: manifest[key] for key in
            ("taxonomy_release_id", "taxonomy_version_id", "taxonomy_manifest_hash", "batch_key", "experimental")
            if key in manifest})]
    if manifest.get("experimental"):
        lines.append("This pack includes unapproved draft evidence. Review the question extraction and taxonomy as well as the proposed labels.\n")
    if "classifier" in manifest:
        lines.extend(["**Requested classifier**\n", _block({key: manifest["classifier"][key] for key in
            ("method", "model_id", "prompt_version", "retrieval", "candidate_limit") if key in manifest["classifier"]})])

    def parts(values: list[dict], *, answer: bool = False, depth: int = 0) -> None:
        for index, part in enumerate(values, 1):
            lines.append(f"**{'Answer part' if answer else 'Question part'} {depth + 1}.{index}**\n")
            lines.append(_block({key: value for key, value in part.items() if key not in
                                {"parts", "question_text", "answer_text"}}))
            lines.append(_block(part["answer_text" if answer else "question_text"]))
            parts(part["parts"], answer=answer, depth=depth + 1)

    for index, record in enumerate(records, 1):
        question_id = record["question_id"]
        context = record["context"]
        lines.extend([f"## Question {index}\n", "### Source and identity\n",
            _block({**{key: record[key] for key in ("question_id", "document_id", "document_sha256",
                    "extraction_revision_id", "extraction_digest", "input_hash", "original_paper_id",
                    "routing_original_input_hash", "routing_evidence") if key in record},
                    "context": {key: value for key, value in context.items() if key not in
                        {"common_stem", "question_text", "parts", "answers"}}}),
            "### Complete question\n", "**Shared stem**\n", _block(context["common_stem"]),
            "**Root question**\n", _block(context["question_text"])])
        parts(context["parts"])
        lines.extend(["### Available answers\n", _block({"answer_status": context["answer_status"]})])
        if not context["answers"]:
            lines.append("No answer is available in the pinned input.\n")
        parts(context["answers"], answer=True)
        lines.append("### AI proposals and student review\n")
        if question_id in results:
            execution = results[question_id]["execution"]
            lines.extend(["**Execution provenance**\n", _block({key: execution[key] for key in
                ("model_id", "requested_model_id", "method", "provider", "usage", "prompt_version", "latency_ms",
                 "max_output_tokens",
                 "candidate_scope", "candidate_catalog_hash", "source_catalog_hash", "original_input_hash",
                 "catalog_delta_review", "semantic_review")
                if key in execution})])
            if execution.get("source_evidence"):
                lines.append("**Original PDF evidence used to recover question context**\n")
                for source in execution["source_evidence"]:
                    lines.append(_block({key: value for key, value in source.items() if key != "original_pdf_pages"}))
                    for page in source.get("original_pdf_pages", []):
                        lines.extend([f"**Original PDF page {page['pdf_page']}**\n", _block(page["text"])])
        elif question_id in failures:
            lines.extend(["**Classification failed. No AI proposal is available.**\n", _block(failures[question_id])])
        else:
            lines.append("**Classification missing. No AI proposal is available.**\n")
        by_part = {mapping["part_id"]: mapping for mapping in mappings.get(question_id, [])}
        candidates = {candidate["node_id"]: candidate for candidate in record["candidates"]}
        for part_index, part_id in enumerate(context["classification_part_ids"], 1):
            lines.extend([f"#### Gradable part {part_index}\n", _block({"part_id": part_id})])
            mapping = by_part.get(part_id)
            if mapping:
                lines.extend([_block({key: mapping[key] for key in ("outcome", "confidence", "bucket")}),
                              "Confidence and bucket are uncalibrated.\n",
                              "**Model reason**\n", _block(mapping["evidence"]["note"])])
                labels = ([mapping["primary_node_id"]] if mapping["primary_node_id"] else []) + mapping["secondary_node_ids"]
                if not labels:
                    lines.append("No accepted primary or secondary label is proposed.\n")
                for label_index, node_id in enumerate(labels):
                    candidate = candidates[node_id]
                    lines.extend([f"**{'Primary' if label_index == 0 else 'Secondary'} label**\n",
                        _block({"breadcrumb": " → ".join(node["name"] for node in candidate["path"]),
                                "node_id": node_id, "paper_id": candidate["paper_id"],
                                "path": candidate["path"]}),
                        "**Supporting evidence**\n", _block(mapping["evidence"]["labels"][node_id]),
                        "**Pinned textbook and descriptor evidence**\n",
                        _block({key: candidate[key] for key in ("descriptor_revision_id", "descriptor_hash",
                            "descriptor", "textbook_references", "source_evidence_hash") if key in candidate})])
            lines.extend(["- [ ] Agree with the proposed classification\n",
                          "- [ ] Change the classification\n", "- [ ] Unresolved / more evidence needed\n",
                          "Correction (primary and secondary labels): ____________________\n",
                          "Reason and source evidence: ____________________\n",
                          "Reviewer and date: ____________________\n"])
    return "\n".join(lines)
