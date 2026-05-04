from fastapi import APIRouter, HTTPException, Path, Query

from apps.api.schemas.annotations import AnnotationCreate, AnnotationRecord, AnnotationUpdate
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.frames import FrameLabel, FrameListResponse, FrameRecord, FrameUpdate
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


@router.patch("/frames/{frame_index}", response_model=FrameRecord)
def update_frame(
    payload: FrameUpdate,
    frame_index: int = Path(..., ge=0),
    dataset_id: str = Query(...),
    episode_index: int = Query(..., ge=0),
) -> FrameRecord:
    if payload.is_bad_frame is None and payload.label_type is None:
        raise HTTPException(status_code=400, detail="No frame mutation requested")

    episode = store.get_episode(dataset_id, episode_index)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.length is not None and frame_index >= episode.length:
        raise HTTPException(status_code=404, detail="Frame not found")

    frames = store.list_frames(
        dataset_id,
        episode_index,
        start_frame=frame_index,
        end_frame=frame_index,
        limit=1,
    )
    if frames is None or not frames:
        raise HTTPException(status_code=404, detail="Frame not found")

    if payload.is_bad_frame is not None:
        _set_bad_frame_annotation(dataset_id, episode_index, frame_index, payload)
    if payload.label_type is not None:
        _set_exact_frame_annotation(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_index=frame_index,
            label_type=payload.label_type,
            label_value=payload.label_value or payload.label_type,
            enabled=True if payload.label_enabled is None else payload.label_enabled,
            updated_by=payload.updated_by,
        )
    annotations = annotation_store.list(dataset_id=dataset_id, episode_index=episode_index)
    return _with_annotation_labels(frames[0], annotations)


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


def _set_bad_frame_annotation(
    dataset_id: str,
    episode_index: int,
    frame_index: int,
    payload: FrameUpdate,
) -> None:
    _set_exact_frame_annotation(
        dataset_id=dataset_id,
        episode_index=episode_index,
        frame_index=frame_index,
        label_type="bad_frame",
        label_value=payload.label_value or "bad_frame",
        enabled=bool(payload.is_bad_frame),
        updated_by=payload.updated_by,
    )


def _set_exact_frame_annotation(
    *,
    dataset_id: str,
    episode_index: int,
    frame_index: int,
    label_type: str,
    label_value: str,
    enabled: bool,
    updated_by: str,
) -> None:
    annotations = annotation_store.list(dataset_id=dataset_id, episode_index=episode_index)
    existing = [
        annotation
        for annotation in annotations
        if annotation.start_frame == frame_index
        and annotation.end_frame == frame_index
        and annotation.label_type == label_type
    ]
    if enabled:
        if existing:
            annotation_store.update(
                existing[0].annotation_id,
                AnnotationUpdate(
                    label_value=label_value,
                    review_status=ReviewStatus.accepted,
                    updated_by=updated_by,
                ),
            )
            return
        annotation_store.create(
            AnnotationCreate(
                dataset_id=dataset_id,
                episode_index=episode_index,
                start_frame=frame_index,
                end_frame=frame_index,
                label_type=label_type,
                label_value=label_value,
                source=AnnotationSource.human,
                confidence=1.0,
                review_status=ReviewStatus.accepted,
                created_by=updated_by,
            )
        )
        return

    for annotation in existing:
        annotation_store.update(
            annotation.annotation_id,
            AnnotationUpdate(
                review_status=ReviewStatus.rejected,
                updated_by=updated_by,
            ),
        )
