"""Answer pairing module for same-doc and MCQ keys."""

from dataclasses import dataclass
import re
from typing import Any
from caf_l2.segmenter import ParsedUnit


@dataclass
class PairedAnswer:
    label_path: str
    answer_text: str | None
    page_start: int | None
    page_end: int | None
    mcq_correct_option: str | None
    pairing_method: str  # same_doc | cross_doc | mcq_key | override


def flatten_units(units: list[ParsedUnit]) -> list[ParsedUnit]:
    """Flatten unit tree in pre-order depth-first."""
    res: list[ParsedUnit] = []
    for u in units:
        res.append(u)
        if u.children:
            res.extend(flatten_units(u.children))
    return res


def extract_mcq_key_table(
    lines_text: list[str], patterns: dict[str, Any]
) -> dict[str, str]:
    """Parse MCQ answer key table lines into {mcq_num: option} mapping."""
    key_map: dict[str, str] = {}
    in_table = False

    table_title_patterns = patterns.get("mcq_key_table_title", [])
    row_patterns = patterns.get("mcq_key_row", [])

    for line in lines_text:
        if any(p.pattern.search(line) for p in table_title_patterns):
            in_table = True
            continue

        if in_table:
            matched = False
            for rp in row_patterns:
                m = rp.pattern.search(line)
                if m:
                    num = m.group("n")
                    opt = m.group("o").upper()
                    key_map[num] = opt
                    matched = True
                    break
            # If line is completely blank or another heading starts, continue
    return key_map


def pair_answers(
    units: list[ParsedUnit],
    mode: str = "interleaved",
    key_patterns: dict[str, Any] | None = None,
) -> dict[str, PairedAnswer]:
    """Pair questions with answers based on profile mode."""
    all_units = flatten_units(units)
    paired: dict[str, PairedAnswer] = {}

    # Check for MCQ keys across the full document text if patterns provided
    mcq_keys: dict[str, str] = {}
    if key_patterns:
        all_lines = [line.text for u in all_units for line in u.line_blocks]
        mcq_keys = extract_mcq_key_table(all_lines, key_patterns)

    for u in all_units:
        if not u.is_gradable and not u.children:
            # If not gradable leaf (e.g. case stem), skip pairing
            continue

        if u.kind == "mcq":
            mcq_num = u.label_path.split(".")[-1].replace("M", "")
            correct_opt = mcq_keys.get(mcq_num) or u.mcq_correct_option
            paired[u.label_path] = PairedAnswer(
                label_path=u.label_path,
                answer_text=u.answer_text or None,
                page_start=u.page_start,
                page_end=u.page_end,
                mcq_correct_option=correct_opt,
                pairing_method="mcq_key" if correct_opt else "same_doc",
            )
        else:
            # Interleaved question/answer
            ans_text = u.answer_text
            paired[u.label_path] = PairedAnswer(
                label_path=u.label_path,
                answer_text=ans_text if ans_text else None,
                page_start=u.page_start,
                page_end=u.page_end,
                mcq_correct_option=None,
                pairing_method="same_doc",
            )

    return paired
