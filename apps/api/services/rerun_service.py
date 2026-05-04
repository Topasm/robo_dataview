from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
import re
from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.lance_store import _numeric_vector, _sequence, store
from apps.api.services.pydantic_compat import model_copy


RERUN_CACHE_DIR = Path("data/cache/rerun")
RERUN_RECORDING_CONFIG_VERSION = "state_action_video_assets_v1"


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


def _cache_key(dataset_id: str, episode_index: int, mode: str) -> str:
    key = f"{dataset_id}|{episode_index}|{mode}|{RERUN_RECORDING_CONFIG_VERSION}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _safe_entity_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("_") or "camera"


def _video_frame_seconds(timestamps: list[object], frame_index: int, fps: float | None) -> float:
    if frame_index < len(timestamps) and isinstance(timestamps[frame_index], (int, float)):
        return float(timestamps[frame_index])
    return frame_index / (fps or 20.0)


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
        if rrd_path.exists():
            return model_copy(
                record,
                update={
                    "status": "ready",
                    "cache_hit": True,
                    "message": "Loaded cached Rerun recording.",
                }
            )

        states = _sequence(timeseries.get("states"))
        actions = _sequence(timeseries.get("actions"))
        timestamps = _sequence(timeseries.get("timestamps"))
        frame_count = max(len(states), len(actions), len(timestamps), 1)
        episode = store.get_episode(record.dataset_id, record.episode_index)
        fps = episode.fps if episode is not None else None

        rr.init("robot_data_studio", recording_id=record.session_id, spawn=False)
        rr.save(rrd_path)
        camera_count = self._log_camera_videos(rr, record, timestamps, frame_count, fps)
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
                "camera_count": camera_count,
                "message": f"Generated Rerun recording with {frame_count} frames and {camera_count} camera videos.",
            }
        )

    def _log_camera_videos(
        self,
        rr: object,
        record: RerunSessionRecord,
        timestamps: list[object],
        frame_count: int,
        fps: float | None,
    ) -> int:
        if not hasattr(rr, "AssetVideo") or not hasattr(rr, "VideoFrameReference"):
            return 0

        episode = store.get_episode(record.dataset_id, record.episode_index)
        if episode is None:
            return 0

        camera_count = 0
        for camera in episode.camera_names:
            blob = store.get_video_blob(record.dataset_id, record.episode_index, camera)
            if blob is None:
                continue
            camera_name = _safe_entity_name(camera)
            asset_path = f"cameras/{camera_name}/video_asset"
            frame_path = f"cameras/{camera_name}/frame"
            rr.log(
                asset_path,
                rr.AssetVideo(contents=blob, media_type="video/mp4"),
                static=True,
            )
            for frame_index in range(frame_count):
                _set_rerun_sequence_time(rr, "frame", frame_index)
                rr.log(
                    frame_path,
                    rr.VideoFrameReference(
                        seconds=_video_frame_seconds(timestamps, frame_index, fps),
                        video_reference=asset_path,
                    ),
                )
            camera_count += 1
        return camera_count


rerun_sessions = RerunSessionStore()
