from __future__ import annotations

from datetime import datetime, timezone
import json
import math
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
DATA_PARQUET_PATH = Path("data/chunk-000/file-000.parquet")
DATA_JSONL_PATH = Path("data/chunk-000/file-000.jsonl")
VIDEO_INDEX_JSONL_PATH = Path("videos/video_index.jsonl")
ANNOTATIONS_JSONL_PATH = Path("annotations/annotations.jsonl")
VALIDATION_JSON_PATH = Path("validation.json")


def write_lerobot_v3_snapshot(
    export_dir: Path,
    *,
    dataset_id: str,
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    version_description: str | None,
    timeseries_by_episode: dict[int, dict[str, Any]] | None = None,
    video_blobs_by_episode: dict[int, dict[str, bytes]] | None = None,
) -> dict[str, Any]:
    """Write a deterministic LeRobot v3-oriented snapshot.

    The exporter always writes the v3 metadata contract and accepted annotation
    rows. When episode time-series and video blobs are provided, it also writes
    frame rows and camera MP4 artifacts. Frame Parquet is written when optional
    `pyarrow` is installed; JSONL remains the mandatory fallback.
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
    data_jsonl_path = root / DATA_JSONL_PATH
    data_parquet_path = root / DATA_PARQUET_PATH
    video_index_path = root / VIDEO_INDEX_JSONL_PATH
    annotations_path = root / ANNOTATIONS_JSONL_PATH
    validation_path = root / VALIDATION_JSON_PATH

    task_rows, task_index_by_episode = _task_rows_and_mapping(episodes)
    episode_index_by_source = {
        episode.episode_index: local_index
        for local_index, episode in enumerate(episodes)
    }
    video_rows = _write_video_blobs(
        root,
        episodes,
        video_blobs_by_episode or {},
        episode_index_by_source=episode_index_by_source,
    )
    frame_rows = _frame_rows(
        episodes,
        timeseries_by_episode or {},
        video_rows=video_rows,
        episode_index_by_source=episode_index_by_source,
        task_index_by_episode=task_index_by_episode,
    )
    episode_rows = _episode_rows(
        episodes,
        annotations_by_episode,
        video_rows,
        episode_index_by_source=episode_index_by_source,
        task_index_by_episode=task_index_by_episode,
    )
    annotation_rows = [
        _annotation_row(annotation)
        for annotations in annotations_by_episode.values()
        for annotation in annotations
    ]
    parquet_files = {
        "tasks": _write_optional_tasks_parquet(tasks_parquet_path, task_rows),
        "episodes": _write_optional_parquet(episodes_parquet_path, episode_rows),
        "data": _write_optional_parquet(data_parquet_path, frame_rows),
    }
    materialization_status = _materialization_status(
        frame_rows=frame_rows,
        data_parquet_written=parquet_files["data"],
        video_rows=video_rows,
    )

    fps = _common_fps(episodes) or 20.0
    info = {
        "dataset_id": dataset_id,
        "format": LEROBOT_SNAPSHOT_VERSION,
        "codebase_version": LEROBOT_CODEBASE_VERSION,
        "materialization_status": materialization_status,
        "version_description": version_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_episodes": len(episodes),
        "total_frames": sum(episode.length or 0 for episode in episodes),
        "total_tasks": len(task_rows),
        "fps": fps,
        "chunks_size": 1000,
        "data_files_size_in_mb": 100,
        "video_files_size_in_mb": 200,
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
        "camera_names": sorted({camera for episode in episodes for camera in episode.camera_names}),
        "features": _feature_schema(frame_rows, video_rows),
        "paths": {
            "data": "data/chunk-000/file-000.parquet",
            "data_jsonl": "data/chunk-000/file-000.jsonl",
            "data_index": "data/chunk-000/file-000.index.jsonl",
            "videos": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
            "video_index": "videos/video_index.jsonl",
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
            "Frame data JSONL and camera MP4 blobs are materialized when available.",
        ],
    }

    info_path.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8")
    stats_path.write_text(json.dumps(_stats(frame_rows), indent=2, sort_keys=True), encoding="utf-8")
    _write_jsonl(tasks_jsonl_path, task_rows)
    _write_jsonl(episodes_jsonl_path, episode_rows)
    _write_jsonl(data_index_path, _data_index_rows(episode_rows))
    _write_jsonl(data_jsonl_path, frame_rows)
    _write_jsonl(video_index_path, video_rows)
    _write_jsonl(annotations_path, annotation_rows)

    validation = validate_lerobot_v3_snapshot(root)
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "format": LEROBOT_SNAPSHOT_VERSION,
        "root": str(root),
        "materialization_status": materialization_status,
        "validation": validation,
        "files": {
            "info": str(info_path),
            "stats": str(stats_path),
            "tasks": str(tasks_parquet_path) if parquet_files["tasks"] else None,
            "tasks_jsonl": str(tasks_jsonl_path),
            "episodes": str(episodes_parquet_path) if parquet_files["episodes"] else None,
            "episodes_jsonl": str(episodes_jsonl_path),
            "data": str(data_parquet_path) if parquet_files["data"] else None,
            "data_jsonl": str(data_jsonl_path),
            "data_index": str(data_index_path),
            "video_index": str(video_index_path),
            "annotations": str(annotations_path),
            "validation": str(validation_path),
        },
        "materialized": {
            "frame_rows": len(frame_rows),
            "video_files": len(video_rows),
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
            episode_index=int(row.get("source_episode_index", row["episode_index"])),
            task_index=row.get("source_task_index", row.get("task_index")),
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
    """Validate the local snapshot and optionally probe the official loader."""

    info_path = root / "meta" / "info.json"
    paths = {
        "info": info_path,
        "stats": root / STATS_JSON_PATH,
        "tasks_parquet": root / TASKS_PARQUET_PATH,
        "tasks_jsonl": root / "meta" / "tasks.jsonl",
        "episodes_parquet": root / EPISODES_PARQUET_PATH,
        "episodes_jsonl": root / EPISODES_JSONL_PATH,
        "data_parquet": root / DATA_PARQUET_PATH,
        "data_jsonl": root / DATA_JSONL_PATH,
        "data_index": root / DATA_INDEX_JSONL_PATH,
        "video_index": root / VIDEO_INDEX_JSONL_PATH,
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
            "loadability_basis": "missing_info",
            "local_lerobot_loadable_heuristic": False,
            "official_loader": _unavailable_official_loader("missing meta/info.json"),
            "materialization_status": "missing_info",
            "files": {name: str(path) for name, path in paths.items()},
            "present": present,
            "errors": errors,
            "warnings": warnings,
        }

    info = json.loads(info_path.read_text(encoding="utf-8"))
    episode_rows = _read_episode_rows(root)
    task_rows = _read_jsonl(paths["tasks_jsonl"]) if present["tasks_jsonl"] else []
    data_index_rows = _read_jsonl(paths["data_index"]) if present["data_index"] else []
    data_rows = _read_jsonl(paths["data_jsonl"]) if present["data_jsonl"] else []
    video_rows = _read_jsonl(paths["video_index"]) if present["video_index"] else []
    parquet_readability = _parquet_readability(paths, present)
    materialization_status = str(info.get("materialization_status") or "metadata_only")

    if info.get("codebase_version") != LEROBOT_CODEBASE_VERSION:
        warnings.append(f"codebase_version is {info.get('codebase_version')!r}, expected {LEROBOT_CODEBASE_VERSION!r}")
    if not present["stats"]:
        errors.append("missing meta/stats.json")
    if not (present["tasks_parquet"] or present["tasks_jsonl"]):
        errors.append("missing task metadata")
    if not (present["episodes_parquet"] or present["episodes_jsonl"]):
        errors.append("missing episode metadata")
    if info.get("fps") is None or float(info.get("fps") or 0) <= 0:
        errors.append("meta/info.json must include a positive fps")
    if int(info.get("total_tasks") or 0) != len(task_rows):
        errors.append("total_tasks does not match task metadata rows")
    if int(info.get("total_episodes") or 0) != len(episode_rows):
        errors.append("total_episodes does not match episode metadata rows")
    if len(data_index_rows) != len(episode_rows):
        errors.append("data index row count does not match episode metadata rows")
    frame_materialized_statuses = {"data_jsonl", "data_jsonl_mp4", "parquet", "parquet_mp4"}
    if materialization_status in frame_materialized_statuses and not (
        present["data_parquet"] or present["data_jsonl"]
    ):
        errors.append("materialized export is missing data rows")

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
    if data_rows and len(data_rows) != previous_end:
        errors.append("materialized frame row count does not match indexed frame count")
    if data_rows and not _frame_rows_have_official_indices(data_rows):
        errors.append("frame rows must include contiguous global index values")
    if episode_rows and not _episode_rows_have_dataset_offsets(episode_rows):
        errors.append("episode metadata must include dataset_from_index and dataset_to_index")
    if episode_rows and not _episode_rows_have_tasks(episode_rows):
        errors.append("episode metadata must include tasks lists")
    errors.extend(
        _parquet_row_count_errors(
            parquet_readability,
            {
                "tasks_parquet": len(task_rows),
                "episodes_parquet": len(episode_rows),
                "data_parquet": len(data_rows) if data_rows else previous_end,
            },
        )
    )

    if not present["tasks_parquet"]:
        warnings.append("pyarrow not available or parquet task metadata was not written")
    if not present["episodes_parquet"]:
        warnings.append("pyarrow not available or parquet episode metadata was not written")
    for name, status in parquet_readability.items():
        if not status.get("present"):
            continue
        label = str(status["label"])
        readable = status.get("readable")
        if readable is False:
            errors.append(f"{label} is not readable as Parquet: {status.get('error')}")
        elif readable is None:
            warnings.append(f"{label} could not be verified because {status.get('error')}")
    if materialization_status == "metadata_only":
        warnings.append("metadata-only snapshot is not directly loadable by LeRobotDataset until data/video shards are materialized")
    elif not present["data_parquet"]:
        warnings.append("frame data was written as JSONL only; pyarrow is required for Parquet training shards")
    if video_rows:
        missing_videos = [row["video_file"] for row in video_rows if not (root / row["video_file"]).exists()]
        if missing_videos:
            errors.append(f"video index references missing files: {missing_videos[:3]}")
        invalid_videos = [
            row["video_file"]
            for row in video_rows
            if (root / row["video_file"]).exists() and not _is_probable_mp4(root / row["video_file"])
        ]
        if invalid_videos:
            errors.append(f"video index references invalid MP4 files: {invalid_videos[:3]}")
    if data_rows and video_rows and not _frame_rows_have_video_references(data_rows, video_rows, root):
        errors.append("frame rows must include valid video feature references")

    frame_indices_ok = _frame_rows_have_official_indices(data_rows) if data_rows else True
    local_loadable = bool(
        not errors
        and present["tasks_parquet"]
        and present["episodes_parquet"]
        and present["data_parquet"]
        and _required_parquet_files_are_readable(parquet_readability)
        and frame_indices_ok
        and _episode_rows_have_data_shard_indices(episode_rows)
        and _episode_rows_have_dataset_offsets(episode_rows)
        and _episode_rows_have_tasks(episode_rows)
        and _episode_rows_have_video_shard_indices(episode_rows, video_rows)
        and _episode_rows_have_video_timestamps(episode_rows, video_rows)
        and _frame_rows_have_video_references(data_rows, video_rows, root)
    )
    official_loader = _validate_with_official_lerobot_loader(root, info)
    if official_loader["available"]:
        lerobot_loadable = bool(not errors and official_loader["ok"])
        loadability_basis = "official_loader"
    else:
        lerobot_loadable = False
        loadability_basis = "local_heuristic_unverified" if local_loadable else "not_loadable"

    return {
        "metadata_ok": not errors,
        "lerobot_loadable": lerobot_loadable,
        "loadability_basis": loadability_basis,
        "local_lerobot_loadable_heuristic": local_loadable,
        "official_loader": official_loader,
        "materialization_status": materialization_status,
        "episode_count": len(episode_rows),
        "frame_count": sum(int(row.get("length") or 0) for row in episode_rows),
        "materialized_frame_count": len(data_rows),
        "materialized_video_count": len(video_rows),
        "files": {name: str(path) for name, path in paths.items()},
        "present": present,
        "parquet_readability": parquet_readability,
        "errors": errors,
        "warnings": warnings,
    }


def _required_parquet_files_are_readable(parquet_readability: dict[str, dict[str, Any]]) -> bool:
    return all(
        parquet_readability.get(name, {}).get("readable") is True
        for name in ("tasks_parquet", "episodes_parquet", "data_parquet")
    )


def _parquet_row_count_errors(
    parquet_readability: dict[str, dict[str, Any]],
    expected_rows: dict[str, int],
) -> list[str]:
    errors = []
    for name, expected in expected_rows.items():
        status = parquet_readability.get(name, {})
        if not status.get("present") or status.get("readable") is not True:
            continue
        actual = status.get("row_count")
        if actual is None:
            continue
        if int(actual) != int(expected):
            errors.append(
                f"{status.get('label', name)} row count {actual} does not match expected {expected}"
            )
    return errors


def _is_probable_mp4(path: Path) -> bool:
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return False
    return len(header) >= 12 and header[4:8] == b"ftyp"


def _parquet_readability(
    paths: dict[str, Path],
    present: dict[str, bool],
) -> dict[str, dict[str, Any]]:
    labels = {
        "tasks_parquet": "task metadata parquet",
        "episodes_parquet": "episode metadata parquet",
        "data_parquet": "frame data parquet",
    }
    return {
        name: _parquet_file_status(paths[name], label=label, present=present[name])
        for name, label in labels.items()
    }


def _parquet_file_status(path: Path, *, label: str, present: bool) -> dict[str, Any]:
    if not present:
        return {
            "present": False,
            "checked": False,
            "readable": False,
            "row_count": None,
            "label": label,
            "error": "file is not present",
        }
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        return {
            "present": True,
            "checked": False,
            "readable": None,
            "row_count": None,
            "label": label,
            "error": f"pyarrow is unavailable: {exc}",
        }
    try:
        table = pq.read_table(path)
    except Exception as exc:
        return {
            "present": True,
            "checked": True,
            "readable": False,
            "row_count": None,
            "label": label,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "present": True,
        "checked": True,
        "readable": True,
        "row_count": getattr(table, "num_rows", None),
        "label": label,
        "error": None,
    }


def _episode_rows_have_data_shard_indices(episode_rows: list[dict[str, Any]]) -> bool:
    return all(
        row.get("data/chunk_index") is not None and row.get("data/file_index") is not None
        for row in episode_rows
    )


def _episode_rows_have_dataset_offsets(episode_rows: list[dict[str, Any]]) -> bool:
    previous_end = 0
    for row in episode_rows:
        start = row.get("dataset_from_index")
        end = row.get("dataset_to_index")
        if start is None or end is None:
            return False
        start_int = int(start)
        end_int = int(end)
        if start_int != previous_end or end_int < start_int:
            return False
        previous_end = end_int
    return True


def _episode_rows_have_tasks(episode_rows: list[dict[str, Any]]) -> bool:
    return all(isinstance(row.get("tasks"), list) and row.get("tasks") for row in episode_rows)


def _frame_rows_have_official_indices(data_rows: list[dict[str, Any]]) -> bool:
    return all(int(row.get("index", -1)) == index for index, row in enumerate(data_rows))


def _frame_rows_have_video_references(
    data_rows: list[dict[str, Any]],
    video_rows: list[dict[str, Any]],
    root: Path,
) -> bool:
    video_rows_by_episode: dict[int, list[dict[str, Any]]] = {}
    for row in video_rows:
        if row.get("episode_index") is None or not row.get("video_key"):
            continue
        video_rows_by_episode.setdefault(int(row["episode_index"]), []).append(row)
    if not video_rows_by_episode:
        return True

    for frame in data_rows:
        episode_index = frame.get("episode_index")
        if episode_index is None:
            return False
        for video in video_rows_by_episode.get(int(episode_index), []):
            video_key = str(video["video_key"])
            reference = frame.get(video_key)
            if not isinstance(reference, dict):
                return False
            path = reference.get("path")
            timestamp = reference.get("timestamp")
            if not isinstance(path, str) or not path:
                return False
            if not (root / path).exists():
                return False
            if not isinstance(timestamp, (int, float)):
                return False
    return True


def _episode_rows_have_video_shard_indices(
    episode_rows: list[dict[str, Any]],
    video_rows: list[dict[str, Any]],
) -> bool:
    video_keys_by_episode: dict[int, set[str]] = {}
    for row in video_rows:
        if row.get("episode_index") is None or not row.get("video_key"):
            continue
        video_keys_by_episode.setdefault(int(row["episode_index"]), set()).add(str(row["video_key"]))
    if not video_keys_by_episode:
        return True
    return all(
        row.get(f"videos/{video_key}/chunk_index") is not None
        and row.get(f"videos/{video_key}/file_index") is not None
        for row in episode_rows
        for video_key in video_keys_by_episode.get(_episode_index_key(row), set())
    )


def _episode_rows_have_video_timestamps(
    episode_rows: list[dict[str, Any]],
    video_rows: list[dict[str, Any]],
) -> bool:
    video_keys_by_episode: dict[int, set[str]] = {}
    for row in video_rows:
        if row.get("episode_index") is None or not row.get("video_key"):
            continue
        video_keys_by_episode.setdefault(int(row["episode_index"]), set()).add(str(row["video_key"]))
    return all(
        row.get(f"videos/{video_key}/from_timestamp") is not None
        and row.get(f"videos/{video_key}/to_timestamp") is not None
        for row in episode_rows
        for video_key in video_keys_by_episode.get(_episode_index_key(row), set())
    )


def _episode_index_key(row: dict[str, Any]) -> int:
    if row.get("episode_index") is None:
        return -1
    return int(row["episode_index"])


def _validate_with_official_lerobot_loader(root: Path, info: dict[str, Any]) -> dict[str, Any]:
    try:
        try:
            from lerobot.datasets import LeRobotDataset
        except ImportError:
            from lerobot.datasets.lerobot_dataset import LeRobotDataset
    except ImportError as exc:
        return _unavailable_official_loader(f"{type(exc).__name__}: {exc}")

    repo_id = _official_loader_repo_id(info, root)
    result: dict[str, Any] = {
        "checked": True,
        "available": True,
        "ok": False,
        "repo_id": repo_id,
        "root": str(root),
        "error": None,
        "length": None,
    }
    try:
        dataset = LeRobotDataset(repo_id, root=root)
        result["length"] = len(dataset) if hasattr(dataset, "__len__") else None
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _unavailable_official_loader(reason: str) -> dict[str, Any]:
    return {
        "checked": True,
        "available": False,
        "ok": None,
        "repo_id": None,
        "root": None,
        "error": reason,
        "length": None,
    }


def _official_loader_repo_id(info: dict[str, Any], root: Path) -> str:
    repo_id = str(info.get("repo_id") or info.get("dataset_id") or root.name)
    if "/" not in repo_id:
        repo_id = f"local/{repo_id}"
    return repo_id


def _task_rows_and_mapping(
    episodes: list[EpisodeDetail],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    task_texts: dict[str, int] = {}
    task_index_by_episode: dict[int, int] = {}
    for episode in episodes:
        task = _episode_task(episode)
        task_index = task_texts.setdefault(task, len(task_texts))
        task_index_by_episode[episode.episode_index] = task_index
    rows = [
        {"task_index": task_index, "task": task}
        for task, task_index in sorted(task_texts.items(), key=lambda item: item[1])
    ]
    return rows, task_index_by_episode


def _episode_rows(
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    video_rows: list[dict[str, Any]],
    *,
    episode_index_by_source: dict[int, int],
    task_index_by_episode: dict[int, int],
) -> list[dict[str, Any]]:
    rows = []
    data_start_idx = 0
    video_index = _video_index_by_episode(video_rows)
    for episode in episodes:
        local_episode_index = episode_index_by_source[episode.episode_index]
        length = episode.length or 0
        data_end_idx = data_start_idx + length
        task = _episode_task(episode)
        local_task_index = task_index_by_episode[episode.episode_index]
        row = {
            "episode_index": local_episode_index,
            "source_episode_index": episode.episode_index,
            "meta/episodes/chunk_index": 0,
            "meta/episodes/file_index": 0,
            "tasks": [task],
            "task_index": local_task_index,
            "source_task_index": episode.task_index,
            "length": length,
            "dataset_from_index": data_start_idx,
            "dataset_to_index": data_end_idx,
            "data_start_idx": data_start_idx,
            "data_end_idx": data_end_idx,
            "data/chunk_index": 0,
            "data/file_index": 0,
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
        row.update(video_index.get(local_episode_index, {}))
        rows.append(row)
        data_start_idx = data_end_idx
    return rows


def _video_index_by_episode(video_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    for row in video_rows:
        episode_index = int(row["episode_index"])
        video_key = str(row["video_key"])
        index.setdefault(episode_index, {})[f"videos/{video_key}/chunk_index"] = int(row["chunk_index"])
        index[episode_index][f"videos/{video_key}/file_index"] = int(row["file_index"])
        index[episode_index][f"videos/{video_key}/from_timestamp"] = float(
            row.get("from_timestamp") or 0.0
        )
        index[episode_index][f"videos/{video_key}/to_timestamp"] = float(
            row.get("to_timestamp") or 0.0
        )
    return index


def _data_index_rows(episode_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "episode_index": row["episode_index"],
            "data_file": "data/chunk-000/file-000.parquet",
            "data_start_idx": row["dataset_from_index"],
            "data_end_idx": row["dataset_to_index"],
            "dataset_from_index": row["dataset_from_index"],
            "dataset_to_index": row["dataset_to_index"],
        }
        for row in episode_rows
    ]


def _frame_rows(
    episodes: list[EpisodeDetail],
    timeseries_by_episode: dict[int, dict[str, Any]],
    video_rows: list[dict[str, Any]],
    *,
    episode_index_by_source: dict[int, int],
    task_index_by_episode: dict[int, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dataset_index = 0
    video_rows_by_episode: dict[int, list[dict[str, Any]]] = {}
    for row in video_rows:
        video_rows_by_episode.setdefault(int(row["episode_index"]), []).append(row)
    for episode in episodes:
        local_episode_index = episode_index_by_source[episode.episode_index]
        local_task_index = task_index_by_episode[episode.episode_index]
        timeseries = timeseries_by_episode.get(episode.episode_index)
        if timeseries is None:
            continue
        timestamps = _sequence(timeseries.get("timestamps"))
        states = _sequence(timeseries.get("states"))
        actions = _sequence(timeseries.get("actions"))
        frame_count = max(len(timestamps), len(states), len(actions), episode.length or 0)
        fps = episode.fps or 20.0
        for frame_index in range(frame_count):
            timestamp = _timestamp_at(timestamps, frame_index, fps)
            row = {
                "index": dataset_index,
                "episode_index": local_episode_index,
                "source_episode_index": episode.episode_index,
                "frame_index": frame_index,
                "timestamp": timestamp,
                "task_index": local_task_index,
                "source_task_index": episode.task_index,
                "observation.state": _numeric_list_at(states, frame_index),
                "action": _numeric_list_at(actions, frame_index),
            }
            row.update(_video_frame_references(video_rows_by_episode.get(local_episode_index, []), timestamp))
            rows.append(row)
            dataset_index += 1
    return rows


def _video_frame_references(
    video_rows: list[dict[str, Any]],
    timestamp: float,
) -> dict[str, dict[str, Any]]:
    return {
        str(row["video_key"]): {
            "path": str(row["video_file"]),
            "timestamp": timestamp,
        }
        for row in video_rows
        if row.get("video_key") and row.get("video_file")
    }


def _write_video_blobs(
    root: Path,
    episodes: list[EpisodeDetail],
    video_blobs_by_episode: dict[int, dict[str, bytes]],
    *,
    episode_index_by_source: dict[int, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        local_episode_index = episode_index_by_source[episode.episode_index]
        camera_blobs = video_blobs_by_episode.get(episode.episode_index, {})
        for camera, blob in sorted(camera_blobs.items()):
            if not blob:
                continue
            camera_dir = root / "videos" / _safe_path_name(camera) / "chunk-000"
            camera_dir.mkdir(parents=True, exist_ok=True)
            relative_path = (
                Path("videos")
                / _safe_path_name(camera)
                / "chunk-000"
                / f"file-{local_episode_index:03d}.mp4"
            )
            path = root / relative_path
            path.write_bytes(blob)
            rows.append(
                {
                    "episode_index": local_episode_index,
                    "source_episode_index": episode.episode_index,
                    "camera": camera,
                    "video_key": _safe_path_name(camera),
                    "chunk_index": 0,
                    "file_index": local_episode_index,
                    "from_timestamp": 0.0,
                    "to_timestamp": _episode_duration_seconds(episode),
                    "video_file": relative_path.as_posix(),
                    "file_size_bytes": len(blob),
                }
            )
    return rows


def _materialization_status(
    *,
    frame_rows: list[dict[str, Any]],
    data_parquet_written: bool,
    video_rows: list[dict[str, Any]],
) -> str:
    has_frames = bool(frame_rows)
    has_videos = bool(video_rows)
    if data_parquet_written and has_videos:
        return "parquet_mp4"
    if data_parquet_written:
        return "parquet"
    if has_frames and has_videos:
        return "data_jsonl_mp4"
    if has_frames:
        return "data_jsonl"
    if has_videos:
        return "mp4_only"
    return "metadata_only"


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


def _episode_task(episode: EpisodeDetail) -> str:
    return episode.language_instruction or episode.caption or f"task_{int(episode.task_index or 0)}"


def _episode_duration_seconds(episode: EpisodeDetail) -> float:
    if episode.duration_seconds is not None:
        return float(episode.duration_seconds)
    if episode.length is not None and episode.fps:
        return float(episode.length) / float(episode.fps)
    return 0.0


def _stats(frame_rows: list[dict[str, Any]]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    timestamp_values = [
        float(row["timestamp"])
        for row in frame_rows
        if isinstance(row.get("timestamp"), (int, float))
    ]
    if timestamp_values:
        features["timestamp"] = _scalar_stats(timestamp_values)

    for key in ("observation.state", "action"):
        vectors = [
            [float(value) for value in row[key]]
            for row in frame_rows
            if isinstance(row.get(key), list) and row[key]
        ]
        if vectors:
            features[key] = _vector_stats(vectors)

    result: dict[str, Any] = {"features": features}
    if not features:
        result["note"] = "Statistics are not materialized because no frame rows were exported."
    return result


def _scalar_stats(values: list[float]) -> dict[str, list[float]]:
    return _vector_stats([[value] for value in values])


def _vector_stats(vectors: list[list[float]]) -> dict[str, list[float]]:
    dim = max(len(vector) for vector in vectors)
    columns = [
        [vector[index] for vector in vectors if index < len(vector) and math.isfinite(vector[index])]
        for index in range(dim)
    ]
    return {
        "mean": [_mean(column) for column in columns],
        "std": [_std(column) for column in columns],
        "min": [min(column) if column else 0.0 for column in columns],
        "max": [max(column) if column else 0.0 for column in columns],
    }


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _feature_schema(
    frame_rows: list[dict[str, Any]],
    video_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    features = {
        "timestamp": {"dtype": "float32", "shape": [1], "names": None},
        "episode_index": {"dtype": "int64", "shape": [1], "names": None},
        "frame_index": {"dtype": "int64", "shape": [1], "names": None},
        "index": {"dtype": "int64", "shape": [1], "names": None},
        "task_index": {"dtype": "int64", "shape": [1], "names": None},
        "source_episode_index": {"dtype": "int64", "shape": [1], "names": None},
        "source_task_index": {"dtype": "int64", "shape": [1], "names": None},
    }
    state_dim = _first_vector_dim_from_rows(frame_rows, "observation.state")
    action_dim = _first_vector_dim_from_rows(frame_rows, "action")
    if state_dim is not None:
        features["observation.state"] = {
            "dtype": "float32",
            "shape": [state_dim],
            "names": None,
        }
    if action_dim is not None:
        features["action"] = {
            "dtype": "float32",
            "shape": [action_dim],
            "names": None,
        }
    for video_key in sorted({str(row["video_key"]) for row in video_rows if row.get("video_key")}):
        features[video_key] = {
            "dtype": "video",
            "shape": [3, 0, 0],
            "names": ["channel", "height", "width"],
        }
    return features


def _first_vector_dim_from_rows(rows: list[dict[str, Any]], key: str) -> int | None:
    for row in rows:
        value = row.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)
    except TypeError:
        return []


def _timestamp_at(timestamps: list[Any], frame_index: int, fps: float) -> float:
    if frame_index < len(timestamps) and isinstance(timestamps[frame_index], (int, float)):
        return float(timestamps[frame_index])
    return frame_index / fps


def _numeric_list_at(values: list[Any], frame_index: int) -> list[float] | None:
    if frame_index >= len(values):
        return None
    value = values[frame_index]
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return [float(value)]
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _safe_path_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value.strip())
    return safe.strip("._-") or "camera"


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


def _write_optional_tasks_parquet(path: Path, rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    try:
        import pandas as pd
    except ImportError:
        return _write_optional_parquet(path, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame(rows)
    if "task" in dataframe:
        dataframe = dataframe.set_index("task")
    try:
        dataframe.to_parquet(path)
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
    return True


def _read_optional_parquet(path: Path) -> list[dict[str, Any]] | None:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return None
    try:
        return pq.read_table(path).to_pylist()
    except Exception:
        return None
