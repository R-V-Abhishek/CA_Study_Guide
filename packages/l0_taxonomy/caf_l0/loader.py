"""L0 Reference & Taxonomy YAML loader."""

import hashlib
from pathlib import Path
from typing import Any
import yaml
from rich.console import Console
from rich.table import Table
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.logging import get_logger
from caf_db.engine import get_session_factory
from caf_db.models.ref import Attempt, DocType, Instrument, LawBoundary, Paper, Scheme, TaxonomyVersion

logger = get_logger("taxonomy.loader")
console = Console()


def compute_yaml_hash(taxonomy_dir: Path) -> str:
    hasher = hashlib.sha256()
    for file in sorted(taxonomy_dir.glob("**/*.yaml")):
        hasher.update(str(file.relative_to(taxonomy_dir)).encode())
        hasher.update(file.read_bytes())
    return hasher.hexdigest()


class TaxonomyLoader:
    def __init__(self, taxonomy_dir: Path = Path("taxonomy")) -> None:
        self.taxonomy_dir = taxonomy_dir
        self.registry_dir = taxonomy_dir / "registry"

    def load_registry_yaml(self, filename: str) -> list[dict[str, Any]]:
        path = self.registry_dir / filename
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []

    def plan(self) -> dict[str, Any]:
        """Inspect YAML and DB, producing a loading plan."""
        schemes = self.load_registry_yaml("schemes.yaml")
        attempts = self.load_registry_yaml("attempts.yaml")
        papers = self.load_registry_yaml("papers.yaml")
        doc_types = self.load_registry_yaml("doc_types.yaml")
        instruments = self.load_registry_yaml("instruments.yaml")
        law_boundaries = self.load_registry_yaml("law_boundaries.yaml")

        return {
            "schemes": schemes,
            "attempts": attempts,
            "papers": papers,
            "doc_types": doc_types,
            "instruments": instruments,
            "law_boundaries": law_boundaries,
            "yaml_hash": compute_yaml_hash(self.taxonomy_dir),
        }

    def print_plan(self, plan: dict[str, Any]) -> None:
        table = Table(title="Taxonomy Load Plan")
        table.add_column("Registry Entity", style="cyan")
        table.add_column("Count", style="green")

        for key in ["schemes", "attempts", "papers", "doc_types", "instruments", "law_boundaries"]:
            table.add_row(key, str(len(plan.get(key, []))))
        table.add_row("YAML Hash", plan.get("yaml_hash", "")[:12])
        console.print(table)

    def apply(self, session: Session, plan: dict[str, Any]) -> int:
        """Apply plan to database in a single transaction."""
        yaml_hash = plan["yaml_hash"]

        # 1. Insert taxonomy_version
        version = TaxonomyVersion(yaml_hash=yaml_hash, notes="Registry sync")
        session.add(version)
        session.flush()

        # 2. Schemes
        for item in plan["schemes"]:
            existing = session.get(Scheme, item["id"])
            if not existing:
                session.add(Scheme(id=item["id"], name=item["name"], notes=item.get("notes")))
            else:
                existing.name = item["name"]
                existing.notes = item.get("notes")

        # 3. Attempts
        for item in plan["attempts"]:
            existing = session.get(Attempt, item["id"])
            if not existing:
                session.add(
                    Attempt(
                        id=item["id"],
                        exam_year=item["exam_year"],
                        exam_month=item["exam_month"],
                        label=item["label"],
                        verified=item.get("verified", False),
                    )
                )
            else:
                existing.label = item["label"]
                existing.verified = item.get("verified", False)

        # 4. Papers
        for item in plan["papers"]:
            existing = session.get(Paper, item["id"])
            if not existing:
                session.add(
                    Paper(
                        id=item["id"],
                        scheme_id=item["scheme_id"],
                        code=item["code"],
                        name=item["name"],
                        group_no=item.get("group_no"),
                        max_marks=item.get("max_marks", 100),
                        is_current=item.get("is_current", False),
                    )
                )
            else:
                existing.name = item["name"]
                existing.group_no = item.get("group_no")
                existing.is_current = item.get("is_current", False)

        # 5. Doc Types
        for item in plan["doc_types"]:
            existing = session.get(DocType, item["id"])
            if not existing:
                session.add(
                    DocType(
                        id=item["id"],
                        signal_class=item["signal_class"],
                        has_questions=item["has_questions"],
                        has_answers=item["has_answers"],
                        description=item.get("description"),
                    )
                )

        # 6. Instruments
        for item in plan["instruments"]:
            existing = session.get(Instrument, item["id"])
            if not existing:
                session.add(
                    Instrument(
                        id=item["id"],
                        name=item["name"],
                        paper_codes=item.get("paper_codes", []),
                    )
                )

        # 7. Law Boundaries
        for item in plan["law_boundaries"]:
            existing = session.get(LawBoundary, item["id"])
            if not existing:
                session.add(
                    LawBoundary(
                        id=item["id"],
                        paper_code=item["paper_code"],
                        instrument_id=item.get("instrument_id"),
                        first_applicable_attempt=item.get("first_applicable_attempt"),
                        scope_node_ids=item.get("scope_node_ids"),
                        policy=item["policy"],
                        description=item.get("description"),
                    )
                )

        session.commit()
        return version.id
