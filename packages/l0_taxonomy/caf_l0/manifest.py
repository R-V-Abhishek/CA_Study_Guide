"""Load the persisted draft and its separate review inventories."""

import json
from pathlib import Path


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    crosswalk = path.with_name("crosswalk.json")
    if crosswalk.exists():
        manifest["crosswalk"] = json.loads(crosswalk.read_text())
    questions = path.with_name("question_sources.json")
    if questions.exists():
        inventory = json.loads(questions.read_text())
        manifest["question_sources"] = inventory["records"]
        manifest["question_inventory_gaps"] = inventory["gaps"]
        manifest["question_inventory_audit"] = inventory["audit"]
    weightages = path.with_name("weightage_sources.json")
    if weightages.exists():
        manifest["weightage_sources"] = json.loads(weightages.read_text())["records"]
    existing_corpus = path.with_name("existing_corpus_inventory.json")
    if existing_corpus.exists():
        manifest["existing_corpus_inventory"] = json.loads(existing_corpus.read_text())
    return manifest
