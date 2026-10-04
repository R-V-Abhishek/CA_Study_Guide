"""Answer pairing module for same-doc and MCQ keys."""

from dataclasses import dataclass, field
import re
from typing import Any
from caf_l2.blocks import LineBlock
from caf_l2.segmenter import ParsedUnit


@dataclass
class PairedAnswer:
    label_path: str
    answer_text: str | None
    page_start: int | None
    page_end: int | None
    mcq_correct_option: str | None
    pairing_method: str  # same_doc | cross_doc | mcq_key | override
    answer_doc_id: int | None = None
    block_start: str | None = None
    block_end: str | None = None
    status: str = "missing"
    candidate_labels: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)


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
    conflicts: set[str] = set()

    table_title_patterns = patterns.get("mcq_key_table_title", [])
    row_patterns = patterns.get("mcq_key_row", [])

    pending_number: str | None = None
    for line in lines_text:
        if any(p.pattern.search(line) for p in table_title_patterns):
            in_table = True
            continue

        if in_table:
            number = next((p.pattern.search(line) for p in patterns.get("mcq_key_number", []) if p.pattern.search(line)), None)
            option = next((p.pattern.search(line) for p in patterns.get("mcq_key_option", []) if p.pattern.search(line)), None)
            if number:
                pending_number = number.group("n")
                continue
            if option and pending_number:
                num, opt = pending_number, option.group("o").upper()
                if num in key_map and key_map[num] != opt:
                    conflicts.add(num)
                key_map[num] = opt
                pending_number = None
                continue
            for rp in row_patterns:
                m = rp.pattern.search(line)
                if m:
                    num = m.group("n")
                    opt = m.group("o").upper()
                    if num in key_map and key_map[num] != opt:
                        conflicts.add(num)
                    key_map[num] = opt
                    break
            # If line is completely blank or another heading starts, continue
    return {num: opt for num, opt in key_map.items() if num not in conflicts}


def pair_answers(
    units: list[ParsedUnit],
    mode: str = "interleaved",
    key_patterns: dict[str, Any] | None = None,
) -> dict[str, PairedAnswer]:
    """Pair questions with answers based on profile mode."""
    all_units = flatten_units(units)
    paired: dict[str, PairedAnswer] = {}

    # Key regions are explicit, so narrative answer lists cannot alter an MCQ key.
    mcq_keys: dict[str, str] = {}
    if key_patterns:
        all_lines = [line.text for u in all_units for line in u.line_blocks if line.region == "answer_key"]
        mcq_keys = extract_mcq_key_table(all_lines, key_patterns)

    key_blocks = sorted([line for unit in all_units for line in unit.line_blocks if line.region == "answer_key"], key=lambda b: (b.page, b.order))
    key_spans: dict[tuple[str, str], list[LineBlock]] = {}
    pending_number: tuple[str, LineBlock] | None = None
    current_key: tuple[str, str] | None = None
    if key_patterns:
        for block in key_blocks:
            for rule in key_patterns.get("mcq_key_row", []):
                match = rule.pattern.search(block.text)
                if match:
                    key_spans.setdefault((block.numbering_scope, match.group("n")), []).append(block)
            new_number = False
            key_option = False
            for rule in key_patterns.get("mcq_key_number", []):
                match = rule.pattern.search(block.text)
                if match:
                    pending_number = (match.group("n"), block)
                    current_key = None
                    new_number = True
            for rule in key_patterns.get("mcq_key_option", []):
                match = rule.pattern.search(block.text)
                if match and pending_number:
                    current_key = (block.numbering_scope, pending_number[0])
                    key_spans.setdefault(current_key, []).extend([pending_number[1], block])
                    pending_number = None
                    key_option = True
            if current_key and not new_number and not key_option and current_key[0] == block.numbering_scope:
                key_spans[current_key].append(block)

    for u in all_units:
        if not u.is_gradable and not u.children:
            # If not gradable leaf (e.g. case stem), skip pairing
            continue

        answer_blocks = [b for b in u.line_blocks if b.region in {"answer", "answer_key"}]
        if u.kind == "mcq":
            mcq_num = u.label_path.split(".")[-1].replace("M", "")
            scope = u.label_path.rsplit(".", 1)[0] if "." in u.label_path else ""
            scoped_lines = [line.text for candidate in all_units if candidate.label_path == scope or candidate.label_path.startswith(scope + ".") for line in candidate.line_blocks if line.region == "answer_key"]
            scoped_keys = extract_mcq_key_table(scoped_lines, key_patterns) if key_patterns else {}
            collection_scope = re.sub(r"\.CS[^.]+$", "", scope)
            collection_lines = [block.text for block in key_blocks if block.numbering_scope == collection_scope]
            collection_keys = extract_mcq_key_table(collection_lines, key_patterns) if key_patterns else {}
            correct_opt = scoped_keys.get(mcq_num) or collection_keys.get(mcq_num) or u.mcq_correct_option
            unique_number = sum(1 for candidate in all_units if candidate.kind == "mcq" and candidate.label_path.split(".")[-1] == f"M{mcq_num}") == 1
            if not scope or unique_number:
                correct_opt = correct_opt or mcq_keys.get(mcq_num)
            if correct_opt and not answer_blocks:
                answer_blocks = key_spans.get((collection_scope, mcq_num), [])
                if not answer_blocks and unique_number:
                    answer_blocks = key_spans.get(("", mcq_num), [])
            key_explanation = "\n".join(block.raw_text or block.text for block in answer_blocks[1:]) if answer_blocks and any("Option" in block.text for block in answer_blocks) else None
            paired[u.label_path] = PairedAnswer(
                label_path=u.label_path,
                answer_text=u.answer_text or key_explanation or None,
                page_start=min((b.page for b in answer_blocks), default=None),
                page_end=max((b.page for b in answer_blocks), default=None),
                mcq_correct_option=correct_opt,
                pairing_method="mcq_key" if correct_opt else "same_doc",
                status="matched" if correct_opt or u.answer_text else "missing",
                block_start=answer_blocks[0].block_id if answer_blocks else None,
                block_end=answer_blocks[-1].block_id if answer_blocks else None,
            )
        else:
            # Interleaved question/answer
            ans_text = u.answer_text
            paired[u.label_path] = PairedAnswer(
                label_path=u.label_path,
                answer_text=ans_text if ans_text else None,
                page_start=min((b.page for b in answer_blocks), default=None),
                page_end=max((b.page for b in answer_blocks), default=None),
                mcq_correct_option=None,
                pairing_method="same_doc",
                status="matched" if ans_text else "missing",
                block_start=next((b.block_id for b in u.line_blocks if b.region == "answer"), None),
                block_end=next((b.block_id for b in reversed(u.line_blocks) if b.region == "answer"), None),
            )

    return paired


def pair_cross_doc_answers(
    question_units: list[ParsedUnit],
    answer_units: list[ParsedUnit],
    answer_doc_id: int | None = None,
) -> dict[str, PairedAnswer]:
    """Pair questions from a question document with answers from a separate answer document.
    
    Matches units by label_path (e.g. Q1(a), Q2(b)(i)).
    """
    flat_questions = flatten_units(question_units)
    flat_answers = flatten_units(answer_units)

    # Build index of answer units by label_path
    answer_map: dict[str, list[ParsedUnit]] = {}
    for ans in flat_answers:
        canonical_label = re.sub(r"\.repeat\d+", "", ans.label_path)
        answer_map.setdefault(canonical_label, []).append(ans)

    paired: dict[str, PairedAnswer] = {}
    for q in flat_questions:
        if not q.is_gradable and not q.children:
            continue

        candidates = answer_map.get(q.label_path, [])
        evidence = [{"answer_doc_id": answer_doc_id, "label_path": candidate.label_path, "answer_text": candidate.answer_text or None, "page_start": candidate.page_start, "page_end": candidate.page_end, "block_start": candidate.block_start, "block_end": candidate.block_end, "mcq_correct_option": candidate.mcq_correct_option} for candidate in candidates]
        ans = candidates[0] if len(candidates) == 1 else None
        if ans:
            paired[q.label_path] = PairedAnswer(
                label_path=q.label_path,
                answer_text=ans.answer_text or None,
                page_start=ans.page_start,
                page_end=ans.page_end,
                mcq_correct_option=ans.mcq_correct_option,
                pairing_method="cross_doc",
                answer_doc_id=answer_doc_id,
                block_start=ans.block_start,
                block_end=ans.block_end,
                status="matched" if ans.answer_text or ans.mcq_correct_option else "missing",
                candidate_labels=[a.label_path for a in candidates],
                candidates=evidence,
            )
        else:
            paired[q.label_path] = PairedAnswer(
                label_path=q.label_path,
                answer_text=None,
                page_start=None,
                page_end=None,
                mcq_correct_option=None,
                pairing_method="cross_doc",
                answer_doc_id=answer_doc_id,
                status="ambiguous" if len(candidates) > 1 else "missing",
                candidate_labels=[a.label_path for a in candidates],
                candidates=evidence,
            )

    return paired
