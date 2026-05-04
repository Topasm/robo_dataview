from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from apps.api.schemas.annotations import AnnotationCreate, AnnotationRecord, AnnotationUpdate


class AnnotationStore:
    def __init__(self) -> None:
        self._records: dict[str, AnnotationRecord] = {}

    def list(self, dataset_id: str, episode_index: int | None) -> list[AnnotationRecord]:
        records = [
            record
            for record in self._records.values()
            if record.dataset_id == dataset_id
            and (episode_index is None or record.episode_index == episode_index)
        ]
        return sorted(records, key=lambda record: (record.episode_index, record.start_frame))

    def create(self, payload: AnnotationCreate) -> AnnotationRecord:
        now = datetime.now(timezone.utc)
        record = AnnotationRecord(
            annotation_id=str(uuid4()),
            created_at=now,
            updated_at=now,
            **payload.dict(),
        )
        self._records[record.annotation_id] = record
        return record

    def update(self, annotation_id: str, payload: AnnotationUpdate) -> AnnotationRecord | None:
        existing = self._records.get(annotation_id)
        if existing is None:
            return None
        update_data = payload.dict(exclude_unset=True)
        update_data.pop("updated_by", None)
        merged = existing.dict()
        merged.update(update_data)
        if merged["end_frame"] < merged["start_frame"]:
            raise ValueError("end_frame must be greater than or equal to start_frame")
        merged["updated_at"] = datetime.now(timezone.utc)
        record = AnnotationRecord(**merged)
        self._records[annotation_id] = record
        return record

    def delete(self, annotation_id: str) -> bool:
        return self._records.pop(annotation_id, None) is not None


annotation_store = AnnotationStore()
