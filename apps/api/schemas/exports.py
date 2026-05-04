from pydantic import BaseModel, Field

from apps.api.schemas.common import ExportFormat, JobStatus


class ExportCreateRequest(BaseModel):
    dataset_id: str
    episode_indices: list[int] = Field(default_factory=list)
    splits: list[str] = Field(default_factory=list)
    format: ExportFormat = ExportFormat.lerobot
    version_description: str | None = None
    publish_uri: str | None = None


class ExportRecord(BaseModel):
    export_id: str
    dataset_id: str
    episode_indices: list[int]
    format: ExportFormat
    status: JobStatus
    output_uri: str | None = None
    message: str | None = None
    artifacts: dict | None = None
