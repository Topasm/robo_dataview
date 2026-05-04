from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.frames import FrameRecord
from apps.api.services.pydantic_compat import model_dump
from packages.robot_schema import build_annotations_pyarrow_schema


LANCE_SUBSET_VERSION = "robot_data_studio_lance_subset_v1"
METADATA_JSON_PATH = Path("metadata.json")
EPISODES_LANCE_PATH = Path("episodes.lance")
FRAMES_LANCE_PATH = Path("frames.lance")
VIDEOS_LANCE_PATH = Path("videos.lance")
ANNOTATIONS_LANCE_PATH = Path("annotations.lance")


class LanceExportDependencyError(RuntimeError):
    pass


def write_lance_subset(
    export_dir: Path,
    *,
    dataset_id: str,
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    frames_by_episode: dict[int, list[FrameRecord]],
    video_blobs_by_episode: dict[int, dict[str, bytes]] | None = None,
    version_description: str | None,
) -> dict[str, Any]:
    """Write a real Lance subset for selected episodes.

    JSON manifests are useful diagnostics, but `format=lance` should produce
    `.lance` tables or fail loudly when the optional Lance stack is unavailable.
    """

    try:
        import pyarrow as pa
        import lance
    except ImportError as exc:
        raise LanceExportDependencyError(
            "Install optional pyarrow and lance dependencies to export Lance subsets."
        ) from exc

    root = export_dir / "lance_subset"
    root.mkdir(parents=True, exist_ok=True)

    episode_rows = _episode_rows(episodes, annotations_by_episode)
    frame_rows = [
        _frame_row(frame)
        for episode in episodes
        for frame in frames_by_episode.get(episode.episode_index, [])
    ]
    annotation_rows = [
        _annotation_row(annotation)
        for annotations in annotations_by_episode.values()
        for annotation in annotations
    ]
    video_rows = _video_rows(episodes, video_blobs_by_episode or {})

    table_paths = {
        "episodes": root / EPISODES_LANCE_PATH,
        "frames": root / FRAMES_LANCE_PATH,
        "videos": root / VIDEOS_LANCE_PATH,
        "annotations": root / ANNOTATIONS_LANCE_PATH,
    }
    _write_lance_table(lance, _table_from_rows(pa, episode_rows, _episodes_schema(pa)), table_paths["episodes"])
    _write_lance_table(lance, _table_from_rows(pa, frame_rows, _frames_schema(pa)), table_paths["frames"])
    _write_lance_table(lance, _table_from_rows(pa, video_rows, _videos_schema(pa)), table_paths["videos"])
    _write_lance_table(
        lance,
        _table_from_rows(pa, annotation_rows, build_annotations_pyarrow_schema()),
        table_paths["annotations"],
    )

    metadata = {
        "dataset_id": dataset_id,
        "format": LANCE_SUBSET_VERSION,
        "version_description": version_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_episodes": len(episode_rows),
        "total_frames": len(frame_rows),
        "total_videos": len(video_rows),
        "total_annotations": len(annotation_rows),
        "tables": {name: path.name for name, path in table_paths.items()},
    }
    metadata_path = root / METADATA_JSON_PATH
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    validation = validate_lance_subset(root)
    validation_path = root / "validation.json"
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "format": LANCE_SUBSET_VERSION,
        "root": str(root),
        "validation": validation,
        "files": {
            "metadata": str(metadata_path),
            "validation": str(validation_path),
            "episodes": str(table_paths["episodes"]),
            "frames": str(table_paths["frames"]),
            "videos": str(table_paths["videos"]),
            "annotations": str(table_paths["annotations"]),
        },
        "materialized": {
            "episode_rows": len(episode_rows),
            "frame_rows": len(frame_rows),
            "video_rows": len(video_rows),
            "annotation_rows": len(annotation_rows),
        },
    }


def validate_lance_subset(root: Path) -> dict[str, Any]:
    metadata_path = root / METADATA_JSON_PATH
    paths = {
        "metadata": metadata_path,
        "episodes": root / EPISODES_LANCE_PATH,
        "frames": root / FRAMES_LANCE_PATH,
        "videos": root / VIDEOS_LANCE_PATH,
        "annotations": root / ANNOTATIONS_LANCE_PATH,
    }
    present = {name: path.exists() for name, path in paths.items()}
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}

    if not present["metadata"]:
        errors.append("missing metadata.json")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("format") != LANCE_SUBSET_VERSION:
            warnings.append(f"unexpected format {metadata.get('format')!r}")

    for table_name in ("episodes", "frames", "videos", "annotations"):
        if not present[table_name]:
            errors.append(f"missing {table_name}.lance")

    table_readability = _lance_table_readability(paths, present)
    for name, status in table_readability.items():
        if not status.get("present"):
            continue
        label = str(status["label"])
        readable = status.get("readable")
        if readable is False:
            errors.append(f"{label} is not readable as Lance: {status.get('error')}")
        elif readable is None:
            warnings.append(f"{label} could not be verified because {status.get('error')}")
    errors.extend(
        _lance_table_row_count_errors(
            table_readability,
            {
                "episodes": int(metadata.get("total_episodes") or 0),
                "frames": int(metadata.get("total_frames") or 0),
                "videos": int(metadata.get("total_videos") or 0),
                "annotations": int(metadata.get("total_annotations") or 0),
            },
        )
    )

    return {
        "metadata_ok": not errors,
        "episode_count": int(metadata.get("total_episodes") or 0),
        "frame_count": int(metadata.get("total_frames") or 0),
        "video_count": int(metadata.get("total_videos") or 0),
        "annotation_count": int(metadata.get("total_annotations") or 0),
        "files": {name: str(path) for name, path in paths.items()},
        "present": present,
        "table_readability": table_readability,
        "errors": errors,
        "warnings": warnings,
    }


def _lance_table_readability(
    paths: dict[str, Path],
    present: dict[str, bool],
) -> dict[str, dict[str, Any]]:
    labels = {
        "episodes": "episodes.lance",
        "frames": "frames.lance",
        "videos": "videos.lance",
        "annotations": "annotations.lance",
    }
    return {
        name: _lance_table_status(paths[name], label=label, present=present[name])
        for name, label in labels.items()
    }


def _lance_table_status(path: Path, *, label: str, present: bool) -> dict[str, Any]:
    if not present:
        return {
            "present": False,
            "checked": False,
            "readable": False,
            "row_count": None,
            "label": label,
            "error": "table is not present",
        }
    try:
        import lance
    except ImportError as exc:
        return {
            "present": True,
            "checked": False,
            "readable": None,
            "row_count": None,
            "label": label,
            "error": f"lance is unavailable: {exc}",
        }
    try:
        dataset = lance.dataset(str(path))
        row_count = _lance_row_count(dataset)
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
        "row_count": row_count,
        "label": label,
        "error": None,
    }


def _lance_row_count(dataset: Any) -> int:
    if hasattr(dataset, "count_rows"):
        return int(dataset.count_rows())
    table = dataset.to_table()
    return int(getattr(table, "num_rows", 0))


def _lance_table_row_count_errors(
    table_readability: dict[str, dict[str, Any]],
    expected_rows: dict[str, int],
) -> list[str]:
    errors = []
    for name, expected in expected_rows.items():
        status = table_readability.get(name, {})
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


def _episode_rows(
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
) -> list[dict[str, Any]]:
    return [
        {
            "dataset_id": episode.dataset_id,
            "episode_index": episode.episode_index,
            "task_index": episode.task_index,
            "length": episode.length,
            "fps": episode.fps,
            "success_label": episode.success_label,
            "failure_reason": episode.failure_reason,
            "quality_score": episode.quality_score,
            "review_status": episode.review_status,
            "caption": episode.caption,
            "split": episode.split,
            "language_instruction": episode.language_instruction,
            "camera_names": episode.camera_names,
            "duration_seconds": episode.duration_seconds,
            "accepted_annotation_count": len(annotations_by_episode.get(episode.episode_index, [])),
        }
        for episode in episodes
    ]


def _frame_row(frame: FrameRecord) -> dict[str, Any]:
    return {
        "dataset_id": frame.dataset_id,
        "episode_index": frame.episode_index,
        "frame_index": frame.frame_index,
        "timestamp": frame.timestamp,
        "task_index": frame.task_index,
        "observation_state": frame.observation_state,
        "action": frame.action,
        "state_norm": frame.state_norm,
        "action_norm": frame.action_norm,
        "is_bad_frame": frame.is_bad_frame,
    }


def _video_rows(
    episodes: list[EpisodeDetail],
    video_blobs_by_episode: dict[int, dict[str, bytes]],
) -> list[dict[str, Any]]:
    rows = []
    for episode in episodes:
        for camera, blob in sorted(video_blobs_by_episode.get(episode.episode_index, {}).items()):
            if not blob:
                continue
            video_key = _safe_path_name(camera)
            filename = f"episode_{int(episode.episode_index):06d}.mp4"
            rows.append(
                {
                    "dataset_id": episode.dataset_id,
                    "episode_index": episode.episode_index,
                    "camera": camera,
                    "video_key": video_key,
                    "relative_path": f"videos/{video_key}/{filename}",
                    "filename": filename,
                    "file_size_bytes": len(blob),
                    "video_blob": blob,
                }
            )
    return rows


def _annotation_row(annotation: AnnotationRecord) -> dict[str, Any]:
    return {
        **model_dump(annotation),
        "source": annotation.source.value,
        "review_status": annotation.review_status.value,
    }


def _write_lance_table(lance: Any, table: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lance.write_dataset(table, str(path), mode="overwrite")


def _table_from_rows(pa: Any, rows: list[dict[str, Any]], schema: Any) -> Any:
    return pa.Table.from_pylist(rows, schema=schema)


def _episodes_schema(pa: Any) -> Any:
    return pa.schema(
        [
            pa.field("dataset_id", pa.string(), nullable=False),
            pa.field("episode_index", pa.int64(), nullable=False),
            pa.field("task_index", pa.int64()),
            pa.field("length", pa.int64()),
            pa.field("fps", pa.float32()),
            pa.field("success_label", pa.bool_()),
            pa.field("failure_reason", pa.string()),
            pa.field("quality_score", pa.float32()),
            pa.field("review_status", pa.string(), nullable=False),
            pa.field("caption", pa.string()),
            pa.field("split", pa.string()),
            pa.field("language_instruction", pa.string()),
            pa.field("camera_names", pa.list_(pa.string())),
            pa.field("duration_seconds", pa.float32()),
            pa.field("accepted_annotation_count", pa.int64(), nullable=False),
        ]
    )


def _frames_schema(pa: Any) -> Any:
    return pa.schema(
        [
            pa.field("dataset_id", pa.string(), nullable=False),
            pa.field("episode_index", pa.int64(), nullable=False),
            pa.field("frame_index", pa.int64(), nullable=False),
            pa.field("timestamp", pa.float32()),
            pa.field("task_index", pa.int64()),
            pa.field("observation_state", pa.list_(pa.float32())),
            pa.field("action", pa.list_(pa.float32())),
            pa.field("state_norm", pa.float32()),
            pa.field("action_norm", pa.float32()),
            pa.field("is_bad_frame", pa.bool_(), nullable=False),
        ]
    )


def _videos_schema(pa: Any) -> Any:
    return pa.schema(
        [
            pa.field("dataset_id", pa.string(), nullable=False),
            pa.field("episode_index", pa.int64(), nullable=False),
            pa.field("camera", pa.string(), nullable=False),
            pa.field("video_key", pa.string(), nullable=False),
            pa.field("relative_path", pa.string(), nullable=False),
            pa.field("filename", pa.string(), nullable=False),
            pa.field("file_size_bytes", pa.int64(), nullable=False),
            pa.field("video_blob", pa.binary(), nullable=False),
        ]
    )


def _safe_path_name(value: str) -> str:
    safe = "".join(character if character.isalnum() else "_" for character in value.strip())
    return "_".join(part for part in safe.split("_") if part) or "camera"
