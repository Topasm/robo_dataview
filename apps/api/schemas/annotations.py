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

from apps.api.schemas.common import AnnotationSource, ReviewStatus


class AnnotationCreate(BaseModel):
    dataset_id: str
    episode_index: int = Field(..., ge=0)
    start_frame: int = Field(..., ge=0)
    end_frame: int = Field(..., ge=0)
    label_type: str
    label_value: str
    source: AnnotationSource = AnnotationSource.human
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    review_status: ReviewStatus = ReviewStatus.pending
    created_by: str = "local"
    assigned_to: str | None = None

    if model_validator is not None:

        @model_validator(mode="after")
        def validate_range(self) -> Self:
            if self.end_frame < self.start_frame:
                raise ValueError("end_frame must be greater than or equal to start_frame")
            return self

    else:

        @root_validator(skip_on_failure=True)  # type: ignore[misc]
        def validate_range(cls, values: dict[str, Any]) -> dict[str, Any]:
            if int(values["end_frame"]) < int(values["start_frame"]):
                raise ValueError("end_frame must be greater than or equal to start_frame")
            return values


class AnnotationUpdate(BaseModel):
    start_frame: int | None = Field(default=None, ge=0)
    end_frame: int | None = Field(default=None, ge=0)
    label_type: str | None = None
    label_value: str | None = None
    source: AnnotationSource | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    review_status: ReviewStatus | None = None
    assigned_to: str | None = None
    updated_by: str | None = None


class AnnotationAssignmentUpdate(BaseModel):
    assigned_to: str | None = None
    updated_by: str | None = None


class AnnotationRecord(BaseModel):
    annotation_id: str
    dataset_id: str
    episode_index: int
    start_frame: int
    end_frame: int
    label_type: str
    label_value: str
    source: AnnotationSource
    confidence: float
    review_status: ReviewStatus
    created_by: str
    updated_by: str = "local"
    assigned_to: str | None = None
    revision: int = 1
    deleted_at: datetime | None = None
    lock_owner: str | None = None
    lock_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AnnotationHistoryRecord(BaseModel):
    event_id: str
    dataset_id: str
    annotation_id: str
    episode_index: int
    action: str
    actor: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: datetime
