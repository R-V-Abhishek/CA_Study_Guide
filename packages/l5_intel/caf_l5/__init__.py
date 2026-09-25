"""L5 Intelligence module for CA Final Study Companion."""

from caf_l5.config import ScoringConfig, load_scoring_config
from caf_l5.planning import generate_study_plan
from caf_l5.revision import get_revision_due_list, record_revision_outcome
from caf_l5.scoring import (
    calculate_attributed_marks,
    compute_age_months,
    compute_decay,
    recompute_scores,
)
from caf_l5.service import (
    compute_weighted_coverage,
    get_current_score_run,
    get_ingestion_coverage_matrix,
    get_subtopic_scores_for_paper,
    get_weak_subtopics,
    is_subtopic_weak,
)
from caf_l5.why import get_subtopic_why

__all__ = [
    "ScoringConfig",
    "load_scoring_config",
    "compute_age_months",
    "compute_decay",
    "calculate_attributed_marks",
    "recompute_scores",
    "get_current_score_run",
    "get_subtopic_scores_for_paper",
    "get_weak_subtopics",
    "is_subtopic_weak",
    "get_ingestion_coverage_matrix",
    "compute_weighted_coverage",
    "get_subtopic_why",
    "generate_study_plan",
    "get_revision_due_list",
    "record_revision_outcome",
]
