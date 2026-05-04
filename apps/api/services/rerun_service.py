from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord


class RerunSessionStore:
    def __init__(self) -> None:
        self._records: dict[str, RerunSessionRecord] = {}

    def create(self, payload: RerunSessionCreate) -> RerunSessionRecord:
        session_id = str(uuid4())
        record = RerunSessionRecord(
            session_id=session_id,
            dataset_id=payload.dataset_id,
            episode_index=payload.episode_index,
            mode=payload.mode,
            status="pending",
            viewer_url=None,
            rrd_url=None,
        )
        self._records[session_id] = record
        return record

    def get(self, session_id: str) -> RerunSessionRecord:
        record = self._records.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Rerun session not found")
        return record


rerun_sessions = RerunSessionStore()
