"""One student review pack with verified coverage of corrected paper assignments."""

import json
from pathlib import Path
import tempfile

from caf_l3.paper_workers import load_review
from caf_l3.review_markdown import render_review_markdown

PAPER_PACKS = {
    "P1": ["P1-corrected"],
    "P2": ["P2", "P2-rerouted"],
    "P3": ["P3", "P3-rerouted"],
    "P4": ["P4-corrected", "P4-rerouted"],
    "P5": ["P5-index-complete", "P5-rerouted", "P5-from-P4"],
    "P6": ["P6-index-complete", "P6-rerouted", "P6-from-P4"],
}
ORIGINAL_PACKS = [f"P{number}" for number in range(1, 7)]


def corpus_status(root: Path) -> dict:
    """Count saved checkpoints, refusing duplicate or missing corpus identities."""
    return _corpus_snapshot(root)[0]


def _corpus_snapshot(root: Path) -> tuple[dict, dict[str, set[str]]]:
    original_ids = set()
    for name in ORIGINAL_PACKS:
        original_ids.update(item["question_id"] for item in json.loads((root / name / "index.json").read_text()))
    seen = set()
    papers = {}
    saved_ids = {}
    for paper, packs in PAPER_PACKS.items():
        roots = completed = parts = completed_parts = 0
        for name in packs:
            directory = root / name
            saved_ids[name] = set()
            for item in json.loads((directory / "index.json").read_text()):
                question_id = item["question_id"]
                if question_id in seen:
                    raise ValueError("A question appears in more than one final paper pack")
                seen.add(question_id)
                roots += 1
                parts += item["gradable_parts"]
                path = directory / "results-direct" / (question_id + ".json")
                if path.exists():
                    saved = json.loads(path.read_text())
                    if saved["result"]["question_id"] != question_id:
                        raise ValueError("Saved result belongs to another question")
                    completed += 1
                    completed_parts += len(saved["result"]["mappings"])
                    saved_ids[name].add(question_id)
        papers[paper] = dict(roots=roots, saved=completed, pending=roots - completed,
            parts=parts, saved_parts=completed_parts, packs=packs)
    if seen != original_ids:
        raise ValueError("Corrected paper packs do not cover the original corpus exactly")
    return dict(total=len(seen), saved=sum(p["saved"] for p in papers.values()),
        pending=sum(p["pending"] for p in papers.values()), papers=papers), saved_ids


def render_corpus(root: Path, output: Path, *, allow_pending: bool = False) -> dict:
    status, saved_ids = _corpus_snapshot(root)
    if status["pending"] and not allow_pending:
        raise ValueError(f"{status['pending']} roots still lack classifications; use allow_pending only for an explicit interim review")
    if output.exists():
        raise ValueError("Markdown already exists; preserve student edits and choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage the complete validated artifact before creating the user-facing file.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", dir=output.parent) as staged:
        staged.write("# Luna classification review — all papers\n\n")
        staged.write(f"Roots: {status['total']} · Saved AI outputs: {status['saved']} · Pending: {status['pending']}\n\n")
        if status["pending"]:
            staged.write("**INTERIM: classification is incomplete. Missing AI outputs are marked explicitly.**\n\n")
        staged.write("These are unapproved student-review proposals. Corrected paper routing is preserved with source evidence. No queue imports or publication are performed.\n\n")
        staged.write("| Paper | Roots | Saved AI outputs | Pending |\n|---|---:|---:|---:|\n")
        for paper, counts in status["papers"].items():
            staged.write(f"| {paper} | {counts['roots']} | {counts['saved']} | {counts['pending']} |\n")
        for paper, packs in PAPER_PACKS.items():
            for name in packs:
                manifest, results = load_review(root / name, result_ids=saved_ids[name])
                if any(record["context"]["paper_id"] != f"s2023.{paper}"
                       for record in manifest["records"]):
                    raise ValueError("A question is assigned to the wrong final paper pack")
                staged.write(f"\n\n# {paper} — {name}\n\n")
                staged.write(render_review_markdown(manifest, results))
        staged.seek(0)
        with output.open("x", encoding="utf-8") as destination:
            while chunk := staged.read(1024 * 1024):
                destination.write(chunk)
    return status
