from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.schemas.annotations import (
    AnnotationAssignmentUpdate,
    AnnotationCreate,
    AnnotationHistoryRecord,
    AnnotationRecord,
    AnnotationUpdate,
)
from apps.api.services.annotation_service import annotation_store
from apps.api.services.pydantic_compat import model_copy
from apps.api.services.user_context import current_user_id


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
def create_annotation(
    payload: AnnotationCreate,
    user_id: str = Depends(current_user_id),
) -> AnnotationRecord:
    if payload.created_by == "local":
        payload = model_copy(payload, update={"created_by": user_id})
    return annotation_store.create(payload)


@router.patch("/annotations/{annotation_id}", response_model=AnnotationRecord)
def update_annotation(
    annotation_id: str,
    payload: AnnotationUpdate,
    user_id: str = Depends(current_user_id),
) -> AnnotationRecord:
    if payload.updated_by is None:
        payload = model_copy(payload, update={"updated_by": user_id})
    record = annotation_store.update(annotation_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return record


@router.patch("/annotations/{annotation_id}/assignment", response_model=AnnotationRecord)
def assign_annotation(
    annotation_id: str,
    payload: AnnotationAssignmentUpdate,
    user_id: str = Depends(current_user_id),
) -> AnnotationRecord:
    update = AnnotationUpdate(
        assigned_to=payload.assigned_to,
        updated_by=payload.updated_by or user_id,
    )
    record = annotation_store.update(annotation_id, update)
    if record is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return record


@router.delete("/annotations/{annotation_id}")
def delete_annotation(
    annotation_id: str,
    user_id: str = Depends(current_user_id),
) -> dict[str, str]:
    deleted = annotation_store.delete(annotation_id, actor=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "deleted"}
