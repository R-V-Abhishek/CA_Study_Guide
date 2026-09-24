"""Profile models, compilation, and fallback resolver."""

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any
import yaml


class ProfileNotFoundError(Exception):
    """Raised when no matching extraction profile exists."""
    pass


@dataclass
class PatternRule:
    pattern: re.Pattern[str]
    require_bold: bool = False


@dataclass
class ChoiceRule:
    pattern: re.Pattern[str]
    compulsory: list[str] = field(default_factory=list)
    optional_pick: str | None = None


@dataclass
class ExtractionDefaults:
    mcq_marks: int = 2
    min_unit_chars: int = 15
    max_unit_chars: int = 25000


@dataclass
class ExtractionProfile:
    id: str
    scheme: str
    doc_type: str
    paper_max: int
    mode: str  # interleaved | sectioned | questions_only
    patterns: dict[str, list[PatternRule]]
    choice_rules: list[ChoiceRule]
    defaults: ExtractionDefaults
    raw_data: dict[str, Any] = field(default_factory=dict)


def load_profile(path: Path) -> ExtractionProfile:
    """Load and compile an extraction profile from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    profile_id = data.get("id", path.stem)
    applies = data.get("applies_to", {})
    scheme = applies.get("scheme", "")
    doc_type = applies.get("doc_type", "")
    paper_max = int(data.get("paper_max", 100))
    mode = data.get("mode", "interleaved")

    patterns: dict[str, list[PatternRule]] = {}
    for rule_name, rule_list in data.get("patterns", {}).items():
        compiled_list: list[PatternRule] = []
        for r in rule_list:
            pat = re.compile(r["re"], re.IGNORECASE)
            req_bold = bool(r.get("require_bold", False))
            compiled_list.append(PatternRule(pattern=pat, require_bold=req_bold))
        patterns[rule_name] = compiled_list

    choice_rules: list[ChoiceRule] = []
    for cr in data.get("choice_rules", []):
        c_pat = re.compile(cr["re"], re.IGNORECASE)
        comp = cr.get("compulsory", [])
        opt_pick = cr.get("optional_pick")
        choice_rules.append(
            ChoiceRule(pattern=c_pat, compulsory=comp, optional_pick=opt_pick)
        )

    defs_dict = data.get("defaults", {})
    defaults = ExtractionDefaults(
        mcq_marks=int(defs_dict.get("mcq_marks", 2)),
        min_unit_chars=int(defs_dict.get("min_unit_chars", 15)),
        max_unit_chars=int(defs_dict.get("max_unit_chars", 25000)),
    )

    return ExtractionProfile(
        id=profile_id,
        scheme=scheme,
        doc_type=doc_type,
        paper_max=paper_max,
        mode=mode,
        patterns=patterns,
        choice_rules=choice_rules,
        defaults=defaults,
        raw_data=data,
    )


def resolve_profile(
    profiles_dir: Path,
    scheme_id: str,
    doc_type_id: str,
    paper_id: str | None = None,
) -> ExtractionProfile:
    """Resolve profile following fallback chain:
    
    1. (scheme, doc_type, paper)
    2. (scheme, doc_type)
    3. (doc_type)
    """
    paper_code = paper_id.split(".")[-1] if paper_id else None

    candidate_filenames = []
    if paper_code:
        candidate_filenames.append(f"{scheme_id}.{doc_type_id}.{paper_code}.yaml")
    if paper_id:
        candidate_filenames.append(f"{scheme_id}.{doc_type_id}.{paper_id}.yaml")
    candidate_filenames.append(f"{scheme_id}.{doc_type_id}.yaml")
    candidate_filenames.append(f"{doc_type_id}.yaml")

    for fname in candidate_filenames:
        p = profiles_dir / fname
        if p.is_file():
            return load_profile(p)

    raise ProfileNotFoundError(
        f"NO_PROFILE: No profile found for scheme={scheme_id}, doc_type={doc_type_id}, paper={paper_id}"
    )
