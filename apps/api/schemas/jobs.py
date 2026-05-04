from pydantic import BaseModel, Field

from apps.api.schemas.common import JobStatus


class JobCreateRequest(BaseModel):
    dataset_id: str
    episode_indices: list[int] = Field(default_factory=list)
    model: str = "vlm-default"
    prompt_template: str = "episode_autolabel_v1"


class JobRecord(BaseModel):
    job_id: str
    kind: str
    status: JobStatus
    dataset_id: str
    episode_indices: list[int]
    progress: float = 0.0
    message: str | None = None
