"""Deterministic validation suite (V1–V7) for extracted units."""

from dataclasses import dataclass, field
import re
from typing import Any
from caf_l2.pairing import PairedAnswer, flatten_units
from caf_l2.profiles import ExtractionProfile
from caf_l2.segmenter import ParsedUnit


@dataclass
class ValidationIssue:
    code: str
    severity: str  # "error" | "warn"
    message: str
    unit_label: str | None = None


@dataclass
class ValidationResult:
    outcome: str  # "ok" | "ok_with_warnings" | "needs_review"
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warn" for i in self.issues)


class DocumentValidator:
    """Validates segmented unit tree against profiles and integrity rules."""

    def __init__(
        self,
        profile: ExtractionProfile,
        has_answers: bool = True,
        optional_pick: int | None = None,
    ):
        self.profile = profile
        self.has_answers = has_answers
        self.optional_pick = optional_pick

    def validate(
        self, units: list[ParsedUnit], answers: dict[str, PairedAnswer]
    ) -> ValidationResult:
        """Run all validators V1 to V7."""
        issues: list[ValidationIssue] = []
        all_units = flatten_units(units)

        # 1. V1: Contiguous numbering
        self._check_v1_numbering(units, issues)

        # 2. V2: Every gradable unit has marks
        self._check_v2_marks(all_units, issues)

        # 3. V3: Choice-aware total
        self._check_v3_attemptable_marks(units, issues)

        # 4. V4: Answer pairing completeness
        if self.has_answers:
            self._check_v4_answers(all_units, answers, issues)

        # 5. V5: Text length bounds
        self._check_v5_lengths(all_units, issues)

        # 6. V6: MCQ completeness
        self._check_v6_mcqs(all_units, answers, issues)

        # 7. V7: Page spans monotonic
        self._check_v7_spans(all_units, issues)

        # Distribute issue flags to units and assign parse_confidence
        self._assign_unit_confidence(all_units, issues)

        outcome = "ok"
        if any(i.severity == "error" for i in issues):
            outcome = "needs_review"
        elif any(i.severity == "warn" for i in issues):
            outcome = "ok_with_warnings"

        return ValidationResult(outcome=outcome, issues=issues)

    def _check_v1_numbering(
        self, root_units: list[ParsedUnit], issues: list[ValidationIssue]
    ) -> None:
        """V1: Question numbers contiguous 1..N; parts contiguous a.. within question."""
        q_nums: list[int] = []
        for u in root_units:
            if u.kind == "question":
                m = re.search(r"\d+", u.label_path)
                if m:
                    q_nums.append(int(m.group(0)))

            # Check parts within questions
            if u.children:
                part_letters: list[str] = []
                for c in u.children:
                    if c.kind == "part":
                        p_part = c.label_path.split(".")[-1]
                        if len(p_part) == 1 and p_part.isalpha():
                            part_letters.append(p_part.lower())

                if part_letters:
                    expected_ord = ord("a")
                    for letter in part_letters:
                        if ord(letter) != expected_ord:
                            issues.append(
                                ValidationIssue(
                                    code="V1_PART_GAP",
                                    severity="error",
                                    message=f"Part letter gap: expected '{chr(expected_ord)}', found '{letter}'",
                                    unit_label=f"{u.label_path}.{letter}",
                                )
                            )
                        expected_ord += 1

        if q_nums:
            expected = 1
            for qn in sorted(q_nums):
                if qn != expected:
                    issues.append(
                        ValidationIssue(
                            code="V1_QUESTION_GAP",
                            severity="error",
                            message=f"Question numbering gap: expected Q{expected}, found Q{qn}",
                            unit_label=f"Q{qn}",
                        )
                    )
                expected += 1

    def _check_v2_marks(
        self, all_units: list[ParsedUnit], issues: list[ValidationIssue]
    ) -> None:
        """V2: Every gradable unit has marks."""
        for u in all_units:
            if u.is_gradable and u.marks is None:
                issues.append(
                    ValidationIssue(
                        code="V2_MISSING_MARKS",
                        severity="error",
                        message=f"Gradable unit {u.label_path} has no marks assigned",
                        unit_label=u.label_path,
                    )
                )

    def _check_v3_attemptable_marks(
        self, root_units: list[ParsedUnit], issues: list[ValidationIssue]
    ) -> None:
        """V3: Choice-aware total: attemptable maximum equals paper_max."""
        # 1. Group items, collapsing OR groups to max(alternatives)
        top_questions = [u for u in root_units if u.kind in ("question", "case_stem")]
        if not top_questions:
            return

        compulsory_marks = 0
        optional_marks_list: list[int] = []

        for q in top_questions:
            q_mark = q.marks or 0
            if q.choice_role == "compulsory":
                compulsory_marks += q_mark
            else:
                optional_marks_list.append(q_mark)

        optional_marks_list.sort(reverse=True)
        k = self.optional_pick or len(optional_marks_list)
        attemptable = compulsory_marks + sum(optional_marks_list[:k])

        diff = abs(attemptable - self.profile.paper_max)
        if diff == 0:
            return

        if diff <= 2:
            issues.append(
                ValidationIssue(
                    code="V3_TOTAL_MARKS_WARN",
                    severity="warn",
                    message=f"Attemptable marks ({attemptable}) differs slightly from paper max ({self.profile.paper_max})",
                )
            )
        else:
            # If no choice rule was parsed, check if total is within 1.0x to 1.6x paper_max
            total_raw = compulsory_marks + sum(optional_marks_list)
            if (
                self.optional_pick is None
                and self.profile.paper_max <= total_raw <= int(1.6 * self.profile.paper_max)
            ):
                issues.append(
                    ValidationIssue(
                        code="V3_TOTAL_MARKS_RAW_WARN",
                        severity="warn",
                        message=f"Total raw marks ({total_raw}) is between paper max and 1.6x, but no choice rule found",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        code="V3_TOTAL_MARKS_MISMATCH",
                        severity="error",
                        message=f"Attemptable marks ({attemptable}) deviates from paper max ({self.profile.paper_max}) by {diff} marks",
                    )
                )

    def _check_v4_answers(
        self,
        all_units: list[ParsedUnit],
        answers: dict[str, PairedAnswer],
        issues: list[ValidationIssue],
    ) -> None:
        """V4: Every gradable unit has an answer or MCQ key."""
        gradables = [u for u in all_units if u.is_gradable]
        if not gradables:
            return

        missing = 0
        for u in gradables:
            ans = answers.get(u.label_path)
            has_ans = ans and (ans.answer_text or ans.mcq_correct_option)
            if not has_ans:
                missing += 1
                issues.append(
                    ValidationIssue(
                        code="V4_MISSING_ANSWER",
                        severity="warn",
                        message=f"Gradable unit {u.label_path} lacks paired answer",
                        unit_label=u.label_path,
                    )
                )

        if (missing / len(gradables)) > 0.10:
            issues.append(
                ValidationIssue(
                    code="V4_MISSING_ANSWERS_ERROR",
                    severity="error",
                    message=f"{missing} of {len(gradables)} gradable units (>10%) lack answers",
                )
            )

    def _check_v5_lengths(
        self, all_units: list[ParsedUnit], issues: list[ValidationIssue]
    ) -> None:
        """V5: Unit text length within bounds [min_unit_chars, max_unit_chars]."""
        for u in all_units:
            text_len = len(u.question_text)
            if text_len == 0 and u.is_gradable:
                issues.append(
                    ValidationIssue(
                        code="V5_UNIT_EMPTY",
                        severity="error",
                        message=f"Gradable unit {u.label_path} has empty question text",
                        unit_label=u.label_path,
                    )
                )
            elif 0 < text_len < self.profile.defaults.min_unit_chars and u.is_gradable:
                issues.append(
                    ValidationIssue(
                        code="V5_UNIT_TOO_SHORT",
                        severity="warn",
                        message=f"Unit {u.label_path} text length ({text_len}) below min threshold ({self.profile.defaults.min_unit_chars})",
                        unit_label=u.label_path,
                    )
                )
            elif text_len > self.profile.defaults.max_unit_chars:
                issues.append(
                    ValidationIssue(
                        code="V5_UNIT_TOO_LONG",
                        severity="error",
                        message=f"Unit {u.label_path} text length ({text_len}) exceeds max threshold ({self.profile.defaults.max_unit_chars})",
                        unit_label=u.label_path,
                    )
                )

    def _check_v6_mcqs(
        self,
        all_units: list[ParsedUnit],
        answers: dict[str, PairedAnswer],
        issues: list[ValidationIssue],
    ) -> None:
        """V6: MCQ completeness (options and key)."""
        for u in all_units:
            if u.kind == "mcq":
                ans = answers.get(u.label_path)
                if not u.mcq_options or len(u.mcq_options) < 4:
                    issues.append(
                        ValidationIssue(
                            code="V6_MCQ_OPTIONS_MISSING",
                            severity="warn",
                            message=f"MCQ {u.label_path} has fewer than 4 options ({len(u.mcq_options)} found)",
                            unit_label=u.label_path,
                        )
                    )
                if not (ans and ans.mcq_correct_option):
                    issues.append(
                        ValidationIssue(
                            code="V6_MCQ_KEY_MISSING",
                            severity="warn",
                            message=f"MCQ {u.label_path} has no paired answer key option",
                            unit_label=u.label_path,
                        )
                    )

    def _check_v7_spans(
        self, all_units: list[ParsedUnit], issues: list[ValidationIssue]
    ) -> None:
        """V7: Page spans monotonic (start <= end)."""
        for u in all_units:
            if u.page_start > u.page_end:
                issues.append(
                    ValidationIssue(
                        code="V7_PAGE_SPAN_INVALID",
                        severity="error",
                        message=f"Unit {u.label_path} has start page ({u.page_start}) > end page ({u.page_end})",
                        unit_label=u.label_path,
                    )
                )

    def _assign_unit_confidence(
        self, all_units: list[ParsedUnit], issues: list[ValidationIssue]
    ) -> None:
        """Assign flags to specific units and set parse_confidence."""
        unit_map = {u.label_path: u for u in all_units}
        for iss in issues:
            if iss.unit_label and iss.unit_label in unit_map:
                u = unit_map[iss.unit_label]
                u.validation_flags.append(iss.code)
                if iss.severity == "error":
                    u.parse_confidence = "low"
                elif iss.severity == "warn" and u.parse_confidence != "low":
                    u.parse_confidence = "medium"
