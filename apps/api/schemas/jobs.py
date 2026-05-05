from typing import Any

from pydantic import BaseModel, Field

from apps.api.schemas.common import ExportFormat, JobStatus


class JobCreateRequest(BaseModel):
    dataset_id: str
    episode_indices: list[int] = Field(default_factory=list)
    model: str = "vlm-default"
    prompt_template: str = "episode_autolabel_v1"
    min_keyframes: int = Field(default=8, ge=1, le=128)
    max_keyframes: int = Field(default=16, ge=1, le=256)


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


class VlmResponseRecord(BaseModel):
    response_id: str
    dataset_id: str
    job_id: str
    episode_index: int
    provider: str
    created_at: str
    raw_response: dict[str, Any]


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
    created_export_id: str | None = None
    export_format: ExportFormat | None = None
    export_uri: str | None = None
    created_rerun_session_id: str | None = None
    rerun_rrd_url: str | None = None
    rerun_rrd_path: str | None = None
    rerun_published_uri: str | None = None
    rerun_viewer_url: str | None = None
    queue_job_id: str | None = None
