from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from apps.api.schemas.annotations import AnnotationCreate, AnnotationRecord, AnnotationUpdate
from apps.api.services.pydantic_compat import model_dump
from packages.robot_schema import build_annotations_pyarrow_schema


ANNOTATION_STORAGE_ROOT = Path("data/lance/annotations")


class AnnotationStore:
    def __init__(
        self,
        storage_root: Path = ANNOTATION_STORAGE_ROOT,
        *,
        persist: bool = True,
        mirror_lance: bool = True,
    ) -> None:
        self.storage_root = storage_root
        self.persist = persist
        self.mirror_lance = mirror_lance
        self._records: dict[str, AnnotationRecord] = {}
        if self.persist:
            self._load_records()

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
            **model_dump(payload),
        )
        self._records[record.annotation_id] = record
        self._persist_dataset(record.dataset_id)
        return record

    def update(self, annotation_id: str, payload: AnnotationUpdate) -> AnnotationRecord | None:
        existing = self._records.get(annotation_id)
        if existing is None:
            return None
        update_data = model_dump(payload, exclude_unset=True)
        update_data.pop("updated_by", None)
        merged = model_dump(existing)
        merged.update(update_data)
        if merged["end_frame"] < merged["start_frame"]:
            raise ValueError("end_frame must be greater than or equal to start_frame")
        merged["updated_at"] = datetime.now(timezone.utc)
        record = AnnotationRecord(**merged)
        self._records[annotation_id] = record
        self._persist_dataset(record.dataset_id)
        return record

    def delete(self, annotation_id: str) -> bool:
        existing = self._records.pop(annotation_id, None)
        if existing is None:
            return False
        self._persist_dataset(existing.dataset_id)
        return True

    def storage_paths(self, dataset_id: str) -> dict[str, str]:
        dataset_dir = self._dataset_dir(dataset_id)
        return {
            "jsonl": str(dataset_dir / "annotations.jsonl"),
            "lance": str(dataset_dir / "annotations.lance"),
        }

    def _load_records(self) -> None:
        if not self.storage_root.exists():
            return
        for jsonl_path in self.storage_root.glob("*/annotations.jsonl"):
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = AnnotationRecord(**json.loads(line))
                self._records[record.annotation_id] = record

    def _persist_dataset(self, dataset_id: str) -> None:
        if not self.persist:
            return
        dataset_dir = self._dataset_dir(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        records = self.list(dataset_id=dataset_id, episode_index=None)
        jsonl_path = dataset_dir / "annotations.jsonl"
        lines = [json.dumps(self._json_row(record), sort_keys=True) for record in records]
        jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        self._mirror_lance(dataset_dir / "annotations.lance", records)

    def _mirror_lance(self, lance_path: Path, records: list[AnnotationRecord]) -> None:
        if not self.mirror_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_annotations_pyarrow_schema()
        rows = [self._lance_row(record) for record in records]
        if rows:
            table = pa.Table.from_pylist(rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")

    def _dataset_dir(self, dataset_id: str) -> Path:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_id).strip("._-")
        digest = hashlib.sha1(dataset_id.encode("utf-8")).hexdigest()[:12]
        return self.storage_root / f"{slug[:80] or 'dataset'}-{digest}"

    @staticmethod
    def _json_row(record: AnnotationRecord) -> dict[str, object]:
        return {
            **model_dump(record),
            "source": record.source.value,
            "review_status": record.review_status.value,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def _lance_row(record: AnnotationRecord) -> dict[str, object]:
        return {
            **model_dump(record),
            "source": record.source.value,
            "review_status": record.review_status.value,
        }


annotation_store = AnnotationStore()
