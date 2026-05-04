from fastapi import APIRouter

from apps.api.schemas.jobs import (
    JobCreateRequest,
    JobRecord,
    PromptTemplateRecord,
    VisualEmbeddingJobCreateRequest,
)
from apps.api.services.job_service import jobs
from packages.prompts import list_prompt_templates


router = APIRouter(tags=["jobs"])


@router.post("/jobs/vlm-label", response_model=JobRecord)
def create_vlm_label_job(payload: JobCreateRequest) -> JobRecord:
    return jobs.create(kind="vlm_label", payload=payload)


@router.post("/jobs/visual-embeddings", response_model=JobRecord)
def create_visual_embedding_job(payload: VisualEmbeddingJobCreateRequest) -> JobRecord:
    return jobs.create(kind="visual_embedding", payload=payload)


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
