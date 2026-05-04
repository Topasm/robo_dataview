from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.pydantic_compat import model_dump


LEROBOT_SNAPSHOT_VERSION = "lerobot_v3_metadata_snapshot"
LEROBOT_CODEBASE_VERSION = "v3.0"
TASKS_PARQUET_PATH = Path("meta/tasks.parquet")
STATS_JSON_PATH = Path("meta/stats.json")
EPISODES_PARQUET_PATH = Path("meta/episodes/chunk-000/file-000.parquet")
EPISODES_JSONL_PATH = Path("meta/episodes/chunk-000/file-000.jsonl")
DATA_INDEX_JSONL_PATH = Path("data/chunk-000/file-000.index.jsonl")
ANNOTATIONS_JSONL_PATH = Path("annotations/annotations.jsonl")
VALIDATION_JSON_PATH = Path("validation.json")


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
    stats_path = root / STATS_JSON_PATH
    tasks_jsonl_path = meta_dir / "tasks.jsonl"
    tasks_parquet_path = root / TASKS_PARQUET_PATH
    episodes_jsonl_path = root / EPISODES_JSONL_PATH
    episodes_parquet_path = root / EPISODES_PARQUET_PATH
    data_index_path = root / DATA_INDEX_JSONL_PATH
    annotations_path = root / ANNOTATIONS_JSONL_PATH
    validation_path = root / VALIDATION_JSON_PATH

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
        "codebase_version": LEROBOT_CODEBASE_VERSION,
        "materialization_status": "metadata_only",
        "version_description": version_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_episodes": len(episodes),
        "total_frames": sum(episode.length or 0 for episode in episodes),
        "total_tasks": len(task_rows),
        "fps": _common_fps(episodes),
        "chunks_size": 1000,
        "data_files_size_in_mb": 100,
        "video_files_size_in_mb": 200,
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
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
            "tasks": "meta/tasks.parquet",
            "tasks_jsonl": "meta/tasks.jsonl",
            "stats": "meta/stats.json",
            "episodes": "meta/episodes/chunk-000/file-000.parquet",
            "episodes_jsonl": "meta/episodes/chunk-000/file-000.jsonl",
            "annotations": "annotations/annotations.jsonl",
            "validation": "validation.json",
        },
        "notes": [
            "Full LeRobot v3 export requires optional lerobot and pyarrow dependencies.",
            "This snapshot preserves selected episodes, tasks, offsets, and accepted annotations.",
            "The official v3 metadata parquet files are written when pyarrow is installed.",
        ],
    }

    info_path.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8")
    stats_path.write_text(json.dumps(_empty_stats(), indent=2, sort_keys=True), encoding="utf-8")
    _write_jsonl(tasks_jsonl_path, task_rows)
    _write_jsonl(episodes_jsonl_path, episode_rows)
    _write_jsonl(data_index_path, _data_index_rows(episode_rows))
    _write_jsonl(annotations_path, annotation_rows)

    parquet_files = {
        "tasks": _write_optional_parquet(tasks_parquet_path, task_rows),
        "episodes": _write_optional_parquet(episodes_parquet_path, episode_rows),
    }
    validation = validate_lerobot_v3_snapshot(root)
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "format": LEROBOT_SNAPSHOT_VERSION,
        "root": str(root),
        "materialization_status": "metadata_only",
        "validation": validation,
        "files": {
            "info": str(info_path),
            "stats": str(stats_path),
            "tasks": str(tasks_parquet_path) if parquet_files["tasks"] else None,
            "tasks_jsonl": str(tasks_jsonl_path),
            "episodes": str(episodes_parquet_path) if parquet_files["episodes"] else None,
            "episodes_jsonl": str(episodes_jsonl_path),
            "data_index": str(data_index_path),
            "annotations": str(annotations_path),
            "validation": str(validation_path),
        },
    }


def read_lerobot_snapshot_summary(root: Path) -> dict[str, Any]:
    info_path = root / "meta" / "info.json"
    if not info_path.exists():
        raise FileNotFoundError("LeRobot snapshot must contain meta/info.json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    episodes = _read_episode_rows(root)
    return {
        "dataset_id": info.get("dataset_id"),
        "format": info.get("format"),
        "total_episodes": info.get("total_episodes"),
        "episode_indices": [episode["episode_index"] for episode in episodes],
    }


def read_lerobot_snapshot_episodes(root: Path, dataset_id: str | None = None) -> list[EpisodeDetail]:
    info_path = root / "meta" / "info.json"
    if not info_path.exists():
        raise FileNotFoundError("LeRobot snapshot must contain meta/info.json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    resolved_dataset_id = dataset_id or str(info.get("dataset_id") or root.name)
    rows = _read_episode_rows(root)
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


def validate_lerobot_v3_snapshot(root: Path) -> dict[str, Any]:
    """Validate the local metadata snapshot without requiring LeRobot itself.

    The current exporter intentionally produces a metadata-only snapshot, so the
    report distinguishes metadata contract health from full LeRobot loadability.
    """

    info_path = root / "meta" / "info.json"
    paths = {
        "info": info_path,
        "stats": root / STATS_JSON_PATH,
        "tasks_parquet": root / TASKS_PARQUET_PATH,
        "tasks_jsonl": root / "meta" / "tasks.jsonl",
        "episodes_parquet": root / EPISODES_PARQUET_PATH,
        "episodes_jsonl": root / EPISODES_JSONL_PATH,
        "data_index": root / DATA_INDEX_JSONL_PATH,
        "annotations": root / ANNOTATIONS_JSONL_PATH,
    }
    present = {name: path.exists() for name, path in paths.items()}
    errors: list[str] = []
    warnings: list[str] = []

    if not present["info"]:
        errors.append("missing meta/info.json")
        return {
            "metadata_ok": False,
            "lerobot_loadable": False,
            "materialization_status": "missing_info",
            "files": {name: str(path) for name, path in paths.items()},
            "present": present,
            "errors": errors,
            "warnings": warnings,
        }

    info = json.loads(info_path.read_text(encoding="utf-8"))
    episode_rows = _read_episode_rows(root)
    data_index_rows = _read_jsonl(paths["data_index"]) if present["data_index"] else []

    if info.get("codebase_version") != LEROBOT_CODEBASE_VERSION:
        warnings.append(f"codebase_version is {info.get('codebase_version')!r}, expected {LEROBOT_CODEBASE_VERSION!r}")
    if not present["stats"]:
        errors.append("missing meta/stats.json")
    if not (present["tasks_parquet"] or present["tasks_jsonl"]):
        errors.append("missing task metadata")
    if not (present["episodes_parquet"] or present["episodes_jsonl"]):
        errors.append("missing episode metadata")
    if int(info.get("total_episodes") or 0) != len(episode_rows):
        errors.append("total_episodes does not match episode metadata rows")
    if len(data_index_rows) != len(episode_rows):
        errors.append("data index row count does not match episode metadata rows")

    previous_end = 0
    for row in data_index_rows:
        start = int(row.get("data_start_idx") or 0)
        end = int(row.get("data_end_idx") or 0)
        if start != previous_end:
            errors.append(f"data index is not contiguous at episode {row.get('episode_index')}")
            break
        if end < start:
            errors.append(f"data index end is before start at episode {row.get('episode_index')}")
            break
        previous_end = end

    if not present["tasks_parquet"]:
        warnings.append("pyarrow not available or parquet task metadata was not written")
    if not present["episodes_parquet"]:
        warnings.append("pyarrow not available or parquet episode metadata was not written")
    warnings.append("metadata-only snapshot is not directly loadable by LeRobotDataset until data/video shards are materialized")

    return {
        "metadata_ok": not errors,
        "lerobot_loadable": False,
        "materialization_status": str(info.get("materialization_status") or "metadata_only"),
        "episode_count": len(episode_rows),
        "frame_count": sum(int(row.get("length") or 0) for row in episode_rows),
        "files": {name: str(path) for name, path in paths.items()},
        "present": present,
        "errors": errors,
        "warnings": warnings,
    }


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


def _empty_stats() -> dict[str, Any]:
    return {
        "note": "Statistics are not materialized in the metadata-only export.",
        "features": {},
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_episode_rows(root: Path) -> list[dict[str, Any]]:
    parquet_path = root / EPISODES_PARQUET_PATH
    if parquet_path.exists():
        rows = _read_optional_parquet(parquet_path)
        if rows is not None:
            return rows
    jsonl_path = root / EPISODES_JSONL_PATH
    if jsonl_path.exists():
        return _read_jsonl(jsonl_path)
    raise FileNotFoundError(
        "LeRobot snapshot must contain meta/episodes/chunk-000/file-000.parquet "
        "or meta/episodes/chunk-000/file-000.jsonl"
    )


def _write_optional_parquet(path: Path, rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)
    return True


def _read_optional_parquet(path: Path) -> list[dict[str, Any]] | None:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return None
    return pq.read_table(path).to_pylist()
