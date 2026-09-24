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
from caf_l0.ids import is_valid_node_id
from caf_db.models.ref import (
    Attempt,
    DocType,
    Instrument,
    LawBoundary,
    Node,
    Paper,
    Scheme,
    TaxonomyVersion,
    WeightageMember,
    WeightageSection,
)

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
        self.papers_dir = taxonomy_dir / "papers"
        self.weightage_dir = taxonomy_dir / "weightage"

    def load_registry_yaml(self, filename: str) -> list[dict[str, Any]]:
        path = self.registry_dir / filename
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []

    def load_papers_yaml(self) -> dict[str, dict[str, Any]]:
        papers = {}
        if self.papers_dir.exists():
            for p in sorted(self.papers_dir.glob("*.yaml")):
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "paper" in data:
                        papers[p.stem] = data
        return papers

    def load_weightages_yaml(self) -> dict[str, dict[str, Any]]:
        weightages = {}
        if self.weightage_dir.exists():
            for w in sorted(self.weightage_dir.glob("*.yaml")):
                with open(w, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "paper" in data:
                        weightages[w.stem] = data
        return weightages

    def validate(
        self,
        papers: dict[str, dict[str, Any]],
        weightages: dict[str, dict[str, Any]],
    ) -> list[str]:
        """Validate taxonomy constraints prior to write."""
        errors: list[str] = []
        seen_node_ids: set[str] = set()
        chapter_ids_by_paper: dict[str, set[str]] = {}

        for code, pdata in papers.items():
            paper_id = pdata["paper"]
            ch_ids: set[str] = set()

            for c_idx, ch in enumerate(pdata.get("chapters", []), start=1):
                cid = ch["id"]
                if not is_valid_node_id(cid):
                    errors.append(f"Invalid chapter node ID format: {cid}")
                if cid in seen_node_ids:
                    errors.append(f"Duplicate node ID: {cid}")
                seen_node_ids.add(cid)
                ch_ids.add(cid)

                seen_t_seq: set[int] = set()
                for t_idx, top in enumerate(ch.get("topics", []), start=1):
                    tid = top["id"]
                    if not is_valid_node_id(tid):
                        errors.append(f"Invalid topic node ID format: {tid}")
                    if tid in seen_node_ids:
                        errors.append(f"Duplicate node ID: {tid}")
                    seen_node_ids.add(tid)

                    t_seq = top.get("seq", t_idx)
                    if t_seq in seen_t_seq:
                        errors.append(f"Duplicate topic seq {t_seq} in chapter {cid}")
                    seen_t_seq.add(t_seq)

                    seen_s_seq: set[int] = set()
                    for s_idx, sub in enumerate(top.get("subtopics", []), start=1):
                        sid = sub["id"]
                        if not is_valid_node_id(sid):
                            errors.append(f"Invalid subtopic node ID format: {sid}")
                        if sid in seen_node_ids:
                            errors.append(f"Duplicate node ID: {sid}")
                        seen_node_ids.add(sid)

                        s_seq = sub.get("seq", s_idx)
                        if s_seq in seen_s_seq:
                            errors.append(f"Duplicate subtopic seq {s_seq} in topic {tid}")
                        seen_s_seq.add(s_seq)

            chapter_ids_by_paper[code] = ch_ids

        # Validate weightages
        for code, wdata in weightages.items():
            ch_ids = chapter_ids_by_paper.get(code, set())
            assigned_chapters: set[str] = set()
            midpoint_sum = 0.0

            for sec in wdata.get("sections", []):
                min_p = sec["min_pct"]
                max_p = sec["max_pct"]
                if min_p > max_p:
                    errors.append(f"Weightage section {sec['id']} has min_pct > max_pct")
                midpoint_sum += (min_p + max_p) / 2.0

                for ch_id in sec.get("chapter_ids", []):
                    if ch_id not in ch_ids:
                        errors.append(f"Weightage section {sec['id']} references unknown chapter {ch_id}")
                    if ch_id in assigned_chapters:
                        errors.append(f"Chapter {ch_id} assigned to multiple weightage sections")
                    assigned_chapters.add(ch_id)

            unassigned = ch_ids - assigned_chapters
            if unassigned:
                errors.append(f"Paper {code} has chapters unassigned to any weightage section: {unassigned}")

            if not (90.0 <= midpoint_sum <= 110.0):
                errors.append(
                    f"Paper {code} weightage midpoint sum {midpoint_sum:.1f}% outside 90-110% tolerance"
                )

        return errors

    def plan(self) -> dict[str, Any]:
        """Inspect YAML files and generate structured plan."""
        schemes = self.load_registry_yaml("schemes.yaml")
        attempts = self.load_registry_yaml("attempts.yaml")
        papers_reg = self.load_registry_yaml("papers.yaml")
        doc_types = self.load_registry_yaml("doc_types.yaml")
        instruments = self.load_registry_yaml("instruments.yaml")
        law_boundaries = self.load_registry_yaml("law_boundaries.yaml")
        paper_trees = self.load_papers_yaml()
        weightages = self.load_weightages_yaml()

        errors = self.validate(paper_trees, weightages)
        if errors:
            raise ValueError(f"Taxonomy validation failed with {len(errors)} error(s):\n" + "\n".join(f" - {e}" for e in errors))

        # Count nodes
        total_chapters = 0
        total_topics = 0
        total_subtopics = 0
        for pdata in paper_trees.values():
            for ch in pdata.get("chapters", []):
                total_chapters += 1
                for top in ch.get("topics", []):
                    total_topics += 1
                    total_subtopics += len(top.get("subtopics", []))

        return {
            "schemes": schemes,
            "attempts": attempts,
            "papers_registry": papers_reg,
            "doc_types": doc_types,
            "instruments": instruments,
            "law_boundaries": law_boundaries,
            "paper_trees": paper_trees,
            "weightages": weightages,
            "total_chapters": total_chapters,
            "total_topics": total_topics,
            "total_subtopics": total_subtopics,
            "yaml_hash": compute_yaml_hash(self.taxonomy_dir),
        }

    def print_plan(self, plan: dict[str, Any]) -> None:
        table = Table(title="Taxonomy Load Plan")
        table.add_column("Registry Entity", style="cyan")
        table.add_column("Count", style="green")

        for key in ["schemes", "attempts", "papers_registry", "doc_types", "instruments", "law_boundaries"]:
            table.add_row(key, str(len(plan.get(key, []))))

        table.add_row("papers_trees", str(len(plan.get("paper_trees", {}))))
        table.add_row("total_chapters", str(plan.get("total_chapters", 0)))
        table.add_row("total_topics", str(plan.get("total_topics", 0)))
        table.add_row("total_subtopics", str(plan.get("total_subtopics", 0)))
        table.add_row("weightages", str(len(plan.get("weightages", {}))))
        table.add_row("YAML Hash", plan.get("yaml_hash", "")[:12])
        console.print(table)

    def apply(self, session: Session, plan: dict[str, Any]) -> int:
        """Apply plan to database in a single transaction."""
        yaml_hash = plan["yaml_hash"]

        # 1. Insert taxonomy_version
        version = TaxonomyVersion(yaml_hash=yaml_hash, notes="Full taxonomy & tree sync")
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

        # 4. Papers Registry
        for item in plan["papers_registry"]:
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

        # 8. Load Paper Trees into ref.node
        for code, pdata in plan["paper_trees"].items():
            paper_id = pdata["paper"]

            for c_idx, ch in enumerate(pdata.get("chapters", []), start=1):
                cid = ch["id"]
                c_node = session.get(Node, cid)
                if not c_node:
                    session.add(
                        Node(
                            id=cid,
                            paper_id=paper_id,
                            parent_id=None,
                            level="chapter",
                            name=ch["name"],
                            seq=ch.get("seq", c_idx),
                            created_in=version.id,
                        )
                    )
                else:
                    c_node.name = ch["name"]
                    c_node.seq = ch.get("seq", c_idx)
                    c_node.updated_in = version.id

                for t_idx, top in enumerate(ch.get("topics", []), start=1):
                    tid = top["id"]
                    t_node = session.get(Node, tid)
                    if not t_node:
                        session.add(
                            Node(
                                id=tid,
                                paper_id=paper_id,
                                parent_id=cid,
                                level="topic",
                                name=top["name"],
                                seq=top.get("seq", t_idx),
                                created_in=version.id,
                            )
                        )
                    else:
                        t_node.name = top["name"]
                        t_node.seq = top.get("seq", t_idx)
                        t_node.updated_in = version.id

                    for s_idx, sub in enumerate(top.get("subtopics", []), start=1):
                        sid = sub["id"]
                        s_node = session.get(Node, sid)
                        if not s_node:
                            session.add(
                                Node(
                                id=sid,
                                paper_id=paper_id,
                                parent_id=tid,
                                level="subtopic",
                                name=sub["name"],
                                seq=sub.get("seq", s_idx),
                                created_in=version.id,
                            )
                        )
                        else:
                            s_node.name = sub["name"]
                            s_node.seq = sub.get("seq", s_idx)
                            s_node.updated_in = version.id

        # 9. Weightages into ref.weightage_section & member
        for code, wdata in plan["weightages"].items():
            paper_id = wdata["paper"]
            for sec in wdata.get("sections", []):
                sec_id = sec["id"]
                w_sec = session.get(WeightageSection, sec_id)
                if not w_sec:
                    w_sec = WeightageSection(
                        id=sec_id,
                        paper_id=paper_id,
                        name=sec["name"],
                        min_pct=sec["min_pct"],
                        max_pct=sec["max_pct"],
                    )
                    session.add(w_sec)
                else:
                    w_sec.name = sec["name"]
                    w_sec.min_pct = sec["min_pct"]
                    w_sec.max_pct = sec["max_pct"]

                session.flush()

                for ch_id in sec.get("chapter_ids", []):
                    mem = session.get(WeightageMember, (sec_id, ch_id))
                    if not mem:
                        session.add(WeightageMember(section_id=sec_id, chapter_id=ch_id))

        session.commit()
        return version.id
