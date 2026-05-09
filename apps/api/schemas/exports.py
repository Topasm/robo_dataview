from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.schemas.common import ExportFormat, JobStatus


class ExportCreateRequest(BaseModel):
    dataset_id: str
    episode_indices: list[int] = Field(default_factory=list)
    splits: list[str] = Field(default_factory=list)
    format: ExportFormat = ExportFormat.lance
    version_description: str | None = None
    publish_uri: str | None = None
    clip_label_type: str | None = "skill"
    accepted_clips_only: bool = True
    materialize_skill_clips: bool = False
    jitter_offsets: list[int] = Field(default_factory=lambda: [0])
    copies_per_clip: int = Field(default=1, ge=1)


class ExportRecord(BaseModel):
    export_id: str
    dataset_id: str
    episode_indices: list[int]
    format: ExportFormat
    status: JobStatus
    output_uri: str | None = None
    message: str | None = None
    artifacts: dict | None = None
    num_episodes: int = 0
    created_at: datetime | None = None


class ExportHubUploadRequest(BaseModel):
    repo_id: str | None = None
    private: bool | None = None
    revision: str | None = None


class ExportHubUploadResponse(BaseModel):
    export_id: str
    repo_id: str
    repo_url: str
    uploaded_path: str
    revision: str | None = None
    commit_url: str | None = None
    message: str
