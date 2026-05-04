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
    reviewed_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    message: str | None = None
