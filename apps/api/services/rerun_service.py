from __future__ import annotations

from importlib import import_module
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.lance_store import _numeric_vector, _sequence, store
from apps.api.services.pydantic_compat import model_copy


RERUN_CACHE_DIR = Path("data/cache/rerun")


def _vector_norm(value: object) -> float | None:
    vector = _numeric_vector(value)
    if not vector:
        return None
    return sum(item * item for item in vector) ** 0.5


def _set_rerun_sequence_time(rr: object, timeline: str, sequence: int) -> None:
    if hasattr(rr, "set_time"):
        rr.set_time(timeline, sequence=sequence)
        return
    rr.set_time_sequence(timeline, sequence)


def _rerun_scalar(rr: object, value: float) -> object:
    if hasattr(rr, "Scalar"):
        return rr.Scalar(value)
    return rr.Scalars(value)


class RerunSessionStore:
    def __init__(self) -> None:
        self._records: dict[str, RerunSessionRecord] = {}

    def create(self, payload: RerunSessionCreate) -> RerunSessionRecord:
        session_id = str(uuid4())
        rrd_path = RERUN_CACHE_DIR / f"{payload.dataset_id}_episode_{payload.episode_index:06d}_{session_id}.rrd"
        record = RerunSessionRecord(
            session_id=session_id,
            dataset_id=payload.dataset_id,
            episode_index=payload.episode_index,
            mode=payload.mode,
            status="pending",
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
        timeseries = store.get_episode_timeseries(record.dataset_id, record.episode_index)
        if timeseries is None:
            return model_copy(
                record,
                update={
                    "status": "episode_not_found",
                    "message": "Episode was not found in the dataset store.",
                }
            )

        try:
            rr = import_module("rerun")
        except ImportError:
            return model_copy(
                record,
                update={
                    "status": "dependency_missing",
                    "message": "Python package 'rerun-sdk>=0.31.4,<0.32' is not installed.",
                }
            )

        RERUN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        states = _sequence(timeseries.get("states"))
        actions = _sequence(timeseries.get("actions"))
        timestamps = _sequence(timeseries.get("timestamps"))
        frame_count = max(len(states), len(actions), len(timestamps), 1)

        rr.init("robot_data_studio", recording_id=record.session_id, spawn=False)
        rr.save(rrd_path)
        for frame_index in range(frame_count):
            _set_rerun_sequence_time(rr, "frame", frame_index)
            if frame_index < len(timestamps):
                timestamp = timestamps[frame_index]
                if isinstance(timestamp, (int, float)):
                    rr.log("episode/timestamp", _rerun_scalar(rr, float(timestamp)))
            if frame_index < len(states):
                state_norm = _vector_norm(states[frame_index])
                if state_norm is not None:
                    rr.log("state/norm", _rerun_scalar(rr, state_norm))
            if frame_index < len(actions):
                action_norm = _vector_norm(actions[frame_index])
                if action_norm is not None:
                    rr.log("action/norm", _rerun_scalar(rr, action_norm))

        return model_copy(
            record,
            update={
                "status": "ready",
                "message": f"Generated Rerun recording with {frame_count} frames.",
            }
        )


rerun_sessions = RerunSessionStore()
