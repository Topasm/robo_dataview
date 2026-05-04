from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.common import JobStatus
from apps.api.schemas.exports import ExportCreateRequest, ExportRecord


class ExportStore:
    def __init__(self) -> None:
        self._records: dict[str, ExportRecord] = {}

    def create(self, payload: ExportCreateRequest) -> ExportRecord:
        export_id = str(uuid4())
        record = ExportRecord(
            export_id=export_id,
            dataset_id=payload.dataset_id,
            episode_indices=payload.episode_indices,
            format=payload.format,
            status=JobStatus.queued,
            output_uri=None,
            message="Export worker integration is planned for Phase 7.",
        )
        self._records[export_id] = record
        return record

    def get(self, export_id: str) -> ExportRecord:
        record = self._records.get(export_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Export not found")
        return record


exports = ExportStore()
