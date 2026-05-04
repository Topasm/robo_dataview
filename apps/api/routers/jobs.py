from fastapi import APIRouter

from apps.api.schemas.jobs import JobCreateRequest, JobRecord
from apps.api.services.job_service import jobs


router = APIRouter(tags=["jobs"])


@router.post("/jobs/vlm-label", response_model=JobRecord)
def create_vlm_label_job(payload: JobCreateRequest) -> JobRecord:
    return jobs.create(kind="vlm_label", payload=payload)


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    return jobs.get(job_id)
