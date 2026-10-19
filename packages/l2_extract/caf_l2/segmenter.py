"""Deterministic document segmenter building unit hierarchy."""

from dataclasses import dataclass, field
import hashlib
import re
from caf_l2.blocks import LineBlock
from caf_l2.profiles import ExtractionProfile, PatternRule, ProfileNotFoundError


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
    content_digest: str = ""
    document_role: str = "mixed"
    parse_confidence: str = "high"
    validation_flags: list[str] = field(default_factory=list)

    @property
    def question_text(self) -> str:
        return "\n".join(self.question_lines).strip()

    @property
    def answer_text(self) -> str:
        return "\n".join(self.answer_lines).strip()


def compute_fingerprint(doc_sha256: str, label_path: str, question_text: str) -> str:
    """Digest complete normalized content and scoped identity (legacy 40-char storage)."""
    norm = re.sub(r"\s+", " ", question_text).strip()
    return hashlib.sha1(f"{doc_sha256}|{label_path}|{norm}".encode("utf-8")).hexdigest()


def attemptable_marks(unit: ParsedUnit) -> int:
    """Count leaves once and collapse OR siblings to one attemptable alternative."""
    if not unit.children:
        return unit.marks or 0
    groups: dict[str, list[int]] = {}
    for child in unit.children:
        key = child.or_group or child.label_path
        groups.setdefault(key, []).append(attemptable_marks(child))
    return sum(max(values) for values in groups.values())


def match_rules(rules: list[PatternRule], line: LineBlock) -> re.Match[str] | None:
    """Return match if line matches any pattern in rules, respecting require_bold."""
    for r in rules:
        if r.require_bold and not line.bold:
            continue
        if r.min_x is not None and line.bbox[0] < r.min_x:
            continue
        if r.max_x is not None and line.bbox[0] > r.max_x:
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
        """Maintain separate answer state, merging only explicit answer anchors by scope."""
        supported_sources = self.profile.raw_data.get("supported_source_hashes")
        if supported_sources and self.doc_sha256 not in supported_sources:
            raise ProfileNotFoundError(f"unsupported_profile: {self.profile.id} has no authentic layout evidence for {self.doc_sha256}")
        self.units = []
        self.compulsory_questions = set()
        self.optional_pick = None
        self._parse_choice_rules(lines)
        index: dict[str, ParsedUnit] = {}
        current: dict[str, ParsedUnit | None] = dict.fromkeys(["case_stem", "question", "part", "subpart", "mcq"])
        order = list(current)
        region = "answer" if self.profile.document_role == "answers" else "question"
        answer_section = self.profile.mode == "answers_only"
        scope = ""
        paper_scope = ""
        test_scope = ""
        pending_or: str | None = None
        or_counter = 0
        in_key = False
        content_started = not self.profile.patterns.get("content_start")
        descriptive = False
        mcq_enabled = not self.profile.patterns.get("mcq_section_start")
        last_target: ParsedUnit | None = None

        def deepest() -> ParsedUnit | None:
            return next((current[k] for k in reversed(order) if current[k] is not None), None)

        for line in lines:
            if any((region.get("page") is None or region["page"] == line.page) and region["bbox"][0] <= line.bbox[0] and region["bbox"][1] <= line.bbox[1] and region["bbox"][2] >= line.bbox[2] and region["bbox"][3] >= line.bbox[3] for region in self.profile.raw_data.get("excluded_regions", [])):
                continue
            if match_rules(self.profile.patterns.get("content_end", []), line):
                break
            if not content_started:
                if match_rules(self.profile.patterns.get("content_start", []), line):
                    content_started = True
                else:
                    continue
            collection_answer = match_rules(self.profile.patterns.get("collection_answer_start", []), line)
            collection = collection_answer or match_rules(self.profile.patterns.get("collection_start", []), line)
            if collection:
                test_scope = f"T{collection.group('n')}"
                scope = ".".join(part for part in [paper_scope, test_scope] if part)
                region = "answer" if collection_answer else "question"
                answer_section = bool(collection_answer)
                descriptive = False
                mcq_enabled = False
                in_key = False
                current = dict.fromkeys(order)
                continue
            line.numbering_scope = scope
            if match_rules(self.profile.patterns.get("descriptive_start", []), line):
                descriptive = True
                in_key = False
                current["mcq"] = None
                continue
            if match_rules(self.profile.patterns.get("mcq_section_start", []), line):
                mcq_enabled = True
                descriptive = False
                continue
            if region == "question" and match_rules(self.profile.patterns.get("case_end", []), line):
                current = dict.fromkeys(order)
                descriptive = True
                continue
            key_title = match_rules(self.profile.patterns.get("mcq_key_table_title", []), line)
            if key_title:
                in_key = True
            key_row = match_rules(self.profile.patterns.get("mcq_key_row", []), line)
            key_end_question_rules = self.profile.patterns.get("answer_question_start", self.profile.patterns.get("question_start", []))
            if in_key and not self.profile.raw_data.get("key_table_ends_at_section") and not key_row and (match_rules(self.profile.patterns.get("case_scenario_start", []), line) or match_rules(key_end_question_rules, line)) and not key_title:
                in_key = False
            if in_key:
                target = deepest() or last_target
                if target:
                    line.region = "answer_key"
                    target.line_blocks.append(line)
                continue
            paper = match_rules(self.profile.patterns.get("paper_start", []), line)
            section = match_rules(self.profile.patterns.get("section_start", []), line)
            if paper or section:
                m = paper or section
                prefix = "P" if paper else "S"
                if paper:
                    paper_scope = f"P{m.group('n')}"
                    scope = ".".join(part for part in [paper_scope, test_scope] if part)
                else:
                    scope = ".".join(part for part in [paper_scope, test_scope, f"{prefix}{m.group('n')}"] if part)
                current = dict.fromkeys(order)
                continue
            answer = match_rules(self.profile.patterns.get("answer_start", []), line)
            if answer:
                region = "answer"
                if self.profile.mode == "sectioned" or re.search(r"suggested\s+answers|^answers\s*$", line.text, re.I):
                    answer_section = True
                    preserved_case = current["case_stem"] if self.profile.raw_data.get("answers_preserve_case") else None
                    current = dict.fromkeys(order)
                    current["case_stem"] = preserved_case
                # Named answer anchors establish the root without guessing question text.
                named = re.search(r"(?:question|answer)\s*(?:no\.?)?\s*(\d+)", line.text, re.I)
                if named:
                    path = f"{scope + '.' if scope else ''}Q{named.group(1)}"
                    if path not in index and self.profile.document_role == "answers":
                        unit = ParsedUnit(label_path=path, display_label=f"Q{named.group(1)}", kind="question", page_start=line.page, page_end=line.page, block_start=line.block_id, block_end=line.block_id, document_role="answers")
                        index[path] = unit
                        self.units.append(unit)
                    current["question"] = index.get(path)
                    current["part"] = current["subpart"] = current["mcq"] = None
                continue
            if match_rules(self.profile.patterns.get("or_separator", []), line):
                previous = deepest()
                if previous:
                    or_counter += 1
                    pending_or = previous.or_group or f"{previous.parent_label_path or 'root'}.or{or_counter}"
                    previous.or_group = pending_or
                    line.region = region
                    previous.line_blocks.append(line)
                continue

            matches = {kind: match_rules(self.profile.patterns.get("answer_question_start" if kind == "question" and region == "answer" and "answer_question_start" in self.profile.patterns else rule, []), line) for kind, rule in (
                ("case_stem", "case_scenario_start"), ("question", "question_start"),
                ("part", "part_start"), ("subpart", "subpart_start"), ("mcq", "mcq_start"))}
            if region == "answer" and self.profile.raw_data.get("answer_new_parts_are_text"):
                for part_kind, group in [("part", "p"), ("subpart", "s")]:
                    part_match = matches[part_kind]
                    parent = (current["part"] if part_kind == "subpart" else None) or current["question"] or current["case_stem"]
                    if part_match and parent and f"{parent.label_path}.{part_match.group(group).lower()}" not in index:
                        matches[part_kind] = None
            option = match_rules(self.profile.patterns.get("mcq_option", []), line) if current["mcq"] else None
            if option:
                target = current["mcq"]
                if region == "answer":
                    if target.mcq_correct_option is None:
                        target.mcq_correct_option = option.group("o").upper()
                else:
                    target.mcq_options.append(line.text)
                kind = None
            else:
                # A case-scoped numerical item is an MCQ; options precede part anchors.
                kinds = ["case_stem", "mcq", "question", "subpart", "part"] if current["case_stem"] and mcq_enabled and not descriptive and (not answer_section or self.profile.raw_data.get("answers_preserve_case")) else ["case_stem", "question", "subpart", "part"]
                if (current["case_stem"] and not mcq_enabled and not descriptive) or (self.profile.raw_data.get("questions_require_section") and not current["case_stem"] and not descriptive):
                    kinds = ["case_stem"]
                if current["mcq"]:
                    kinds = [k for k in kinds if k not in {"part", "subpart"}]
                kind = next((k for k in kinds if matches[k]), None)
            if kind:
                if kind == "case_stem" and self.profile.document_role != "answers":
                    region = "question"
                    answer_section = False
                    descriptive = False
                    mcq_enabled = not self.profile.patterns.get("mcq_section_start")
                m = matches[kind]
                parent = None
                if kind == "question":
                    parent = current["case_stem"] if not self.profile.patterns.get("case_end") else None
                    token = f"Q{m.group('n')}"
                elif kind == "case_stem":
                    token = f"CS{m.group('n')}"
                elif kind == "mcq":
                    parent = current["case_stem"]
                    token = f"M{m.group('n')}"
                elif kind == "part":
                    parent = current["question"] or current["case_stem"]
                    token = m.group('p').lower()
                else:
                    parent = current["part"] or current["question"] or current["case_stem"]
                    token = m.group('s').lower()
                path = f"{parent.label_path}.{token}" if parent else f"{scope + '.' if scope else ''}{token}"
                # In mixed interleaved papers a new part starts question text; answer parts
                # reuse an existing node. Sectioned/answer-only papers stay in answer state.
                if not answer_section and self.profile.document_role != "answers":
                    if kind in {"question", "case_stem", "mcq"} or path not in index:
                        region = "question"
                if region == "answer" and path in index and self.profile.document_role != "answers":
                    target = index[path]
                else:
                    original_path = path
                    duplicate = 1
                    while path in index:
                        duplicate += 1
                        path = f"{original_path}.alt{duplicate}" if pending_or else f"{original_path}.repeat{duplicate}"
                    target = ParsedUnit(label_path=path, display_label=token, kind=kind,
                        page_start=line.page, page_end=line.page, block_start=line.block_id,
                        block_end=line.block_id, parent_label_path=parent.label_path if parent else None,
                        document_role=self.profile.document_role, or_group=pending_or)
                    if duplicate > 1 and not pending_or:
                        target.validation_flags.append("AMBIGUOUS_REPEATED_LABEL")
                    if kind == "question":
                        target.choice_role = "compulsory" if token in self.compulsory_questions else ("optional" if self.compulsory_questions or self.optional_pick else "unknown")
                    if kind == "mcq":
                        target.marks = self.profile.defaults.mcq_marks
                        target.marks_source = "mcq_default"
                    index[path] = target
                    (parent.children if parent else self.units).append(target)
                pending_or = None
                pos = order.index(kind)
                for deeper in order[pos + 1:]:
                    current[deeper] = None
                current[kind] = target
            else:
                target = deepest()
            if target is None:
                continue
            last_target = target
            line.region = region
            target.line_blocks.append(line)
            target.page_end = max(target.page_end, line.page)
            target.block_end = line.block_id
            marks = match_rules(self.profile.patterns.get("marks", []), line)
            if marks and target.marks is None:
                target.marks = int(marks.group("m"))
                target.marks_source = "explicit"
            if target.kind == "mcq" and region == "question" and target.mcq_options and not option:
                target.mcq_options[-1] += "\n" + (line.raw_text or line.text)
            # Preserve marks and anchors verbatim; normalized text remains searchable.
            (target.answer_lines if region == "answer" else target.question_lines).append(line.raw_text or line.text)
        self._post_process(self.units)
        return self.units

    def _parse_choice_rules(self, lines: list[LineBlock]) -> None:
        """Scan introductory pages for paper choice rules."""
        intro_text = " ".join(l.text for l in lines if l.page <= 2 or self.profile.raw_data.get("instructions_any_page"))
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
                        else NUMBER_WORDS.get(k_str.lower())
                    )

    def _post_process(self, units: list[ParsedUnit]) -> None:
        """Recursively roll up marks, set gradable flags, and compute fingerprints."""
        for u in units:
            if u.children:
                self._post_process(u.children)
                if u.kind == "case_stem" and self.profile.raw_data.get("mcqs_compulsory") and all(child.kind == "mcq" for child in u.children):
                    u.choice_role = "compulsory"
                # Expand parent boundaries
                u.page_start = min(u.page_start, u.children[0].page_start)
                u.page_end = max(u.page_end, u.children[-1].page_end)
                # Keep the root stem block; it precedes the children.
                u.block_end = u.children[-1].block_end

                child_marks = [
                    c.marks for c in u.children if c.marks is not None
                ]
                if len(child_marks) == len(u.children) and len(u.children) > 0:
                    u.marks = attemptable_marks(u)
                    u.marks_source = "summed"
                    u.is_gradable = False
                elif u.marks is not None:
                    u.is_gradable = False
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

            u.content_digest = hashlib.sha256((u.question_text + "\n" + u.answer_text).encode("utf-8")).hexdigest()
            u.fingerprint = compute_fingerprint(
                self.doc_sha256, u.label_path, u.question_text + "\n" + u.answer_text
            )
