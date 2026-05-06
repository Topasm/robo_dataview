from typing import Any

from pydantic import BaseModel, Field


class DatasetOpenRequest(BaseModel):
    uri: str = Field(..., description="Local path, hf:// URI, s3:// URI, or other Lance location.")
    name: str | None = Field(default=None, description="Optional display name.")


class DatasetRecord(BaseModel):
    dataset_id: str
    name: str
    uri: str
    status: str
    message: str | None = None


class DatasetSummary(BaseModel):
    dataset_id: str
    name: str
    uri: str
    status: str
    episode_count: int
    frame_count: int
    fps: float | None = None
    camera_names: list[str]
    camera_info: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Per-camera encoding metadata sourced from a sibling LeRobot "
            "meta/info.json when present (codec, fps, resolution, channels). "
            "Null when the dataset does not ship info.json."
        ),
    )
    reviewed_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    message: str | None = None


class DatasetTableHealth(BaseModel):
    table: str
    present: bool
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    missing_required_columns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DatasetHealth(BaseModel):
    dataset_id: str
    ok: bool
    status: str
    storage_model: str
    episode_count: int = 0
    frame_count: int = 0
    camera_count: int = 0
    tables: list[DatasetTableHealth] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
