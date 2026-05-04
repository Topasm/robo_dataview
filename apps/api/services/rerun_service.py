from __future__ import annotations

import hashlib
from importlib import import_module
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.lance_store import store
from apps.api.services.pydantic_compat import model_dump
from workers.rerun_cache_worker import (
    RERUN_RECORDING_CONFIG_VERSION,
    generate_rerun_recording,
)


RERUN_CACHE_DIR = Path("data/cache/rerun")
RERUN_SESSION_RECORD_PATH = Path("data/app/rerun_sessions.jsonl")


def _cache_key(dataset_id: str, episode_index: int, mode: str) -> str:
    key = f"{dataset_id}|{episode_index}|{mode}|{RERUN_RECORDING_CONFIG_VERSION}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class RerunSessionStore:
    def __init__(self, record_path: Path | None = None) -> None:
        self.record_path = record_path
        self._records: dict[str, RerunSessionRecord] = {}
        self._load_existing_records()

    def create(self, payload: RerunSessionCreate) -> RerunSessionRecord:
        session_id = str(uuid4())
        cache_key = _cache_key(payload.dataset_id, payload.episode_index, payload.mode)
        rrd_path = RERUN_CACHE_DIR / f"{payload.dataset_id}_episode_{payload.episode_index:06d}_{cache_key}.rrd"
        record = RerunSessionRecord(
            session_id=session_id,
            dataset_id=payload.dataset_id,
            episode_index=payload.episode_index,
            mode=payload.mode,
            status="pending",
            cache_key=cache_key,
            viewer_url=None,
            rrd_url=f"/api/rerun/recordings/{session_id}.rrd",
            rrd_path=str(rrd_path),
        )
        record = self._generate_rrd(record, rrd_path)
        self._save(record)
        return record

    def get(self, session_id: str) -> RerunSessionRecord:
        record = self._records.get(session_id)
        if record is None:
            self._load_existing_records()
            record = self._records.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Rerun session not found")
        return record

    def path_for_recording(self, session_id: str) -> Path:
        record = self.get(session_id)
        if record.rrd_path is None:
            raise HTTPException(status_code=404, detail="Rerun recording not available")
        path = Path(record.rrd_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Rerun recording not found")
        return path

    def _generate_rrd(self, record: RerunSessionRecord, rrd_path: Path) -> RerunSessionRecord:
        return generate_rerun_recording(
            record,
            rrd_path,
            dataset_store=store,
            import_module_fn=import_module,
        )

    def _save(self, record: RerunSessionRecord) -> None:
        self._records[record.session_id] = record
        if self.record_path is None:
            return
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        with self.record_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(model_dump(record), default=str, sort_keys=True))
            handle.write("\n")

    def _load_existing_records(self) -> None:
        if self.record_path is None or not self.record_path.exists():
            return
        for line in self.record_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = RerunSessionRecord(**json.loads(line))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            self._records[record.session_id] = record


rerun_sessions = RerunSessionStore(record_path=RERUN_SESSION_RECORD_PATH)
