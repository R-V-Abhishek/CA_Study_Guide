"""Scoring configuration loader for L5 Intelligence."""

import hashlib
from pathlib import Path
import tomllib
from typing import Any
from pydantic import BaseModel, Field


class WeightsConfig(BaseModel):
    exam: float = 0.6
    practice: float = 0.2
    prior: float = 0.2


class PlanConfig(BaseModel):
    per_chapter_cap: int = 3
    weak_boost: float = 0.25
    in_progress_boost: float = 0.10


class ScoringConfig(BaseModel):
    version: str = "v1"
    half_life_exam_months: float = 24.0
    half_life_practice_months: float = 12.0
    secondary_share: float = 0.5
    p6_cross_paper_factor: float = 0.5  # κ
    law_stale_factor: float = 0.5       # λ
    freq_window_attempts: int = 5       # N
    weak_flag_min_hits: int = 3

    weights: WeightsConfig = Field(default_factory=WeightsConfig)
    plan: PlanConfig = Field(default_factory=PlanConfig)

    raw_bytes: bytes = Field(default=b"", exclude=True)

    @property
    def config_hash(self) -> str:
        """Deterministic 16-character SHA-256 hash of configuration."""
        if self.raw_bytes:
            return hashlib.sha256(self.raw_bytes).hexdigest()[:16]
        # Fallback to model dump serialization
        dump = f"{self.version}:{self.half_life_exam_months}:{self.half_life_practice_months}:{self.weights.model_dump()}"
        return hashlib.sha256(dump.encode("utf-8")).hexdigest()[:16]


def load_scoring_config(config_path: Path | str = "config/scoring.toml") -> ScoringConfig:
    """Load and validate scoring configuration from TOML file."""
    path = Path(config_path)
    if not path.is_file():
        # Fallback to defaults
        return ScoringConfig()

    raw_bytes = path.read_bytes()
    data = tomllib.loads(raw_bytes.decode("utf-8"))

    cfg = ScoringConfig(
        version=data.get("version", "v1"),
        half_life_exam_months=float(data.get("half_life_exam_months", 24.0)),
        half_life_practice_months=float(data.get("half_life_practice_months", 12.0)),
        secondary_share=float(data.get("secondary_share", 0.5)),
        p6_cross_paper_factor=float(data.get("p6_cross_paper_factor", 0.5)),
        law_stale_factor=float(data.get("law_stale_factor", 0.5)),
        freq_window_attempts=int(data.get("freq_window_attempts", 5)),
        weak_flag_min_hits=int(data.get("weak_flag_min_hits", 3)),
        weights=WeightsConfig(**data.get("weights", {})),
        plan=PlanConfig(**data.get("plan", {})),
        raw_bytes=raw_bytes,
    )
    return cfg
