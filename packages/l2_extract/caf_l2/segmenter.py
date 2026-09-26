"""Deterministic document segmenter building unit hierarchy."""

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any
from caf_l2.blocks import LineBlock
from caf_l2.profiles import ExtractionProfile, PatternRule


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}


@dataclass
class ParsedUnit:
    label_path: str
    display_label: str
    kind: str  # case_stem | question | part | subpart | mcq
    page_start: int
    page_end: int
    block_start: str
    block_end: str
    is_gradable: bool = False
    marks: int | None = None
    marks_source: str | None = None
    choice_role: str = "unknown"
    or_group: str | None = None
    question_lines: list[str] = field(default_factory=list)
    answer_lines: list[str] = field(default_factory=list)
    line_blocks: list[LineBlock] = field(default_factory=list)
    children: list["ParsedUnit"] = field(default_factory=list)
    parent_label_path: str | None = None
    mcq_options: list[str] = field(default_factory=list)
    mcq_correct_option: str | None = None
    fingerprint: str = ""
    parse_confidence: str = "high"
    validation_flags: list[str] = field(default_factory=list)

    @property
    def question_text(self) -> str:
        return "\n".join(self.question_lines).strip()

    @property
    def answer_text(self) -> str:
        return "\n".join(self.answer_lines).strip()


def compute_fingerprint(doc_sha256: str, label_path: str, question_text: str) -> str:
    """sha1(doc_sha256 + "|" + label_path + "|" + normalise(question_text)[:200])"""
    norm = re.sub(r"[^a-z0-9]", "", question_text.lower())[:200]
    return hashlib.sha1(f"{doc_sha256}|{label_path}|{norm}".encode("utf-8")).hexdigest()


def match_rules(rules: list[PatternRule], line: LineBlock) -> re.Match[str] | None:
    """Return match if line matches any pattern in rules, respecting require_bold."""
    for r in rules:
        if r.require_bold and not line.bold:
            continue
        m = r.pattern.search(line.text)
        if m:
            return m
    return None


class Segmenter:
    """Deterministic profile-driven segmenter."""

    def __init__(self, profile: ExtractionProfile, doc_sha256: str):
        self.profile = profile
        self.doc_sha256 = doc_sha256
        self.units: list[ParsedUnit] = []
        self.compulsory_questions: set[str] = set()
        self.optional_pick: int | None = None

    def segment(self, lines: list[LineBlock]) -> list[ParsedUnit]:
        """Segment block stream into unit tree."""
        if not lines:
            return []

        # 1. Parse instructions in the first 2 pages for choice rules
        self._parse_choice_rules(lines)

        # 2. Main line traversal state machine
        current_case: ParsedUnit | None = None
        current_question: ParsedUnit | None = None
        current_part: ParsedUnit | None = None
        current_subpart: ParsedUnit | None = None
        current_mcq: ParsedUnit | None = None

        current_region = "question"  # "question" | "answer"
        pending_or_group: str | None = None
        or_counter = 0

        for line in lines:
            # Check anchors in precedence order
            case_match = match_rules(
                self.profile.patterns.get("case_scenario_start", []), line
            )
            q_match = match_rules(
                self.profile.patterns.get("question_start", []), line
            )
            or_match = match_rules(
                self.profile.patterns.get("or_separator", []), line
            )
            ans_match = match_rules(
                self.profile.patterns.get("answer_start", []), line
            )
            part_match = match_rules(
                self.profile.patterns.get("part_start", []), line
            )
            subpart_match = match_rules(
                self.profile.patterns.get("subpart_start", []), line
            )
            mcq_match = (
                match_rules(self.profile.patterns.get("mcq_start", []), line)
                if current_case
                else None
            )
            opt_match = (
                match_rules(self.profile.patterns.get("mcq_option", []), line)
                if current_mcq
                else None
            )

            # Check marks in line
            marks_match = match_rules(self.profile.patterns.get("marks", []), line)
            clean_line_text = line.text
            extracted_marks: int | None = None
            if marks_match:
                extracted_marks = int(marks_match.group("m"))
                # Strip marks text from line content
                clean_line_text = re.sub(
                    marks_match.re.pattern, "", clean_line_text
                ).strip()

            if case_match:
                c_num = case_match.group("n")
                label_path = f"CS{c_num}"
                current_case = ParsedUnit(
                    label_path=label_path,
                    display_label=f"Case Scenario {c_num}",
                    kind="case_stem",
                    page_start=line.page,
                    page_end=line.page,
                    block_start=line.block_id,
                    block_end=line.block_id,
                    is_gradable=False,
                )
                self.units.append(current_case)
                current_question = None
                current_part = None
                current_subpart = None
                current_mcq = None
                current_region = "question"

            elif q_match:
                q_num = q_match.group("n")
                if current_case:
                    label_path = f"{current_case.label_path}.Q{q_num}"
                else:
                    label_path = f"Q{q_num}"
                choice = "compulsory" if label_path in self.compulsory_questions else (
                    "optional" if self.compulsory_questions or self.optional_pick else "unknown"
                )
                current_question = ParsedUnit(
                    label_path=label_path,
                    display_label=f"Question {q_num}",
                    kind="question",
                    page_start=line.page,
                    page_end=line.page,
                    block_start=line.block_id,
                    block_end=line.block_id,
                    parent_label_path=current_case.label_path if current_case else None,
                    choice_role=choice,
                    or_group=pending_or_group,
                )
                pending_or_group = None
                if current_case:
                    current_case.children.append(current_question)
                else:
                    self.units.append(current_question)
                current_part = None
                current_subpart = None
                current_mcq = None
                current_region = "question"

            elif or_match:
                # Next sibling unit gets or_group
                parent_prefix = (
                    current_part.label_path
                    if current_part
                    else (current_question.label_path if current_question else "root")
                )
                or_counter += 1
                pending_or_group = f"{parent_prefix}.or{or_counter}"
                continue

            elif part_match:
                p_label = part_match.group("p").lower()
                if current_question:
                    parent_path = current_question.label_path
                elif current_case:
                    parent_path = f"{current_case.label_path}.Q1"
                else:
                    parent_path = "Q1"
                label_path = f"{parent_path}.{p_label}"
                current_part = ParsedUnit(
                    label_path=label_path,
                    display_label=f"({p_label})",
                    kind="part",
                    page_start=line.page,
                    page_end=line.page,
                    block_start=line.block_id,
                    block_end=line.block_id,
                    parent_label_path=parent_path,
                    or_group=pending_or_group,
                )
                pending_or_group = None
                if current_question:
                    current_question.children.append(current_part)
                elif current_case:
                    current_case.children.append(current_part)
                else:
                    self.units.append(current_part)
                current_subpart = None
                current_mcq = None
                current_region = "question"

            elif subpart_match:
                s_label = subpart_match.group("s").lower()
                if current_part:
                    parent_path = current_part.label_path
                elif current_question:
                    parent_path = current_question.label_path
                elif current_case:
                    parent_path = f"{current_case.label_path}.Q1"
                else:
                    parent_path = "Q1"
                label_path = f"{parent_path}.{s_label}"
                current_subpart = ParsedUnit(
                    label_path=label_path,
                    display_label=f"({s_label})",
                    kind="subpart",
                    page_start=line.page,
                    page_end=line.page,
                    block_start=line.block_id,
                    block_end=line.block_id,
                    parent_label_path=parent_path,
                    or_group=pending_or_group,
                )
                pending_or_group = None
                if current_part:
                    current_part.children.append(current_subpart)
                elif current_question:
                    current_question.children.append(current_subpart)
                else:
                    self.units.append(current_subpart)
                current_mcq = None
                current_region = "question"

            elif mcq_match:
                m_num = mcq_match.group("n")
                parent_path = current_case.label_path if current_case else "CS1"
                label_path = f"{parent_path}.M{m_num}"
                current_mcq = ParsedUnit(
                    label_path=label_path,
                    display_label=f"MCQ {m_num}",
                    kind="mcq",
                    page_start=line.page,
                    page_end=line.page,
                    block_start=line.block_id,
                    block_end=line.block_id,
                    parent_label_path=parent_path,
                    is_gradable=True,
                    marks=self.profile.defaults.mcq_marks,
                    marks_source="mcq_default",
                )
                if current_case:
                    current_case.children.append(current_mcq)
                else:
                    self.units.append(current_mcq)
                current_region = "question"

            elif opt_match and current_mcq:
                current_mcq.mcq_options.append(line.text)

            elif ans_match:
                current_region = "answer"

            # Determine deepest open unit
            deepest = (
                current_mcq
                or current_subpart
                or current_part
                or current_question
                or current_case
            )

            if deepest:
                # Update boundary
                deepest.page_end = line.page
                deepest.block_end = line.block_id
                deepest.line_blocks.append(line)

                # Attach marks if available and not yet set
                if extracted_marks is not None and deepest.marks is None:
                    deepest.marks = extracted_marks
                    deepest.marks_source = "explicit"

                # Append text
                if clean_line_text:
                    if current_region == "question":
                        deepest.question_lines.append(clean_line_text)
                    else:
                        deepest.answer_lines.append(clean_line_text)

        # 3. Post-process unit tree: roll up marks, assign gradable status, fingerprints
        self._post_process(self.units)
        return self.units

    def _parse_choice_rules(self, lines: list[LineBlock]) -> None:
        """Scan introductory pages for paper choice rules."""
        intro_text = " ".join(l.text for l in lines if l.page <= 2)
        for cr in self.profile.choice_rules:
            m = cr.pattern.search(intro_text)
            if m:
                if cr.compulsory:
                    self.compulsory_questions.update(cr.compulsory)
                if cr.optional_pick:
                    k_str = m.groupdict().get("k", cr.optional_pick)
                    self.optional_pick = (
                        int(k_str)
                        if k_str.isdigit()
                        else NUMBER_WORDS.get(k_str.lower(), 4)
                    )

    def _post_process(self, units: list[ParsedUnit]) -> None:
        """Recursively roll up marks, set gradable flags, and compute fingerprints."""
        for u in units:
            if u.children:
                self._post_process(u.children)
                # Expand parent boundaries
                u.page_start = min(u.page_start, u.children[0].page_start)
                u.page_end = max(u.page_end, u.children[-1].page_end)
                u.block_start = u.children[0].block_start
                u.block_end = u.children[-1].block_end

                child_marks = [
                    c.marks for c in u.children if c.marks is not None
                ]
                if len(child_marks) == len(u.children) and len(u.children) > 0:
                    u.marks = sum(child_marks)
                    u.marks_source = "summed"
                    u.is_gradable = False
                elif u.marks is not None:
                    u.is_gradable = True
                else:
                    u.is_gradable = False
            else:
                if u.kind in ("part", "subpart", "mcq"):
                    u.is_gradable = True
                    if u.marks is None and u.kind == "mcq":
                        u.marks = self.profile.defaults.mcq_marks
                        u.marks_source = "mcq_default"
                elif u.kind == "question":
                    u.is_gradable = True
                elif u.kind == "case_stem":
                    u.is_gradable = False

            u.fingerprint = compute_fingerprint(
                self.doc_sha256, u.label_path, u.question_text
            )
