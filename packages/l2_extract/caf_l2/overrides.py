"""Document-level manual overrides loader and applier."""

from pathlib import Path
from typing import Any
import yaml
from caf_l2.pairing import flatten_units
from caf_l2.segmenter import ParsedUnit


class OverrideInvalidError(Exception):
    """Raised when an override produces validator errors."""
    pass


def load_override(overrides_dir: Path, doc_sha256: str) -> dict[str, Any] | None:
    """Load YAML override file if present for given document SHA-256."""
    override_path = overrides_dir / f"{doc_sha256}.yaml"
    if not override_path.is_file():
        return None

    with open(override_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_override(
    units: list[ParsedUnit], override_data: dict[str, Any]
) -> list[ParsedUnit]:
    """Apply patch or replace override to segmented units."""
    mode = override_data.get("mode", "patch")
    override_units = override_data.get("units", [])

    if mode == "replace":
        new_units: list[ParsedUnit] = []
        for ou in override_units:
            u = ParsedUnit(
                label_path=ou["label_path"],
                display_label=ou.get("display_label", ou["label_path"]),
                kind=ou.get("kind", "question"),
                page_start=ou.get("page_start", 1),
                page_end=ou.get("page_end", 1),
                block_start=ou.get("start", "p1-b1"),
                block_end=ou.get("end", "p1-b1"),
                marks=ou.get("marks"),
                marks_source="override" if ou.get("marks") is not None else None,
                is_gradable=ou.get("is_gradable", True),
                choice_role=ou.get("choice_role", "unknown"),
            )
            new_units.append(u)
        return new_units

    # Patch mode
    all_units = flatten_units(units)
    unit_map = {u.label_path: u for u in all_units}

    to_delete: set[str] = set()
    for ou in override_units:
        lp = ou.get("label_path")
        if not lp:
            continue

        if ou.get("delete"):
            to_delete.add(lp)
            continue

        if lp in unit_map:
            u = unit_map[lp]
            if "marks" in ou:
                u.marks = ou["marks"]
                u.marks_source = "override"
            if "start" in ou:
                u.block_start = ou["start"]
            if "end" in ou:
                u.block_end = ou["end"]
            if "choice_role" in ou:
                u.choice_role = ou["choice_role"]
            if "is_gradable" in ou:
                u.is_gradable = ou["is_gradable"]

    # Filter deleted units from root tree
    def prune(unit_list: list[ParsedUnit]) -> list[ParsedUnit]:
        filtered = []
        for u in unit_list:
            if u.label_path in to_delete:
                continue
            if u.children:
                u.children = prune(u.children)
            filtered.append(u)
        return filtered

    return prune(units)
