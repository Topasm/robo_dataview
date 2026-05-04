from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.pydantic_compat import model_dump


LEROBOT_SNAPSHOT_VERSION = "lerobot_v3_metadata_snapshot"


def write_lerobot_v3_snapshot(
    export_dir: Path,
    *,
    dataset_id: str,
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    version_description: str | None,
) -> dict[str, Any]:
    """Write a deterministic LeRobot v3-oriented metadata snapshot.

    This is not a full Parquet/MP4 materialization. It creates the v3 directory
    contract and enough metadata for Robot Data Studio to validate selected
    subsets before the optional `lerobot`/`pyarrow` export path is available.
    """

    root = export_dir / "lerobot_v3"
    meta_dir = root / "meta"
    episodes_dir = meta_dir / "episodes" / "chunk-000"
    data_dir = root / "data" / "chunk-000"
    videos_dir = root / "videos"
    annotations_dir = root / "annotations"
    for directory in (meta_dir, episodes_dir, data_dir, videos_dir, annotations_dir):
        directory.mkdir(parents=True, exist_ok=True)

    info_path = meta_dir / "info.json"
    tasks_path = meta_dir / "tasks.jsonl"
    episodes_path = episodes_dir / "file-000.jsonl"
    data_index_path = data_dir / "file-000.index.jsonl"
    annotations_path = annotations_dir / "annotations.jsonl"

    task_rows = _task_rows(episodes)
    episode_rows = _episode_rows(episodes, annotations_by_episode)
    annotation_rows = [
        _annotation_row(annotation)
        for annotations in annotations_by_episode.values()
        for annotation in annotations
    ]

    info = {
        "dataset_id": dataset_id,
        "format": LEROBOT_SNAPSHOT_VERSION,
        "materialization_status": "metadata_only",
        "version_description": version_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_episodes": len(episodes),
        "total_frames": sum(episode.length or 0 for episode in episodes),
        "fps": _common_fps(episodes),
        "camera_names": sorted({camera for episode in episodes for camera in episode.camera_names}),
        "features": {
            "observation.state": {"dtype": "float32", "shape": ["state_dim"]},
            "action": {"dtype": "float32", "shape": ["action_dim"]},
            "timestamp": {"dtype": "float32", "shape": [1]},
            "episode_index": {"dtype": "int64", "shape": [1]},
            "frame_index": {"dtype": "int64", "shape": [1]},
        },
        "paths": {
            "data": "data/chunk-000/file-000.parquet",
            "data_index": "data/chunk-000/file-000.index.jsonl",
            "videos": "videos/{camera}/chunk-000/file-000.mp4",
            "tasks": "meta/tasks.jsonl",
            "episodes": "meta/episodes/chunk-000/file-000.parquet",
            "episodes_index": "meta/episodes/chunk-000/file-000.jsonl",
            "annotations": "annotations/annotations.jsonl",
        },
        "notes": [
            "Full LeRobot v3 export requires optional lerobot and pyarrow dependencies.",
            "This snapshot preserves selected episodes, tasks, offsets, and accepted annotations.",
        ],
    }

    info_path.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8")
    _write_jsonl(tasks_path, task_rows)
    _write_jsonl(episodes_path, episode_rows)
    _write_jsonl(data_index_path, _data_index_rows(episode_rows))
    _write_jsonl(annotations_path, annotation_rows)

    return {
        "format": LEROBOT_SNAPSHOT_VERSION,
        "root": str(root),
        "materialization_status": "metadata_only",
        "files": {
            "info": str(info_path),
            "tasks": str(tasks_path),
            "episodes_index": str(episodes_path),
            "data_index": str(data_index_path),
            "annotations": str(annotations_path),
        },
    }


def read_lerobot_snapshot_summary(root: Path) -> dict[str, Any]:
    info_path = root / "meta" / "info.json"
    episodes_path = root / "meta" / "episodes" / "chunk-000" / "file-000.jsonl"
    if not info_path.exists() or not episodes_path.exists():
        raise FileNotFoundError("LeRobot snapshot must contain meta/info.json and episode index JSONL")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    episodes = [
        json.loads(line)
        for line in episodes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "dataset_id": info.get("dataset_id"),
        "format": info.get("format"),
        "total_episodes": info.get("total_episodes"),
        "episode_indices": [episode["episode_index"] for episode in episodes],
    }


def read_lerobot_snapshot_episodes(root: Path, dataset_id: str | None = None) -> list[EpisodeDetail]:
    info_path = root / "meta" / "info.json"
    episodes_path = root / "meta" / "episodes" / "chunk-000" / "file-000.jsonl"
    if not info_path.exists() or not episodes_path.exists():
        raise FileNotFoundError("LeRobot snapshot must contain meta/info.json and episode index JSONL")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    resolved_dataset_id = dataset_id or str(info.get("dataset_id") or root.name)
    rows = [
        json.loads(line)
        for line in episodes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [
        EpisodeDetail(
            dataset_id=resolved_dataset_id,
            episode_index=int(row["episode_index"]),
            task_index=row.get("task_index"),
            length=row.get("length"),
            success_label=row.get("success_label"),
            quality_score=row.get("quality_score"),
            review_status=row.get("review_status") or "pending",
            caption=row.get("caption"),
            split=row.get("split"),
            fps=row.get("fps"),
            camera_names=row.get("camera_names") or [],
            duration_seconds=(
                row["length"] / row["fps"]
                if row.get("length") is not None and row.get("fps")
                else None
            ),
            language_instruction=row.get("language_instruction"),
        )
        for row in rows
    ]


def _task_rows(episodes: list[EpisodeDetail]) -> list[dict[str, Any]]:
    tasks: dict[int, str] = {}
    for episode in episodes:
        task_index = int(episode.task_index or 0)
        tasks.setdefault(
            task_index,
            episode.language_instruction or episode.caption or f"task_{task_index}",
        )
    return [
        {"task_index": task_index, "task": task}
        for task_index, task in sorted(tasks.items(), key=lambda item: item[0])
    ]


def _episode_rows(
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
) -> list[dict[str, Any]]:
    rows = []
    data_start_idx = 0
    for episode in episodes:
        length = episode.length or 0
        data_end_idx = data_start_idx + length
        rows.append(
            {
                "episode_index": episode.episode_index,
                "task_index": episode.task_index,
                "length": length,
                "data_start_idx": data_start_idx,
                "data_end_idx": data_end_idx,
                "fps": episode.fps,
                "split": episode.split,
                "success_label": episode.success_label,
                "quality_score": episode.quality_score,
                "review_status": episode.review_status,
                "caption": episode.caption,
                "language_instruction": episode.language_instruction,
                "camera_names": episode.camera_names,
                "accepted_annotation_count": len(annotations_by_episode.get(episode.episode_index, [])),
            }
        )
        data_start_idx = data_end_idx
    return rows


def _data_index_rows(episode_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "episode_index": row["episode_index"],
            "data_file": "data/chunk-000/file-000.parquet",
            "data_start_idx": row["data_start_idx"],
            "data_end_idx": row["data_end_idx"],
        }
        for row in episode_rows
    ]


def _annotation_row(annotation: AnnotationRecord) -> dict[str, Any]:
    row = model_dump(annotation)
    row["source"] = annotation.source.value
    row["review_status"] = annotation.review_status.value
    row["created_at"] = annotation.created_at.isoformat()
    row["updated_at"] = annotation.updated_at.isoformat()
    return row


def _common_fps(episodes: list[EpisodeDetail]) -> float | None:
    fps_values = {episode.fps for episode in episodes if episode.fps is not None}
    if len(fps_values) == 1:
        return fps_values.pop()
    return None


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )
