from fastapi import APIRouter, HTTPException, Query

from apps.api.schemas.annotations import (
    AnnotationCreate,
    AnnotationHistoryRecord,
    AnnotationRecord,
    AnnotationUpdate,
)
from apps.api.services.annotation_service import annotation_store


router = APIRouter(tags=["annotations"])


@router.get("/annotations", response_model=list[AnnotationRecord])
def list_annotations(
    dataset_id: str = Query(...),
    episode_index: int | None = Query(default=None),
) -> list[AnnotationRecord]:
    return annotation_store.list(dataset_id=dataset_id, episode_index=episode_index)


@router.get("/annotations/history", response_model=list[AnnotationHistoryRecord])
def list_annotation_history(
    dataset_id: str = Query(...),
    episode_index: int | None = Query(default=None),
    annotation_id: str | None = Query(default=None),
) -> list[AnnotationHistoryRecord]:
    return annotation_store.list_history(
        dataset_id=dataset_id,
        episode_index=episode_index,
        annotation_id=annotation_id,
    )


@router.post("/annotations", response_model=AnnotationRecord)
def create_annotation(payload: AnnotationCreate) -> AnnotationRecord:
    return annotation_store.create(payload)


@router.patch("/annotations/{annotation_id}", response_model=AnnotationRecord)
def update_annotation(annotation_id: str, payload: AnnotationUpdate) -> AnnotationRecord:
    record = annotation_store.update(annotation_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return record


@router.delete("/annotations/{annotation_id}")
def delete_annotation(annotation_id: str) -> dict[str, str]:
    deleted = annotation_store.delete(annotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "deleted"}
