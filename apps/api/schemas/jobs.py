from pydantic import BaseModel, Field

from apps.api.schemas.common import JobStatus


class JobCreateRequest(BaseModel):
    dataset_id: str
    episode_indices: list[int] = Field(default_factory=list)
    model: str = "vlm-default"
    prompt_template: str = "episode_autolabel_v1"


class VisualEmbeddingJobCreateRequest(BaseModel):
    dataset_id: str
    episode_indices: list[int] = Field(default_factory=list)
    model: str = "deterministic-visual"
    camera_names: list[str] = Field(default_factory=list)
    min_keyframes: int = Field(default=8, ge=1, le=128)
    max_keyframes: int = Field(default=16, ge=1, le=256)


class PromptTemplateRecord(BaseModel):
    prompt_id: str
    version: str
    title: str
    description: str
    expected_outputs: list[str]


class JobRecord(BaseModel):
    job_id: str
    kind: str
    status: JobStatus
    dataset_id: str
    episode_indices: list[int]
    progress: float = 0.0
    message: str | None = None
    created_annotation_ids: list[str] = Field(default_factory=list)
    model: str | None = None
    prompt_template: str | None = None
    prompt_version: str | None = None
    provider: str | None = None
    raw_response_ids: list[str] = Field(default_factory=list)
    raw_response_uri: str | None = None
    created_embedding_ids: list[str] = Field(default_factory=list)
    artifact_count: int = 0
    queue_job_id: str | None = None
