from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.lance_store import store
from workers.rerun_cache_worker import (
    RERUN_RECORDING_CONFIG_VERSION,
    generate_rerun_recording,
)


RERUN_CACHE_DIR = Path("data/cache/rerun")


def _cache_key(dataset_id: str, episode_index: int, mode: str) -> str:
    key = f"{dataset_id}|{episode_index}|{mode}|{RERUN_RECORDING_CONFIG_VERSION}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class RerunSessionStore:
    def __init__(self) -> None:
        self._records: dict[str, RerunSessionRecord] = {}

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
        self._records[session_id] = record
        return record

    def get(self, session_id: str) -> RerunSessionRecord:
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


rerun_sessions = RerunSessionStore()
