from fastapi import APIRouter
from fastapi.responses import FileResponse

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.rerun_service import rerun_sessions


router = APIRouter(tags=["rerun"])


@router.post("/rerun/session", response_model=RerunSessionRecord)
def create_rerun_session(payload: RerunSessionCreate) -> RerunSessionRecord:
    return rerun_sessions.create(payload)


@router.get("/rerun/session/{session_id}", response_model=RerunSessionRecord)
def get_rerun_session(session_id: str) -> RerunSessionRecord:
    return rerun_sessions.get(session_id)


@router.get("/rerun/recordings/{session_id}.rrd")
def get_rerun_recording(session_id: str) -> FileResponse:
    path = rerun_sessions.path_for_recording(session_id)
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)
