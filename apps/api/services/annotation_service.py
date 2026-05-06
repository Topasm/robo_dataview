from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from apps.api.schemas.annotations import (
    AnnotationCreate,
    AnnotationHistoryRecord,
    AnnotationRecord,
    AnnotationUpdate,
)
from apps.api.services.pydantic_compat import model_dump
from packages.robot_schema import (
    build_annotation_events_pyarrow_schema,
    build_annotations_current_pyarrow_schema,
    build_annotations_pyarrow_schema,
)


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
        self._history: list[AnnotationHistoryRecord] = []
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
            updated_by=payload.created_by,
            revision=1,
            **model_dump(payload),
        )
        self._records[record.annotation_id] = record
        self._append_history(
            dataset_id=record.dataset_id,
            annotation_id=record.annotation_id,
            episode_index=record.episode_index,
            action="create",
            actor=record.created_by,
            before=None,
            after=self._json_row(record),
        )
        self._persist_dataset(record.dataset_id)
        return record

    def update(self, annotation_id: str, payload: AnnotationUpdate) -> AnnotationRecord | None:
        existing = self._records.get(annotation_id)
        if existing is None:
            return None
        update_data = model_dump(payload, exclude_unset=True)
        actor = str(update_data.pop("updated_by", None) or "local")
        merged = model_dump(existing)
        merged.update(update_data)
        if merged["end_frame"] < merged["start_frame"]:
            raise ValueError("end_frame must be greater than or equal to start_frame")
        merged["updated_at"] = datetime.now(timezone.utc)
        merged["updated_by"] = actor
        merged["revision"] = int(merged.get("revision") or 1) + 1
        record = AnnotationRecord(**merged)
        self._records[annotation_id] = record
        self._append_history(
            dataset_id=record.dataset_id,
            annotation_id=record.annotation_id,
            episode_index=record.episode_index,
            action="update",
            actor=actor,
            before=self._json_row(existing),
            after=self._json_row(record),
        )
        self._persist_dataset(record.dataset_id)
        return record

    def delete(self, annotation_id: str, *, actor: str = "local") -> bool:
        existing = self._records.pop(annotation_id, None)
        if existing is None:
            return False
        self._append_history(
            dataset_id=existing.dataset_id,
            annotation_id=existing.annotation_id,
            episode_index=existing.episode_index,
            action="delete",
            actor=actor,
            before=self._json_row(existing),
            after=None,
        )
        self._persist_dataset(existing.dataset_id)
        return True

    def list_history(
        self,
        dataset_id: str,
        *,
        episode_index: int | None = None,
        annotation_id: str | None = None,
    ) -> list[AnnotationHistoryRecord]:
        return [
            event
            for event in self._history
            if event.dataset_id == dataset_id
            and (episode_index is None or event.episode_index == episode_index)
            and (annotation_id is None or event.annotation_id == annotation_id)
        ]

    def storage_paths(self, dataset_id: str) -> dict[str, str]:
        dataset_dir = self._dataset_dir(dataset_id)
        return {
            "jsonl": str(dataset_dir / "annotations.jsonl"),
            "lance": str(dataset_dir / "annotations.lance"),
            "current_lance": str(dataset_dir / "annotations_current.lance"),
            "events_lance": str(dataset_dir / "annotation_events.lance"),
            "history": str(dataset_dir / "history.jsonl"),
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
        for history_path in self.storage_root.glob("*/history.jsonl"):
            for line in history_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                self._history.append(AnnotationHistoryRecord(**json.loads(line)))

    def _persist_dataset(self, dataset_id: str) -> None:
        if not self.persist:
            return
        dataset_dir = self._dataset_dir(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        records = self.list(dataset_id=dataset_id, episode_index=None)
        jsonl_path = dataset_dir / "annotations.jsonl"
        lines = [json.dumps(self._json_row(record), sort_keys=True) for record in records]
        _atomic_write_text(jsonl_path, "\n".join(lines) + ("\n" if lines else ""))
        self._mirror_current_lance(dataset_dir / "annotations_current.lance", records)
        # Keep the original path during the transition so older tools/tests that
        # expect annotations.lance still see the current view.
        self._mirror_lance(dataset_dir / "annotations.lance", records)

    def _append_history(
        self,
        *,
        dataset_id: str,
        annotation_id: str,
        episode_index: int,
        action: str,
        actor: str,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
    ) -> None:
        event = AnnotationHistoryRecord(
            event_id=str(uuid4()),
            dataset_id=dataset_id,
            annotation_id=annotation_id,
            episode_index=episode_index,
            action=action,
            actor=actor,
            before=before,
            after=after,
            created_at=datetime.now(timezone.utc),
        )
        self._history.append(event)
        if not self.persist:
            return
        dataset_dir = self._dataset_dir(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        history_path = dataset_dir / "history.jsonl"
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._history_json_row(event), sort_keys=True) + "\n")
        self._mirror_events_lance(dataset_dir / "annotation_events.lance", dataset_id)

    def _mirror_current_lance(self, lance_path: Path, records: list[AnnotationRecord]) -> None:
        if not self.mirror_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_annotations_current_pyarrow_schema()
        rows = [self._lance_row(record) for record in records]
        if rows:
            table = pa.Table.from_pylist(rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")

    def _mirror_events_lance(self, lance_path: Path, dataset_id: str) -> None:
        if not self.mirror_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_annotation_events_pyarrow_schema()
        rows = [
            self._history_lance_row(event)
            for event in self._history
            if event.dataset_id == dataset_id
        ]
        if rows:
            table = pa.Table.from_pylist(rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")

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
            "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
            "lock_expires_at": (
                record.lock_expires_at.isoformat() if record.lock_expires_at else None
            ),
        }

    @staticmethod
    def _history_json_row(record: AnnotationHistoryRecord) -> dict[str, object]:
        return {
            **model_dump(record),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _history_lance_row(record: AnnotationHistoryRecord) -> dict[str, object]:
        return {
            "event_id": record.event_id,
            "annotation_id": record.annotation_id,
            "dataset_id": record.dataset_id,
            "episode_index": record.episode_index,
            "action": record.action,
            "actor": record.actor,
            "before_json": (
                json.dumps(record.before, sort_keys=True)
                if record.before is not None
                else None
            ),
            "after_json": (
                json.dumps(record.after, sort_keys=True)
                if record.after is not None
                else None
            ),
            "created_at": record.created_at,
        }

    @staticmethod
    def _lance_row(record: AnnotationRecord) -> dict[str, object]:
        return {
            **model_dump(record),
            "source": record.source.value,
            "review_status": record.review_status.value,
        }


annotation_store = AnnotationStore()


def _atomic_write_text(path: Path, text: str) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)
