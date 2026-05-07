from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field

try:
    from pydantic import model_validator
except ImportError:  # Pydantic v1 compatibility for system Python test environments.
    model_validator = None
    from pydantic import root_validator
else:
    root_validator = None

from apps.api.schemas.common import ReviewStatus


_ALLOWED_DISPOSITIONS = {"kept", "deleted", "flagged"}


class EpisodeListItem(BaseModel):
    dataset_id: str
    episode_index: int
    task_index: int | None = None
    length: int | None = None
    success_label: bool | None = None
    quality_score: float | None = None
    review_status: str = "pending"
    caption: str | None = None
    failure_reason: str | None = None
    has_vlm_label: bool = False
    has_human_label: bool = False
    split: str | None = None
    fps: float | None = None
    camera_names: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    language_instruction: str | None = None
    disposition: str | None = None
    disposition_reason: str | None = None
    disposition_updated_at: datetime | None = None
    dirty_annotation_count: int = 0


class EpisodeListPage(BaseModel):
    dataset_id: str
    items: list[EpisodeListItem]
    total: int
    limit: int
    offset: int
    next_offset: int | None = None
    previous_offset: int | None = None
    sort_by: str = "episode_index"
    sort_order: str = "asc"
    filter_query: str | None = None


class EpisodeDetail(EpisodeListItem):
    pass


class StateActionSummary(BaseModel):
    dataset_id: str
    episode_index: int
    frame_count: int
    state_dim: int | None = None
    action_dim: int | None = None
    state_norm_min: float | None = None
    state_norm_max: float | None = None
    action_norm_min: float | None = None
    action_norm_max: float | None = None


class EpisodeTimeseries(BaseModel):
    dataset_id: str
    episode_index: int
    frame_count: int
    fps: float | None = None
    sample_count: int
    sample_indices: list[int]
    timestamps: list[float | None] | None = None
    state_norms: list[float | None]
    action_norms: list[float | None]
    state_values: list[list[float | None] | None] = Field(default_factory=list)
    action_values: list[list[float | None] | None] = Field(default_factory=list)
    state_dim: int | None = None
    action_dim: int | None = None


class EpisodeLabelUpdate(BaseModel):
    caption: str | None = None
    success_label: bool | None = None
    failure_reason: str | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    split: str | None = None
    review_status: ReviewStatus | None = None
    language_instruction: str | None = None
    updated_by: str | None = None


class EpisodeDispositionUpdate(BaseModel):
    disposition: str | None = None
    reason: str | None = None
    updated_by: str | None = None

    if model_validator is not None:

        @model_validator(mode="after")
        def validate_disposition(self) -> Self:
            if self.disposition is not None and self.disposition not in _ALLOWED_DISPOSITIONS:
                raise ValueError(
                    "disposition must be one of 'kept', 'deleted', 'flagged' or null"
                )
            return self

    else:

        @root_validator(skip_on_failure=True)  # type: ignore[misc]
        def validate_disposition(cls, values: dict[str, Any]) -> dict[str, Any]:
            disposition = values.get("disposition")
            if disposition is not None and disposition not in _ALLOWED_DISPOSITIONS:
                raise ValueError(
                    "disposition must be one of 'kept', 'deleted', 'flagged' or null"
                )
            return values


class EpisodeLabelHistoryRecord(BaseModel):
    event_id: str
    dataset_id: str
    episode_index: int
    action: str
    actor: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: datetime
