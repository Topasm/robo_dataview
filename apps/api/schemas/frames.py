from __future__ import annotations

from pydantic import BaseModel, Field

from apps.api.schemas.common import AnnotationSource, ReviewStatus


class FrameLabel(BaseModel):
    annotation_id: str
    label_type: str
    label_value: str
    source: AnnotationSource
    confidence: float
    review_status: ReviewStatus


class FrameRecord(BaseModel):
    dataset_id: str
    episode_index: int
    frame_index: int = Field(..., ge=0)
    timestamp: float | None = None
    task_index: int | None = None
    observation_state: list[float] | None = None
    action: list[float] | None = None
    state_norm: float | None = None
    action_norm: float | None = None
    is_bad_frame: bool = False
    labels: list[FrameLabel] = Field(default_factory=list)


class FrameUpdate(BaseModel):
    is_bad_frame: bool | None = None
    label_value: str | None = Field(default=None, min_length=1)
    updated_by: str = "local"


class FrameListResponse(BaseModel):
    dataset_id: str
    episode_index: int
    frame_count: int
    start_frame: int
    end_frame: int | None
    limit: int
    returned_count: int
    items: list[FrameRecord]
