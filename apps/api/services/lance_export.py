from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.frames import FrameRecord
from apps.api.services.pydantic_compat import model_dump
from packages.robot_schema import (
    build_annotation_events_pyarrow_schema,
    build_annotations_current_pyarrow_schema,
    build_annotations_pyarrow_schema,
    build_episodes_pyarrow_schema,
    build_frames_pyarrow_schema,
    build_media_pyarrow_schema,
    build_raw_videos_pyarrow_schema,
)


LANCE_SUBSET_VERSION = "robot_data_studio_lance_subset_v2"
MANIFEST_JSON_PATH = Path("manifest.json")
METADATA_JSON_PATH = Path("metadata.json")
EPISODES_LANCE_PATH = Path("episodes.lance")
FRAMES_LANCE_PATH = Path("frames.lance")
MEDIA_LANCE_PATH = Path("media.lance")
TRAIN_EPISODES_LANCE_PATH = Path("train_episodes.lance")
ANNOTATIONS_CURRENT_LANCE_PATH = Path("annotations_current.lance")
ANNOTATION_EVENTS_LANCE_PATH = Path("annotation_events.lance")
LEGACY_VIDEOS_LANCE_PATH = Path("videos.lance")
LEGACY_ANNOTATIONS_LANCE_PATH = Path("annotations.lance")


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

    frame_rows = sorted(
        [
            _frame_row(frame)
            for episode in episodes
            for frame in frames_by_episode.get(episode.episode_index, [])
        ],
        key=lambda row: (int(row["episode_index"]), int(row["frame_index"])),
    )
    episode_rows = _episode_rows(
        episodes,
        annotations_by_episode,
        frames_by_episode,
        video_blobs_by_episode or {},
    )
    annotation_rows = [
        _annotation_row(annotation)
        for annotations in annotations_by_episode.values()
        for annotation in annotations
    ]
    annotation_event_rows: list[dict[str, Any]] = []
    media_rows = _media_rows(episodes, video_blobs_by_episode or {})
    camera_feature_keys = _camera_feature_keys(episodes, video_blobs_by_episode or {})
    state_dim = _first_vector_dim(
        row.get("observation_state")
        for row in frame_rows
    )
    action_dim = _first_vector_dim(
        row.get("action")
        for row in frame_rows
    )
    fps = _representative_fps(episodes)

    table_paths = {
        "episodes": root / EPISODES_LANCE_PATH,
        "frames": root / FRAMES_LANCE_PATH,
        "media": root / MEDIA_LANCE_PATH,
        "train_episodes": root / TRAIN_EPISODES_LANCE_PATH,
        "annotations_current": root / ANNOTATIONS_CURRENT_LANCE_PATH,
        "annotation_events": root / ANNOTATION_EVENTS_LANCE_PATH,
        "videos": root / LEGACY_VIDEOS_LANCE_PATH,
        "annotations": root / LEGACY_ANNOTATIONS_LANCE_PATH,
    }
    _write_lance_table(
        lance,
        _table_from_rows(pa, episode_rows, build_episodes_pyarrow_schema(camera_feature_keys)),
        table_paths["episodes"],
    )
    _write_lance_table(
        lance,
        _table_from_rows(pa, frame_rows, build_frames_pyarrow_schema()),
        table_paths["frames"],
    )
    _write_lance_table(
        lance,
        _table_from_rows(pa, media_rows, build_media_pyarrow_schema()),
        table_paths["media"],
    )
    _write_lance_table(
        lance,
        _table_from_rows(pa, episode_rows, build_episodes_pyarrow_schema(camera_feature_keys)),
        table_paths["train_episodes"],
    )
    _write_lance_table(
        lance,
        _table_from_rows(pa, annotation_rows, build_annotations_current_pyarrow_schema()),
        table_paths["annotations_current"],
    )
    _write_lance_table(
        lance,
        _table_from_rows(pa, annotation_event_rows, build_annotation_events_pyarrow_schema()),
        table_paths["annotation_events"],
    )
    _write_lance_table(
        lance,
        _table_from_rows(pa, media_rows, build_raw_videos_pyarrow_schema()),
        table_paths["videos"],
    )
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
        "total_media": len(media_rows),
        "total_videos": len(media_rows),
        "total_annotations": len(annotation_rows),
        "total_annotation_events": len(annotation_event_rows),
        "state_dim": state_dim,
        "action_dim": action_dim,
        "fps": fps,
        "primary_training_table": table_paths["train_episodes"].name,
        "training_columns": {
            "state": "observation_state",
            "action": "actions",
        },
        "frame_table": {
            "index_columns": ["episode_index", "frame_index"],
            "state_column": "observation_state",
            "action_column": "action",
            "sorted_by": ["episode_index", "frame_index"],
            "state_dim_consistent": _vectors_have_consistent_dim(
                row.get("observation_state")
                for row in frame_rows
            ),
            "action_dim_consistent": _vectors_have_consistent_dim(
                row.get("action")
                for row in frame_rows
            ),
        },
        "tables": {name: path.name for name, path in table_paths.items()},
        "canonical_tables": {
            "episodes": table_paths["episodes"].name,
            "frames": table_paths["frames"].name,
            "media": table_paths["media"].name,
            "train_episodes": table_paths["train_episodes"].name,
            "annotations_current": table_paths["annotations_current"].name,
            "annotation_events": table_paths["annotation_events"].name,
        },
        "legacy_tables": {
            "videos": table_paths["videos"].name,
            "annotations": table_paths["annotations"].name,
        },
    }
    manifest_path = root / MANIFEST_JSON_PATH
    metadata_path = root / METADATA_JSON_PATH
    manifest_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    validation = validate_lance_subset(root)
    validation_path = root / "validation.json"
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "format": LANCE_SUBSET_VERSION,
        "root": str(root),
        "validation": validation,
        "files": {
            "manifest": str(manifest_path),
            "metadata": str(metadata_path),
            "validation": str(validation_path),
            "episodes": str(table_paths["episodes"]),
            "frames": str(table_paths["frames"]),
            "media": str(table_paths["media"]),
            "train_episodes": str(table_paths["train_episodes"]),
            "annotations_current": str(table_paths["annotations_current"]),
            "annotation_events": str(table_paths["annotation_events"]),
            "videos": str(table_paths["videos"]),
            "annotations": str(table_paths["annotations"]),
        },
        "materialized": {
            "episode_rows": len(episode_rows),
            "frame_rows": len(frame_rows),
            "media_rows": len(media_rows),
            "train_episode_rows": len(episode_rows),
            "video_rows": len(media_rows),
            "annotation_current_rows": len(annotation_rows),
            "annotation_event_rows": len(annotation_event_rows),
            "annotation_rows": len(annotation_rows),
        },
    }


def validate_lance_subset(root: Path) -> dict[str, Any]:
    manifest_path = root / MANIFEST_JSON_PATH
    metadata_path = root / METADATA_JSON_PATH
    paths = {
        "manifest": manifest_path,
        "metadata": metadata_path,
        "episodes": root / EPISODES_LANCE_PATH,
        "frames": root / FRAMES_LANCE_PATH,
        "media": root / MEDIA_LANCE_PATH,
        "train_episodes": root / TRAIN_EPISODES_LANCE_PATH,
        "annotations_current": root / ANNOTATIONS_CURRENT_LANCE_PATH,
        "annotation_events": root / ANNOTATION_EVENTS_LANCE_PATH,
        "videos": root / LEGACY_VIDEOS_LANCE_PATH,
        "annotations": root / LEGACY_ANNOTATIONS_LANCE_PATH,
    }
    present = {name: path.exists() for name, path in paths.items()}
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}

    metadata_source_path = (
        metadata_path
        if present["metadata"]
        else manifest_path
        if present["manifest"]
        else None
    )
    if metadata_source_path is None:
        errors.append("missing manifest.json or metadata.json")
    else:
        metadata = json.loads(metadata_source_path.read_text(encoding="utf-8"))
        if metadata.get("format") != LANCE_SUBSET_VERSION:
            warnings.append(f"unexpected format {metadata.get('format')!r}")
        if not present["manifest"]:
            warnings.append("manifest.json is missing; metadata.json was used as a legacy fallback")

    for table_name in (
        "episodes",
        "frames",
        "media",
        "train_episodes",
        "annotations_current",
        "annotation_events",
    ):
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
                "media": int(metadata.get("total_media") or metadata.get("total_videos") or 0),
                "train_episodes": int(metadata.get("total_episodes") or 0),
                "annotations_current": int(metadata.get("total_annotations") or 0),
                "annotation_events": int(metadata.get("total_annotation_events") or 0),
                "videos": int(metadata.get("total_media") or metadata.get("total_videos") or 0),
                "annotations": int(metadata.get("total_annotations") or 0),
            },
        )
    )
    frame_contract = metadata.get("frame_table") if isinstance(metadata, dict) else None
    if isinstance(frame_contract, dict):
        if frame_contract.get("state_dim_consistent") is False:
            warnings.append("frame_table observation_state dimensions are not consistent")
        if frame_contract.get("action_dim_consistent") is False:
            warnings.append("frame_table action dimensions are not consistent")

    return {
        "metadata_ok": not errors,
        "episode_count": int(metadata.get("total_episodes") or 0),
        "frame_count": int(metadata.get("total_frames") or 0),
        "media_count": int(metadata.get("total_media") or metadata.get("total_videos") or 0),
        "train_episode_count": int(metadata.get("total_episodes") or 0),
        "video_count": int(metadata.get("total_videos") or 0),
        "annotation_count": int(metadata.get("total_annotations") or 0),
        "annotation_current_count": int(metadata.get("total_annotations") or 0),
        "annotation_event_count": int(metadata.get("total_annotation_events") or 0),
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
        "media": "media.lance",
        "train_episodes": "train_episodes.lance",
        "annotations_current": "annotations_current.lance",
        "annotation_events": "annotation_events.lance",
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
    frames_by_episode: dict[int, list[FrameRecord]],
    video_blobs_by_episode: dict[int, dict[str, bytes]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    created_at = datetime.now(timezone.utc)
    for episode in episodes:
        frames = sorted(
            frames_by_episode.get(episode.episode_index, []),
            key=lambda frame: frame.frame_index,
        )
        timestamps = [frame.timestamp for frame in frames]
        timestamp_values = [timestamp for timestamp in timestamps if timestamp is not None]
        row: dict[str, Any] = {
            "episode_id": _episode_id(episode.episode_index),
            "episode_index": episode.episode_index,
            "task_id": _task_id(episode.task_index),
            "task_index": episode.task_index,
            "num_frames": len(frames) or episode.length,
            "fps": episode.fps,
            "length": episode.length,
            "start_time": min(timestamp_values) if timestamp_values else None,
            "end_time": max(timestamp_values) if timestamp_values else None,
            "timestamps": timestamps,
            "observation_state": [frame.observation_state for frame in frames],
            "actions": [frame.action for frame in frames],
            "language_instruction": episode.language_instruction,
            "episode_caption": episode.caption,
            "success_label": episode.success_label,
            "failure_reason": episode.failure_reason,
            "quality_score": episode.quality_score,
            "review_status": episode.review_status,
            "train_val_test_split": episode.split,
            "split": episode.split,
            "created_at": created_at,
            "dataset_version": None,
        }
        if len(annotations_by_episode.get(episode.episode_index, [])) > 0:
            row["review_status"] = row["review_status"] or "accepted"
        for camera, blob in sorted(video_blobs_by_episode.get(episode.episode_index, {}).items()):
            if not blob:
                continue
            key = _normalize_feature_key(camera)
            row[f"{key}_video_blob"] = blob
            row[f"{key}_from_timestamp"] = row["start_time"]
            row[f"{key}_to_timestamp"] = row["end_time"]
        rows.append(row)
    return rows


def _frame_row(frame: FrameRecord) -> dict[str, Any]:
    return {
        "episode_id": _episode_id(frame.episode_index),
        "episode_index": frame.episode_index,
        "frame_index": frame.frame_index,
        "global_frame_index": None,
        "timestamp": frame.timestamp,
        "task_id": _task_id(frame.task_index),
        "task_index": frame.task_index,
        "observation_state": frame.observation_state,
        "action": frame.action,
        "is_bad_frame": frame.is_bad_frame,
        "state_norm": frame.state_norm,
        "action_norm": frame.action_norm,
        "phase_label": _first_frame_label(frame, "phase"),
        "vlm_step_caption": _first_frame_label(frame, "caption", source="vlm"),
        "human_step_caption": _first_frame_label(frame, "caption", source="human"),
        "review_status": _first_frame_review_status(frame),
    }


def _media_rows(
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
                    "media_id": f"{_episode_id(episode.episode_index)}:{video_key}",
                    "episode_id": _episode_id(episode.episode_index),
                    "episode_index": episode.episode_index,
                    "camera_id": video_key,
                    "camera_name": camera,
                    "media_type": "video",
                    "uri": None,
                    "relative_path": f"videos/{video_key}/{filename}",
                    "video_blob": blob,
                    "video_path": None,
                    "from_timestamp": 0.0,
                    "to_timestamp": episode.duration_seconds,
                    "num_frames": episode.length,
                    "chunk_index": None,
                    "file_index": None,
                    "sha256": None,
                    "byte_size": len(blob),
                    "width_pixels": None,
                    "height_pixels": None,
                    "fps": episode.fps,
                    "codec": None,
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


def _safe_path_name(value: str) -> str:
    safe = "".join(character if character.isalnum() else "_" for character in value.strip())
    return "_".join(part for part in safe.split("_") if part) or "camera"


def _normalize_feature_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", value)


def _camera_feature_keys(
    episodes: list[EpisodeDetail],
    video_blobs_by_episode: dict[int, dict[str, bytes]],
) -> list[str]:
    keys: set[str] = set()
    for episode in episodes:
        keys.update(
            camera
            for camera, blob in video_blobs_by_episode.get(episode.episode_index, {}).items()
            if blob
        )
    return sorted(keys)


def _episode_id(episode_index: int) -> str:
    return f"episode_{int(episode_index):06d}"


def _task_id(task_index: int | None) -> str | None:
    if task_index is None:
        return None
    return f"task_{int(task_index):06d}"


def _first_frame_label(
    frame: FrameRecord,
    label_type: str,
    *,
    source: str | None = None,
) -> str | None:
    for label in frame.labels:
        if label.label_type != label_type:
            continue
        if source is not None and label.source.value != source:
            continue
        return label.label_value
    return None


def _first_frame_review_status(frame: FrameRecord) -> str | None:
    if not frame.labels:
        return None
    return frame.labels[0].review_status.value


def _first_vector_dim(values: Any) -> int | None:
    for value in values:
        if isinstance(value, list):
            return len(value)
    return None


def _vectors_have_consistent_dim(values: Any) -> bool:
    expected: int | None = None
    for value in values:
        if value is None:
            continue
        if not isinstance(value, list):
            return False
        if expected is None:
            expected = len(value)
            continue
        if len(value) != expected:
            return False
    return True


def _representative_fps(episodes: list[EpisodeDetail]) -> float | None:
    for episode in episodes:
        if episode.fps is not None:
            return episode.fps
    return None
