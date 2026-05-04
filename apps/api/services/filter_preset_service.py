from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from apps.api.schemas.search import FilterPresetCreate, FilterPresetRecord
from apps.api.services.pydantic_compat import model_dump


FILTER_PRESET_STORAGE_ROOT = Path("data/lance/filter_presets")


class FilterPresetStore:
    def __init__(self, storage_root: Path = FILTER_PRESET_STORAGE_ROOT) -> None:
        self.storage_root = storage_root
        self._records: dict[str, FilterPresetRecord] = {}
        self._load()

    def list(self, dataset_id: str) -> list[FilterPresetRecord]:
        records = [record for record in self._records.values() if record.dataset_id == dataset_id]
        return sorted(records, key=lambda record: (record.name.lower(), record.created_at))

    def create(self, payload: FilterPresetCreate) -> FilterPresetRecord:
        now = datetime.now(timezone.utc)
        record = FilterPresetRecord(
            preset_id=str(uuid4()),
            dataset_id=payload.dataset_id,
            name=payload.name.strip(),
            query=payload.query.strip(),
            created_at=now,
            updated_at=now,
        )
        self._records[record.preset_id] = record
        self._persist()
        return record

    def delete(self, preset_id: str) -> bool:
        if self._records.pop(preset_id, None) is None:
            return False
        self._persist()
        return True

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            self._records[row["preset_id"]] = FilterPresetRecord(**row)

    def _persist(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        rows = [
            self._json_row(record)
            for record in sorted(
                self._records.values(),
                key=lambda record: (record.dataset_id, record.name.lower(), record.created_at),
            )
        ]
        self._path().write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _path(self) -> Path:
        return self.storage_root / "filter_presets.jsonl"

    @staticmethod
    def _json_row(record: FilterPresetRecord) -> dict[str, object]:
        return {
            **model_dump(record),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }


filter_preset_store = FilterPresetStore()
