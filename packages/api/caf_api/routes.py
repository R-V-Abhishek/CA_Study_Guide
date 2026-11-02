"""Authenticated study, system and profile endpoints, assembled in their original route order."""

from fastapi import APIRouter

from caf_api.deps import get_db, get_operations_db  # noqa: F401  (kept for existing importers)
from caf_api.profile import router as profile_router
from caf_api.study import (  # noqa: F401  (kept for existing importers)
    get_dashboard,
    get_paper_tree,
    get_subtopic_detail,
    list_papers,
    router as study_router,
)
from caf_api.system import router as system_router

router = APIRouter()
router.include_router(study_router)
router.include_router(system_router)
router.include_router(profile_router)
