"""Evidence-backed contents-page drafts; never mutate or approve a taxonomy."""

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re

import pymupdf


_STRUCTURE = re.compile(r"^(MODULE|CHAPTER|UNIT)\s*[-–—]?\s*(\d+|[IVXLCDM]+)\s*[:.\-–—]?\s*(.*)$", re.I)
_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)(?:\.(?!\d)|\s)\s*(.*)$")
_REFERENCE = re.compile(r"[.．…]{2,}\s*(\d+(?:\.\d+)*(?:\s*[-–]\s*\d+(?:\.\d+)*)?)\s*$")
_EXCLUDED = re.compile(r"^(learning outcomes?|(?:chapter|unit) overview|contents|summary|test your|questions?|answers?|practice questions?|shortcut to|annexure)\b", re.I)


@dataclass
class IndexEntry:
    id: str
    parent_id: str | None
    kind: str
    number: str
    title: str
    printed_page_reference: str | None
    source_pdf_pages: list[int]
    raw_text: str


def parse_index_pages(pages: list[tuple[int, str]]) -> tuple[list[IndexEntry], list[dict]]:
    """Parse already-selected contents pages, retaining unresolved source text.

    Printed references are book labels, not PDF offsets. Numbered descendants
    are attached only to an observed prefix; a missing prefix is flagged.
    """
    entries: list[IndexEntry] = []
    entry_kinds: dict[str, str] = {}
    unresolved = []
    context: dict[str, str] = {}
    numbered: dict[str, str] = {}
    pending: list[str] = []
    evidence: list[int] = []

    def flush():
        if not pending:
            return
        raw = " ".join(pending)
        source_pages = list(evidence)
        pending.clear()
        evidence.clear()
        reference = _REFERENCE.search(raw)
        content = raw[:reference.start()].strip() if reference else raw
        if _EXCLUDED.match(content):
            return
        structure = _STRUCTURE.match(content)
        number_match = _NUMBER.match(content)
        if structure:
            kind, number, title = structure.groups()
            kind = kind.lower()
            parent = context.get("module") if kind == "chapter" else context.get("chapter") if kind == "unit" else None
            if kind in {"module", "chapter", "unit"}:
                numbered.clear()
            if kind == "module":
                context.clear()
            elif kind == "chapter":
                context.pop("unit", None)
        elif number_match and reference:
            number, title = number_match.groups()
            prefix = number.rsplit(".", 1)[0] if "." in number else None
            parent = numbered.get(prefix) if prefix else None
            kind = "subtopic" if parent and entry_kinds[parent] in {"topic", "subtopic"} else "topic"
            if parent is None:
                parent = context.get("unit", context.get("chapter", context.get("module")))
                if prefix:
                    unresolved.append({"reason": "number_prefix_not_observed", "prefix": prefix, "raw_text": raw, "source_pdf_pages": source_pages})
        else:
            unresolved.append({"reason": "unparsed_line", "raw_text": raw, "source_pdf_pages": source_pages})
            return
        if not title and kind != "module":
            unresolved.append({"reason": "missing_title", "raw_text": raw, "source_pdf_pages": source_pages})
            return
        entry_id = f"index-{len(entries) + 1}"
        entries.append(IndexEntry(entry_id, parent, kind, number, title or f"Module {number}", reference.group(1) if reference else None, source_pages, raw))
        entry_kinds[entry_id] = kind
        if structure:
            context[kind] = entry_id
            if kind in {"chapter", "unit"}:
                numbered[number] = entry_id
        else:
            numbered[number] = entry_id

    for pdf_page, text in pages:
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or line.startswith("©") or re.fullmatch(r"[ivxlcdm]+|\d+", line, re.I):
                continue
            if re.match(r"^(?:DETAILED\s+)?CONTENTS\b", line, re.I):
                flush()
                module = re.search(r"MODULE\s*[-–—]?\s*(\d+)", line, re.I)
                if module:
                    pending.append(f"MODULE {module.group(1)}")
                    evidence.append(pdf_page)
                    flush()
                continue
            if _STRUCTURE.match(line) or _NUMBER.match(line) or _EXCLUDED.match(line):
                flush()
            pending.append(line)
            if pdf_page not in evidence:
                evidence.append(pdf_page)
            if _REFERENCE.search(line):
                flush()
    flush()
    return entries, unresolved


def extract_index(path: Path, pdf_pages: list[int] | None = None) -> dict:
    """Read a front-matter PDF; automatic selection starts at detailed contents."""
    with pymupdf.open(path) as pdf:
        texts = [page.get_text(sort=True) for page in pdf]
    if pdf_pages is None:
        starts = [i for i, text in enumerate(texts) if re.search(r"DETAILED\s+CONTENTS", text, re.I)]
        if not starts:
            starts = [i for i, text in enumerate(texts) if re.search(r"^\s*CONTENTS\s*$", text, re.M | re.I)]
        pdf_pages = list(range(starts[0] + 1, len(texts) + 1)) if starts else []
    if any(page < 1 or page > len(texts) for page in pdf_pages):
        raise ValueError(f"PDF pages must be between 1 and {len(texts)}")
    entries, unresolved = parse_index_pages([(page, texts[page - 1]) for page in pdf_pages])
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "selected_pdf_pages": pdf_pages,
            "entries": [asdict(entry) for entry in entries], "unresolved": unresolved,
            "selection_issue": None if pdf_pages else "No contents heading found; select PDF pages explicitly"}


def build_index_report(manifest: dict, base_path: Path, pdf_pages: list[int] | None = None) -> dict:
    """Reconcile front-matter index entries with exact names in the draft tree."""
    def normalize(value):
        module = re.fullmatch(r"module\s*[-–—]?\s*(\d+)", value, flags=re.I)
        if module:
            return f"module {module.group(1)}"
        value = re.sub(r"^(?:chapter|unit)\s*[-–—]?\s*\d+\s*[:.\-–—]?", "", value, flags=re.I)
        return re.sub(r"[^\w]+", " ", value.casefold()).strip()

    nodes = manifest["nodes"]
    by_id = {node["id"]: node for node in nodes}

    def path_titles(node):
        titles = []
        while node is not None:
            titles.append(normalize(node["name"]))
            node = by_id.get(node["parent_id"])
        return tuple(reversed(titles))

    reports = []
    for artifact in manifest["textbook_artifacts"]:
        if artifact.get("artifact_role") != "front_matter":
            continue
        path = base_path / artifact["local_path"]
        report = {"artifact_id": artifact["id"], "paper_id": artifact["paper_id"], "local_path": str(path), "download_url": artifact["download_url"]}
        if not path.is_file():
            report["source_issue"] = "Local front-matter PDF is missing"
            reports.append(report)
            continue
        report.update(extract_index(path, pdf_pages))
        report["hash_matches_manifest"] = report["sha256"] == artifact["sha256"]
        entry_paths = {}
        paper_nodes = [node for node in nodes if node["paper_id"] == artifact["paper_id"]]
        for entry in report["entries"]:
            parent_path = entry_paths.get(entry["parent_id"], ())
            entry_path = parent_path + (normalize(entry["title"]),)
            entry_paths[entry["id"]] = entry_path
            matches = [node for node in paper_nodes if normalize(node["name"]) == normalize(entry["title"]) and node["kind"] == entry["kind"]]
            exact = [node for node in matches if path_titles(node) == entry_path]
            entry["matching_node_ids"] = [node["id"] for node in exact]
            entry["same_title_node_ids"] = [node["id"] for node in matches]
            entry["reconciliation"] = "exact_path_match" if len(exact) == 1 else "ambiguous_path_match" if exact else "title_match_requires_hierarchy_review" if matches else "missing_from_draft"
        reports.append(report)
    return {"version_id": manifest["version_id"], "target_attempt": manifest["target_attempt"],
            "status": "draft_requires_curator_review", "published": False,
            "note": "Printed page labels are not PDF page offsets. Missing entries and unresolved lines require source review; this report does not approve or modify taxonomy nodes.",
            "sources": reports}
