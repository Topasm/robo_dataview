from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from apps.api.schemas.annotations import (
    AnnotationCreate,
    AnnotationHistoryRecord,
    AnnotationRecord,
    AnnotationUpdate,
)
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.services.pydantic_compat import model_copy, model_dump
from packages.robot_schema import (
    build_annotation_events_pyarrow_schema,
    build_annotations_current_pyarrow_schema,
    build_annotations_pyarrow_schema,
)


EPISODE_DISPOSITION_LABEL_TYPE = "episode_disposition"


ANNOTATION_STORAGE_ROOT = Path("data/lance/annotations")


class AnnotationConflictError(RuntimeError):
    pass


class AnnotationStore:
    def __init__(
        self,
        storage_root: Path = ANNOTATION_STORAGE_ROOT,
        *,
        persist: bool = True,
        mirror_lance: bool = True,
        write_legacy_lance_mirror: bool | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.persist = persist
        self.mirror_lance = mirror_lance
        self.write_legacy_lance_mirror = (
            _env_flag("ROBOT_DATA_STUDIO_WRITE_LEGACY_ANNOTATIONS_LANCE", default=True)
            if write_legacy_lance_mirror is None
            else write_legacy_lance_mirror
        )
        self._records: dict[str, AnnotationRecord] = {}
        self._history: list[AnnotationHistoryRecord] = []
        if self.persist:
            self._load_records()

    def get(self, annotation_id: str) -> AnnotationRecord | None:
        return self._records.get(annotation_id)

    def list(self, dataset_id: str, episode_index: int | None) -> list[AnnotationRecord]:
        records = [
            record
            for record in self._records.values()
            if record.dataset_id == dataset_id
            and (episode_index is None or record.episode_index == episode_index)
            and record.deleted_at is None
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

    def update(
        self,
        annotation_id: str,
        payload: AnnotationUpdate,
        *,
        action: str | None = None,
    ) -> AnnotationRecord | None:
        existing = self._records.get(annotation_id)
        if existing is None or existing.deleted_at is not None:
            return None
        update_data = model_dump(payload, exclude_unset=True)
        expected_revision = update_data.pop("expected_revision", None)
        if (
            expected_revision is not None
            and int(expected_revision) != int(existing.revision)
        ):
            raise AnnotationConflictError(
                f"annotation revision mismatch: expected {expected_revision}, current {existing.revision}"
            )
        actor = str(update_data.pop("updated_by", None) or "local")
        if update_data.get("metadata") is None:
            update_data.pop("metadata", None)
        action = action or _annotation_update_action(update_data)
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
            action=action,
            actor=actor,
            before=self._json_row(existing),
            after=self._json_row(record),
        )
        self._persist_dataset(record.dataset_id)
        return record

    def mark_applied(
        self,
        annotation_ids: list[str],
        *,
        export_id: str,
        actor: str = "local",
    ) -> list[AnnotationRecord]:
        """Stamp `applied_export_id` on the given annotations and persist once.

        Best-effort: silently skips ids that are missing or soft-deleted. Bumps
        revision and updated_at, appends an audit event per id, then writes
        JSONL + Lance mirrors a single time per touched dataset_id.
        """

        if not annotation_ids:
            return []
        now = datetime.now(timezone.utc)
        updated: list[AnnotationRecord] = []
        touched_datasets: set[str] = set()
        for annotation_id in annotation_ids:
            existing = self._records.get(annotation_id)
            if existing is None or existing.deleted_at is not None:
                continue
            if existing.applied_export_id == export_id:
                continue
            merged = model_dump(existing)
            merged["applied_export_id"] = export_id
            merged["updated_at"] = now
            merged["updated_by"] = actor
            merged["revision"] = int(merged.get("revision") or 1) + 1
            record = AnnotationRecord(**merged)
            self._records[annotation_id] = record
            self._append_history(
                dataset_id=record.dataset_id,
                annotation_id=record.annotation_id,
                episode_index=record.episode_index,
                action="apply",
                actor=actor,
                before=self._json_row(existing),
                after=self._json_row(record),
            )
            updated.append(record)
            touched_datasets.add(record.dataset_id)
        for dataset_id in touched_datasets:
            self._persist_dataset(dataset_id)
        return updated

    def compact_dataset(
        self,
        dataset_id: str,
        *,
        keep_history: bool = False,
    ) -> dict[str, Any]:
        """Drop soft-deleted tombstones and optionally audit history for a dataset.

        Normal annotation edits keep tombstones/history so local review can audit
        changes. After a curated export is safely uploaded, the UI can call this
        to make the local overlay match the currently active annotation state.
        """

        records_before = self._dataset_records(dataset_id)
        history_before = [
            event for event in self._history if event.dataset_id == dataset_id
        ]
        deleted_ids = {
            record.annotation_id
            for record in records_before
            if record.deleted_at is not None
        }
        for annotation_id in deleted_ids:
            self._records.pop(annotation_id, None)
        if not keep_history:
            self._history = [
                event for event in self._history if event.dataset_id != dataset_id
            ]

        self._persist_dataset(dataset_id)
        self._rewrite_history_dataset(dataset_id)

        records_after = self._dataset_records(dataset_id)
        history_after = [
            event for event in self._history if event.dataset_id == dataset_id
        ]
        return {
            "dataset_id": dataset_id,
            "active_records": len(records_after),
            "records_before": len(records_before),
            "records_pruned": len(records_before) - len(records_after),
            "deleted_records_pruned": len(deleted_ids),
            "history_events_before": len(history_before),
            "history_events_after": len(history_after),
            "history_events_pruned": len(history_before) - len(history_after),
            "history_kept": keep_history,
        }

    def delete(
        self,
        annotation_id: str,
        *,
        actor: str = "local",
        expected_revision: int | None = None,
    ) -> bool:
        existing = self._records.get(annotation_id)
        if existing is None or existing.deleted_at is not None:
            return False
        if (
            expected_revision is not None
            and int(expected_revision) != int(existing.revision)
        ):
            raise AnnotationConflictError(
                f"annotation revision mismatch: expected {expected_revision}, current {existing.revision}"
            )
        now = datetime.now(timezone.utc)
        record = model_copy(
            existing,
            update={
                "deleted_at": now,
                "updated_at": now,
                "updated_by": actor,
                "revision": existing.revision + 1,
            },
        )
        self._records[annotation_id] = record
        self._append_history(
            dataset_id=record.dataset_id,
            annotation_id=record.annotation_id,
            episode_index=record.episode_index,
            action="delete",
            actor=actor,
            before=self._json_row(existing),
            after=None,
        )
        self._persist_dataset(record.dataset_id)
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

    def upsert_episode_disposition(
        self,
        *,
        dataset_id: str,
        episode_index: int,
        disposition: str | None,
        reason: str | None,
        actor: str = "local",
    ) -> dict[str, Any] | None:
        existing = self._find_active_disposition(dataset_id, episode_index)
        if disposition is None:
            if existing is None:
                return None
            self.delete(existing.annotation_id, actor=actor)
            return None

        metadata = {"reason": reason} if reason is not None else {}
        if existing is not None:
            updated = self.update(
                existing.annotation_id,
                AnnotationUpdate(
                    label_value=disposition,
                    metadata=metadata,
                    updated_by=actor,
                ),
                action="disposition_update",
            )
            if updated is None:
                return None
            return {
                "disposition": updated.label_value,
                "reason": (updated.metadata or {}).get("reason"),
                "disposition_updated_at": updated.updated_at,
            }

        created = self.create(
            AnnotationCreate(
                dataset_id=dataset_id,
                episode_index=episode_index,
                start_frame=0,
                end_frame=0,
                label_type=EPISODE_DISPOSITION_LABEL_TYPE,
                label_value=disposition,
                source=AnnotationSource.human,
                review_status=ReviewStatus.accepted,
                metadata=metadata,
                created_by=actor,
            )
        )
        return {
            "disposition": created.label_value,
            "reason": (created.metadata or {}).get("reason"),
            "disposition_updated_at": created.updated_at,
        }

    def list_episode_dispositions(
        self,
        dataset_id: str,
    ) -> dict[int, dict[str, Any]]:
        latest: dict[int, AnnotationRecord] = {}
        for record in self._records.values():
            if record.dataset_id != dataset_id:
                continue
            if record.label_type != EPISODE_DISPOSITION_LABEL_TYPE:
                continue
            if record.deleted_at is not None:
                continue
            existing = latest.get(record.episode_index)
            if existing is None or record.updated_at > existing.updated_at:
                latest[record.episode_index] = record
        return {
            episode_index: {
                "disposition": record.label_value,
                "reason": (record.metadata or {}).get("reason"),
                "disposition_updated_at": record.updated_at,
            }
            for episode_index, record in latest.items()
        }

    def _find_active_disposition(
        self,
        dataset_id: str,
        episode_index: int,
    ) -> AnnotationRecord | None:
        latest: AnnotationRecord | None = None
        for record in self._records.values():
            if record.dataset_id != dataset_id:
                continue
            if record.episode_index != episode_index:
                continue
            if record.label_type != EPISODE_DISPOSITION_LABEL_TYPE:
                continue
            if record.deleted_at is not None:
                continue
            if latest is None or record.updated_at > latest.updated_at:
                latest = record
        return latest

    def storage_paths(self, dataset_id: str) -> dict[str, str]:
        dataset_dir = self._dataset_dir(dataset_id)
        return {
            "jsonl": str(dataset_dir / "annotations.jsonl"),
            "lance": str(dataset_dir / "annotations.lance"),
            "legacy_lance": str(dataset_dir / "annotations.lance"),
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
        records = self._dataset_records(dataset_id)
        active_records = [record for record in records if record.deleted_at is None]
        jsonl_path = dataset_dir / "annotations.jsonl"
        lines = [json.dumps(self._json_row(record), sort_keys=True) for record in records]
        _atomic_write_text(jsonl_path, "\n".join(lines) + ("\n" if lines else ""))
        self._mirror_current_lance(dataset_dir / "annotations_current.lance", active_records)
        if self.write_legacy_lance_mirror:
            # Deprecated compatibility path for older tools that still expect a
            # single current-view annotations.lance table.
            self._mirror_lance(dataset_dir / "annotations.lance", active_records)

    def _dataset_records(self, dataset_id: str) -> list[AnnotationRecord]:
        records = [
            record for record in self._records.values() if record.dataset_id == dataset_id
        ]
        return sorted(
            records,
            key=lambda record: (
                record.episode_index,
                record.start_frame,
                record.annotation_id,
            ),
        )

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

    def _rewrite_history_dataset(self, dataset_id: str) -> None:
        if not self.persist:
            return
        dataset_dir = self._dataset_dir(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        history_path = dataset_dir / "history.jsonl"
        rows = [
            self._history_json_row(event)
            for event in self._history
            if event.dataset_id == dataset_id
        ]
        if rows:
            text = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
            _atomic_write_text(history_path, text)
            self._mirror_events_lance(dataset_dir / "annotation_events.lance", dataset_id)
            return
        if history_path.exists():
            history_path.unlink()
        _remove_path(dataset_dir / "annotation_events.lance")

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
        row = model_dump(record)
        metadata = row.pop("metadata", {}) or {}
        return {
            **row,
            "source": record.source.value,
            "review_status": record.review_status.value,
            "metadata_json": json.dumps(metadata, sort_keys=True),
        }


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


annotation_store = AnnotationStore()


def _annotation_update_action(update_data: dict[str, object]) -> str:
    if set(update_data) == {"assigned_to"}:
        return "assign"
    review_status = update_data.get("review_status")
    status_value = getattr(review_status, "value", review_status)
    if status_value == "accepted":
        return "accept"
    if status_value == "rejected":
        return "reject"
    return "update"


def _atomic_write_text(path: Path, text: str) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        import shutil

        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
