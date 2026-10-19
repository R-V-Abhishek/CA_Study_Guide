"""Typed administrator-only readiness, source-bound decisions and audit history."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from caf_api.auth import Principal, require_admin
from caf_api.routes import get_operations_db
from caf_common.settings import get_settings
from caf_contracts.readiness import (ReadinessSummary, ReadinessWriteResult, BindingWrite,
                                     InventoryWrite, PriorWrite)
from caf_l5.readiness import readiness_summary, write_readiness, ReadinessConflict

router = APIRouter(prefix='/api/v1/admin/readiness', tags=['administrator readiness'],
                   dependencies=[Depends(require_admin)])


@router.get('', response_model=ReadinessSummary)
def summary(target_attempt_id: str | None = None, taxonomy_version_id: int | None = None,
            paper_id: str | None = None, source_family: str | None = None,
            blocker_type: str | None = None, db: Session = Depends(get_operations_db)):
    try:
        return readiness_summary(db, target_attempt_id or get_settings().app.target_attempt_id,
                                 taxonomy_version_id, paper_id, source_family, blocker_type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def mutate(db, body, admin, kind):
    try:
        result = write_readiness(db, body, admin.id, kind)
        db.commit()
        return result
    except ReadinessConflict as exc:
        db.rollback()
        raise HTTPException(409, {'message': str(exc), 'current_hash': exc.current_hash,
                                  'current': exc.current}) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.put('/bindings', response_model=ReadinessWriteResult)
def binding(body: BindingWrite, db: Session = Depends(get_operations_db),
            admin: Principal = Depends(require_admin)):
    return mutate(db, body, admin, 'binding')


@router.put('/inventory', response_model=ReadinessWriteResult)
def inventory(body: InventoryWrite, db: Session = Depends(get_operations_db),
              admin: Principal = Depends(require_admin)):
    return mutate(db, body, admin, 'inventory')


@router.put('/priors', response_model=ReadinessWriteResult)
def prior(body: PriorWrite, db: Session = Depends(get_operations_db),
          admin: Principal = Depends(require_admin)):
    return mutate(db, body, admin, 'prior')
