from fastapi import APIRouter, HTTPException, Query

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.common import ReviewStatus
from apps.api.schemas.frames import FrameLabel, FrameListResponse, FrameRecord
from apps.api.services.annotation_service import annotation_store
from apps.api.services.lance_store import store
from apps.api.services.pydantic_compat import model_copy

router = APIRouter(tags=["frames"])


@router.get("/frames", response_model=FrameListResponse)
def list_frames(
    dataset_id: str = Query(...),
    episode_index: int = Query(..., ge=0),
    start_frame: int = Query(default=0, ge=0),
    end_frame: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> FrameListResponse:
    if end_frame is not None and end_frame < start_frame:
        raise HTTPException(
            status_code=400,
            detail="end_frame must be greater than or equal to start_frame",
        )

    episode = store.get_episode(dataset_id, episode_index)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    frames = store.list_frames(
        dataset_id,
        episode_index,
        start_frame=start_frame,
        end_frame=end_frame,
        limit=limit,
    )
    if frames is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    annotations = annotation_store.list(dataset_id=dataset_id, episode_index=episode_index)
    items = [_with_annotation_labels(frame, annotations) for frame in frames]
    inferred_count = max((frame.frame_index for frame in items), default=-1) + 1
    return FrameListResponse(
        dataset_id=dataset_id,
        episode_index=episode_index,
        frame_count=episode.length or inferred_count,
        start_frame=start_frame,
        end_frame=end_frame,
        limit=limit,
        returned_count=len(items),
        items=items,
    )


BAD_FRAME_LABEL_TYPES = {"bad_frame", "bad_range", "bad_episode"}


def _with_annotation_labels(frame: FrameRecord, annotations: list[AnnotationRecord]) -> FrameRecord:
    labels: list[FrameLabel] = []
    has_bad_label = False
    for annotation in annotations:
        if annotation.start_frame <= frame.frame_index <= annotation.end_frame:
            labels.append(
                FrameLabel(
                    annotation_id=annotation.annotation_id,
                    label_type=annotation.label_type,
                    label_value=annotation.label_value,
                    source=annotation.source,
                    confidence=annotation.confidence,
                    review_status=annotation.review_status,
                )
            )
            if (
                annotation.label_type in BAD_FRAME_LABEL_TYPES
                and annotation.review_status != ReviewStatus.rejected
            ):
                has_bad_label = True
    return model_copy(
        frame,
        update={
            "labels": labels,
            "is_bad_frame": frame.is_bad_frame or has_bad_label,
        },
    )
