"""Proposed classification labels backed by module contents, never release approval."""

from uuid import NAMESPACE_URL, uuid5

from caf_l0.releases import digest


def draft_candidates(index: dict, *, paper_id: str, download_url: str,
                     edition: str, applicable_attempts: list[str]) -> list[dict]:
    entries = {entry["id"]: entry for entry in index["entries"]}
    parents = {entry["parent_id"] for entry in index["entries"]}
    result = []
    for entry in index["entries"]:
        if entry["kind"] not in {"topic", "subtopic"} or entry["id"] in parents:
            continue
        chain = [entry]
        parent = entry["parent_id"]
        while parent:
            chain.insert(0, entries[parent])
            parent = entries[parent]["parent_id"]
        path = []
        for position, item in enumerate(chain):
            key = download_url + "#" + "/".join(
                f"{ancestor['kind']}:{ancestor['number']}:{ancestor['title']}"
                for ancestor in chain[:position + 1])
            path.append(dict(id=str(uuid5(NAMESPACE_URL, key)), name=item["title"],
                level=item["kind"], paper_id=paper_id))
        descriptor = dict(core_concept=entry["title"], terminology=[entry["title"]],
            scope=" / ".join(item["title"] for item in chain),
            status="index_derived_draft_requires_review", approved=False,
            applicability_status="source_attempts_only_target_release_not_approved",
            source_edition=edition, applicable_attempts=applicable_attempts,
            note="Index heading evidence only; no statutory interpretation or release approval is inferred.")
        references = [dict(artifact_id=str(uuid5(NAMESPACE_URL, download_url)),
            edition=edition, sha256=index["sha256"], download_url=download_url,
            pdf_page_start=min(entry["source_pdf_pages"]), pdf_page_end=max(entry["source_pdf_pages"]),
            printed_page_reference=entry["printed_page_reference"], review_status="pending",
            availability="verified_local_pdf", heading_origin="module_index")]
        result.append(dict(node_id=path[-1]["id"], paper_id=paper_id, path=path,
            descriptor_revision_id=None, descriptor_hash=digest(descriptor), descriptor=descriptor,
            textbook_references=references, source_evidence_hash=digest(references),
            experimental=True, heading_origin="module_index"))
    return result
