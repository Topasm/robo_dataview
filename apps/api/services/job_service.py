from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.common import JobStatus
from apps.api.schemas.jobs import JobCreateRequest, JobRecord


class JobStore:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}

    def create(self, kind: str, payload: JobCreateRequest) -> JobRecord:
        job_id = str(uuid4())
        record = JobRecord(
            job_id=job_id,
            kind=kind,
            status=JobStatus.queued,
            dataset_id=payload.dataset_id,
            episode_indices=payload.episode_indices,
            progress=0.0,
            message="Worker queue integration is planned for Phase 5.",
        )
        self._records[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord:
        record = self._records.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return record


jobs = JobStore()
