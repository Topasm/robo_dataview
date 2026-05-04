from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.api.schemas.common import JobStatus
from apps.api.schemas.exports import ExportCreateRequest
from apps.api.schemas.jobs import (
    JobCreateRequest,
    JobRecord,
    PromptTemplateRecord,
    VisualEmbeddingJobCreateRequest,
)
from apps.api.schemas.rerun import RerunSessionCreate
from apps.api.services.job_service import jobs
from packages.prompts import list_prompt_templates


router = APIRouter(tags=["jobs"])
TERMINAL_JOB_STATUSES = {JobStatus.succeeded, JobStatus.failed}


@router.post("/jobs/vlm-label", response_model=JobRecord)
def create_vlm_label_job(payload: JobCreateRequest) -> JobRecord:
    return jobs.create(kind="vlm_label", payload=payload)


@router.post("/jobs/visual-embeddings", response_model=JobRecord)
def create_visual_embedding_job(payload: VisualEmbeddingJobCreateRequest) -> JobRecord:
    return jobs.create(kind="visual_embedding", payload=payload)


@router.post("/jobs/export", response_model=JobRecord)
def create_export_job(payload: ExportCreateRequest) -> JobRecord:
    return jobs.create(kind="export", payload=payload)


@router.post("/jobs/rerun-session", response_model=JobRecord)
def create_rerun_session_job(payload: RerunSessionCreate) -> JobRecord:
    return jobs.create(kind="rerun_session", payload=payload)


@router.get("/jobs/vlm-prompts", response_model=list[PromptTemplateRecord])
def list_vlm_prompts() -> list[PromptTemplateRecord]:
    return [
        PromptTemplateRecord(
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            title=prompt.title,
            description=prompt.description,
            expected_outputs=list(prompt.expected_outputs),
        )
        for prompt in list_prompt_templates()
    ]


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    return jobs.get(job_id)


@router.get("/jobs/{job_id}/events", response_model=None)
def stream_job_events(job_id: str) -> StreamingResponse:
    async def events():
        last_event: str | None = None
        while True:
            try:
                record = jobs.get(job_id)
            except HTTPException as exc:
                yield _sse_event("error", {"status_code": exc.status_code, "detail": exc.detail})
                return

            event = _job_sse_event(record)
            if event != last_event:
                yield event
                last_event = event
            if record.status in TERMINAL_JOB_STATUSES:
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _job_sse_event(record: JobRecord) -> str:
    return _sse_event(
        "job",
        {
            "job_id": record.job_id,
            "kind": record.kind,
            "status": record.status,
            "progress": record.progress,
            "message": record.message,
            "queue_job_id": record.queue_job_id,
            "created_export_id": record.created_export_id,
            "export_format": record.export_format,
            "export_uri": record.export_uri,
            "created_rerun_session_id": record.created_rerun_session_id,
            "rerun_rrd_url": record.rerun_rrd_url,
            "rerun_rrd_path": record.rerun_rrd_path,
            "rerun_viewer_url": record.rerun_viewer_url,
        },
    )


def _sse_event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, sort_keys=True)}\n\n"
