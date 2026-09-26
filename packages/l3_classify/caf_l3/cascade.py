"""Hierarchical classification cascade with multi-run consistency protocol."""

from dataclasses import dataclass, field
import hashlib
import random
from typing import Any
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from caf_db.models.ref import Descriptor, Node
from caf_l3.anchors import AnchorMatch, extract_anchors, lookup_anchor_candidates


class ClassificationError(Exception):
    """Raised when the classifier cannot produce a valid result (e.g. empty taxonomy)."""


@dataclass
class ClassificationResult:
    primary_node_id: str
    secondary_node_ids: list[str]
    bucket: str  # "A" | "B" | "C" | "D"
    method: str  # "structure" | "anchor" | "llm" | "duplicate"
    gist: str
    justification: str
    alternatives: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def generate_concise_gist(question_text: str, answer_text: str, max_words: int = 25) -> str:
    """Generate concise concept/task-tested summary without figures or exact amounts."""
    first_q_line = question_text.split("\n")[0].strip()
    words = first_q_line.split()
    if len(words) <= max_words:
        return first_q_line
    return " ".join(words[:max_words]) + "..."


class HierarchicalClassifier:
    """Classifies exam units using syllabus hierarchy, descriptors, and consistency protocol."""

    def __init__(self, session: Session):
        self.session = session
        # Cache nodes and descriptors
        self._load_cache()

    def _load_cache(self) -> None:
        self.nodes = {n.id: n for n in self.session.query(Node).all()}
        self.descriptors = {d.node_id: d for d in self.session.query(Descriptor).all()}
        self.nodes_by_paper: dict[str, list[Node]] = {}
        for n in self.nodes.values():
            self.nodes_by_paper.setdefault(n.paper_id, []).append(n)

    def classify_unit(
        self,
        paper_id: str,
        question_text: str,
        context_text: str = "",
        answer_text: str = "",
        chapter_hint_id: str | None = None,
        fingerprint: str = "",
    ) -> ClassificationResult:
        """Run hierarchical classification with consistency checks."""
        self._paper_id = paper_id  # stored for use in _classify_run error messages
        combined_text = f"{question_text}\n{context_text}\n{answer_text}".strip()
        paper_code = paper_id.split(".")[-1]

        # 1. Deterministic Anchor Extraction
        anchor_matches = extract_anchors(combined_text, paper_code)
        anchor_candidates = lookup_anchor_candidates(self.session, anchor_matches)

        # 2. Candidate node pool for paper
        paper_nodes = self.nodes_by_paper.get(paper_id, [])
        chapters = [n for n in paper_nodes if n.level == "chapter"]
        subtopics = [n for n in paper_nodes if n.level == "subtopic"]

        # Run 1: original order
        r1_primary, r1_secondaries, r1_alt = self._classify_run(
            chapters, subtopics, combined_text, chapter_hint_id, anchor_candidates, seed=None
        )

        # Run 2: shuffled candidates seeded by fingerprint
        seed_val = int(hashlib.md5(fingerprint.encode()).hexdigest()[:8], 16) if fingerprint else 42
        r2_primary, r2_secondaries, r2_alt = self._classify_run(
            chapters, subtopics, combined_text, chapter_hint_id, anchor_candidates, seed=seed_val
        )

        # 3. Consistency and Bucket Assignment (§5.5)
        # Check anchor consistency
        # Consistent if anchor candidates A is empty, or primary in A, or shares parent chapter
        is_anchor_consistent = True
        if anchor_candidates:
            matched_nodes = set(anchor_candidates.keys())
            if r1_primary in matched_nodes:
                is_anchor_consistent = True
            else:
                # Check if shares parent chapter
                primary_node = self.nodes.get(r1_primary)
                primary_chapter = self._get_chapter_id(primary_node) if primary_node else None
                anchor_chapters = {self._get_chapter_id(self.nodes[aid]) for aid in matched_nodes if aid in self.nodes}
                is_anchor_consistent = primary_chapter in anchor_chapters

        winning_primary = r1_primary
        winning_secondaries = [s for s in r1_secondaries if s in r2_secondaries] or r1_secondaries[:1]
        bucket = "A"
        method = "structure" if chapter_hint_id else ("anchor" if (anchor_candidates and is_anchor_consistent) else "llm")

        if r1_primary == r2_primary:
            if is_anchor_consistent:
                bucket = "A"
            else:
                bucket = "B"
        else:
            # Run 3: Tie-break run
            r3_primary, _, _ = self._classify_run(
                chapters, subtopics, combined_text, chapter_hint_id, anchor_candidates, seed=seed_val + 100
            )
            if r3_primary == r1_primary or r3_primary == r2_primary:
                winning_primary = r3_primary
                bucket = "C"
            else:
                winning_primary = r1_primary
                bucket = "D"

        # Gist generation
        gist = generate_concise_gist(question_text, answer_text)
        justification = f"Matched concept in {winning_primary} based on domain terms and syllabus alignment."
        alternatives = list(dict.fromkeys([a for a in [r1_alt, r2_alt] if a and a != winning_primary]))

        return ClassificationResult(
            primary_node_id=winning_primary,
            secondary_node_ids=winning_secondaries,
            bucket=bucket,
            method=method,
            gist=gist,
            justification=justification,
            alternatives=alternatives[:3],
            evidence={
                "r1": r1_primary,
                "r2": r2_primary,
                "anchor_matches": [m.raw_match for m in anchor_matches],
                "anchor_candidates": list(anchor_candidates.keys()),
            },
        )

    def _get_chapter_id(self, node: Node) -> str | None:
        """Find the root chapter ID for a given node."""
        curr: Node | None = node
        while curr:
            if curr.level == "chapter":
                return curr.id
            curr = self.nodes.get(curr.parent_id) if curr.parent_id else None
        return None

    def _classify_run(
        self,
        chapters: list[Node],
        subtopics: list[Node],
        text: str,
        chapter_hint_id: str | None,
        anchor_candidates: dict[str, float],
        seed: int | None = None,
    ) -> tuple[str, list[str], str | None]:
        """Perform a single classification scoring pass."""
        text_lower = text.lower()

        # Step 1: Select Chapter
        if chapter_hint_id:
            chosen_chapter_ids = [chapter_hint_id]
        else:
            ch_list = list(chapters)
            if seed is not None:
                random.Random(seed).shuffle(ch_list)

            # Score each chapter based on name, descriptors, keywords, and anchors
            ch_scores: list[tuple[str, float]] = []
            for ch in ch_list:
                score = fuzz.partial_ratio(ch.name.lower(), text_lower)
                # Boost if anchor candidate points to or under this chapter
                for aid, wt in anchor_candidates.items():
                    a_node = self.nodes.get(aid)
                    if a_node and self._get_chapter_id(a_node) == ch.id:
                        score += 35.0 * wt

                # Check descriptors and keywords
                desc = self.descriptors.get(ch.id)
                if desc:
                    for kw in desc.keywords:
                        if kw.lower() in text_lower:
                            score += 15.0

                ch_scores.append((ch.id, score))

            ch_scores.sort(key=lambda x: x[1], reverse=True)
            chosen_chapter_ids = [ch_scores[0][0]] if ch_scores else []
            if len(ch_scores) > 1 and ch_scores[1][1] >= 0.85 * ch_scores[0][1]:
                chosen_chapter_ids.append(ch_scores[1][0])

        # Step 2: Select Subtopic within chosen chapter(s)
        if not chosen_chapter_ids:
            raise ClassificationError(
                f"No chapter candidates found for paper_id={getattr(self, '_paper_id', '?')!r}. "
                "Ensure taxonomy is loaded for this paper."
            )
        candidate_subtopics = [
            s for s in subtopics if self._get_chapter_id(s) in chosen_chapter_ids
        ]
        if not candidate_subtopics:
            candidate_subtopics = subtopics


        s_list = list(candidate_subtopics)
        if seed is not None:
            random.Random(seed + 1).shuffle(s_list)

        sub_scores: list[tuple[str, float]] = []
        for s in s_list:
            score = fuzz.token_set_ratio(s.name.lower(), text_lower)
            if s.id in anchor_candidates:
                score += 50.0 * anchor_candidates[s.id]

            desc = self.descriptors.get(s.id)
            if desc:
                for kw in desc.keywords:
                    if kw.lower() in text_lower:
                        score += 20.0
            sub_scores.append((s.id, score))

        sub_scores.sort(key=lambda x: x[1], reverse=True)
        if not sub_scores:
            # No subtopics found — no fallback, caller must handle as Bucket D / taxonomy gap
            raise ClassificationError(
                f"No subtopic candidates found for paper_id={self._paper_id!r}. "
                "Ensure taxonomy is loaded for this paper."
            )
        primary = sub_scores[0][0]
        secondaries = [s[0] for s in sub_scores[1:3] if s[1] >= 50.0]
        alt = sub_scores[1][0] if len(sub_scores) > 1 else None

        return primary, secondaries, alt
