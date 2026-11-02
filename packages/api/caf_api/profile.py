"""Per-account profile settings and export."""

from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_api.responses import (
    ProfileSettings,
    ProfileExport,
)
from caf_api.study import api_list_mock_tests
from caf_api.deps import get_db
from caf_api.auth import Principal, require_account, get_identity_db
from caf_db.models.app import (
    Note,
    Progress,
    ProgressEvent,
    RevisionEvent,
    UserAccount,
    StudySession,
)
from caf_db.models.ref import Attempt, Paper

from caf_l5.service import get_account_settings, selected_papers

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_account)])


class ProfileSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)
    target_attempt_id: str
    selected_paper_ids: list[str] = Field(min_length=1)
    hours_per_week: float = Field(gt=0, le=9999.9, allow_inf_nan=False)
    minutes_per_subtopic: int = Field(gt=0, le=2147483647)
    revision_intervals: list[int] = Field(min_length=1)
    exam_start_date: date | None = None
    include_hindi: bool = False

    @model_validator(mode="after")
    def validate_settings(self):
        if not self.display_name.strip():
            raise ValueError("Display name cannot be blank")
        if len(set(self.selected_paper_ids)) != len(self.selected_paper_ids):
            raise ValueError("Selected papers must be unique")
        if any(day <= 0 for day in self.revision_intervals):
            raise ValueError("Revision intervals must be positive")
        if any(day > 2147483647 for day in self.revision_intervals):
            raise ValueError("Revision intervals exceed the supported integer range")
        if any(a >= b for a, b in zip(self.revision_intervals, self.revision_intervals[1:])):
            raise ValueError("Revision intervals must be strictly increasing")
        return self


def profile_settings_payload(session: Session, account: Principal) -> dict:
    settings = get_account_settings(session, account.id)
    papers = session.scalars(
        sa.select(Paper).where(Paper.is_current.is_(True)).order_by(Paper.code, Paper.id)
    ).all()
    paper_ids = selected_papers(session, account.id)
    return {
        "display_name": account.name,
        "target_attempt_id": settings.target_attempt_id,
        "selected_paper_ids": paper_ids,
        "groups": sorted({p.group_no for p in papers if p.id in paper_ids}),
        "hours_per_week": float(settings.hours_per_week),
        "minutes_per_subtopic": settings.minutes_per_subtopic,
        "revision_intervals": settings.revision_intervals,
        "exam_start_date": settings.exam_start_date,
        "include_hindi": settings.include_hindi,
        "available_papers": [
            {"id": p.id, "code": p.code, "name": p.name, "group_no": p.group_no} for p in papers
        ],
        "available_attempts": [
            {"id": a.id, "label": a.label}
            for a in session.scalars(sa.select(Attempt).order_by(Attempt.id))
        ],
    }


@router.get("/me/settings", response_model=ProfileSettings)
def get_profile_settings(
    session: Session = Depends(get_db), account: Principal = Depends(require_account)
):
    return profile_settings_payload(session, account)


@router.put("/me/settings", response_model=ProfileSettings)
def update_profile_settings(
    req: ProfileSettingsUpdate,
    session: Session = Depends(get_identity_db),
    account: Principal = Depends(require_account),
):
    if session.get(Attempt, req.target_attempt_id) is None:
        raise HTTPException(status_code=422, detail="Unknown target attempt")
    valid_papers = set(session.scalars(sa.select(Paper.id).where(Paper.is_current.is_(True))))
    if not set(req.selected_paper_ids).issubset(valid_papers):
        raise HTTPException(status_code=422, detail="Select current papers only")
    settings = get_account_settings(session, account.id)
    user = session.get(UserAccount, account.id)
    user.name = req.display_name.strip()
    settings.target_attempt_id = req.target_attempt_id
    settings.selected_paper_ids = req.selected_paper_ids
    settings.hours_per_week = req.hours_per_week
    settings.minutes_per_subtopic = req.minutes_per_subtopic
    settings.revision_intervals = req.revision_intervals
    settings.exam_start_date = req.exam_start_date
    settings.include_hindi = req.include_hindi
    session.commit()
    payload = profile_settings_payload(session, account)
    payload["display_name"] = user.name
    return payload


@router.get("/me/export", response_model=ProfileExport)
def export_profile(
    session: Session = Depends(get_db), account: Principal = Depends(require_account)
):
    def records(model):
        rows = session.scalars(sa.select(model).where(model.user_id == account.id)).all()
        return [
            {
                column.name: row.__dict__[column.name]
                for column in model.__table__.columns
                if column.name != "user_id"
            }
            for row in rows
        ]

    return {
        "account_id": account.id,
        "exported_at": datetime.now(timezone.utc),
        "settings": profile_settings_payload(session, account),
        "progress": records(Progress),
        "notes": records(Note),
        "progress_events": records(ProgressEvent),
        "revision_events": records(RevisionEvent),
        "mock_tests": api_list_mock_tests(None, session, account),
        "study_sessions": records(StudySession),
    }
