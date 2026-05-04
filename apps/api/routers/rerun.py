from fastapi import APIRouter

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.rerun_service import rerun_sessions


router = APIRouter(tags=["rerun"])


@router.post("/rerun/session", response_model=RerunSessionRecord)
def create_rerun_session(payload: RerunSessionCreate) -> RerunSessionRecord:
    return rerun_sessions.create(payload)


@router.get("/rerun/session/{session_id}", response_model=RerunSessionRecord)
def get_rerun_session(session_id: str) -> RerunSessionRecord:
    return rerun_sessions.get(session_id)
