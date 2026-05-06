from __future__ import annotations

from datetime import datetime, timezone
from importlib.resources import files as resource_files
import json
import os
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
    build_episode_metadata_pyarrow_schema,
    build_episodes_pyarrow_schema,
    build_frame_skill_labels_pyarrow_schema,
    build_frames_pyarrow_schema,
    build_media_pyarrow_schema,
    build_raw_videos_pyarrow_schema,
    build_skill_segments_pyarrow_schema,
    build_skills_pyarrow_schema,
    build_train_skill_clips_pyarrow_schema,
)


LANCE_SUBSET_VERSION = "robot_data_studio_lance_subset_v2"
MANIFEST_JSON_PATH = Path("manifest.json")
METADATA_JSON_PATH = Path("metadata.json")
EPISODES_LANCE_PATH = Path("episodes.lance")
FRAMES_LANCE_PATH = Path("frames.lance")
MEDIA_LANCE_PATH = Path("media.lance")
TRAIN_EPISODES_LANCE_PATH = Path("train_episodes.lance")
TRAIN_SKILL_CLIPS_LANCE_PATH = Path("train_skill_clips.lance")
SKILLS_LANCE_PATH = Path("skills.lance")
SKILL_SEGMENTS_LANCE_PATH = Path("skill_segments.lance")
FRAME_SKILL_LABELS_LANCE_PATH = Path("frame_skill_labels.lance")
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
    clip_export_options: dict[str, Any] | None = None,
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

    write_legacy = _env_flag(
        "ROBOT_DATA_STUDIO_WRITE_LEGACY_EXPORT_TABLES", default=False
    )
    write_media_blobs = _env_flag(
        "ROBOT_DATA_STUDIO_EXPORT_MEDIA_BLOBS", default=False
    )

    frame_rows = sorted(
        [
            _frame_row(frame)
            for episode in episodes
            for frame in frames_by_episode.get(episode.episode_index, [])
        ],
        key=lambda row: (int(row["episode_index"]), int(row["frame_index"])),
    )
    episode_metadata_rows = _episode_metadata_rows(
        episodes,
        annotations_by_episode,
        frames_by_episode,
    )
    train_episode_rows = _train_episode_rows(
        episodes,
        annotations_by_episode,
        frames_by_episode,
        video_blobs_by_episode or {},
    )
    clip_export = clip_export_options or {}
    materialize_skill_clips = bool(clip_export.get("materialize_skill_clips"))
    clip_label_type = str(clip_export.get("clip_label_type") or "skill")
    accepted_only = bool(clip_export.get("accepted_clips_only", True))
    skill_segment_rows = _skill_segment_rows(
        annotations_by_episode,
        clip_label_type=clip_label_type,
        accepted_only=accepted_only,
    )
    skill_rows = _skill_vocabulary_rows()
    frame_skill_label_rows = (
        _frame_skill_label_rows(skill_segment_rows)
        if materialize_skill_clips
        else []
    )
    train_skill_clip_rows = (
        _train_skill_clip_rows(
            episodes,
            annotations_by_episode,
            frames_by_episode,
            video_blobs_by_episode or {},
            clip_label_type=clip_label_type,
            accepted_only=accepted_only,
        )
        if materialize_skill_clips
        else []
    )
    annotation_rows = [
        _annotation_row(annotation)
        for annotations in annotations_by_episode.values()
        for annotation in annotations
    ]
    annotation_event_rows: list[dict[str, Any]] = []
    media_rows = _media_rows(
        episodes,
        video_blobs_by_episode or {},
        include_blobs=write_media_blobs,
    )
    legacy_video_rows = (
        _media_rows(episodes, video_blobs_by_episode or {}, include_blobs=True)
        if write_legacy
        else []
    )
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

    canonical_paths = {
        "episodes": root / EPISODES_LANCE_PATH,
        "frames": root / FRAMES_LANCE_PATH,
        "media": root / MEDIA_LANCE_PATH,
        "train_episodes": root / TRAIN_EPISODES_LANCE_PATH,
        "annotations_current": root / ANNOTATIONS_CURRENT_LANCE_PATH,
        "annotation_events": root / ANNOTATION_EVENTS_LANCE_PATH,
    }
    if materialize_skill_clips:
        canonical_paths["skills"] = root / SKILLS_LANCE_PATH
        canonical_paths["skill_segments"] = root / SKILL_SEGMENTS_LANCE_PATH
        canonical_paths["frame_skill_labels"] = root / FRAME_SKILL_LABELS_LANCE_PATH
        canonical_paths["train_skill_clips"] = root / TRAIN_SKILL_CLIPS_LANCE_PATH
    legacy_paths: dict[str, Path] = {}
    if write_legacy:
        legacy_paths = {
            "videos": root / LEGACY_VIDEOS_LANCE_PATH,
            "annotations": root / LEGACY_ANNOTATIONS_LANCE_PATH,
        }
    table_paths = {**canonical_paths, **legacy_paths}

    # episodes.lance is metadata-only; training-grade blobs live in train_episodes.lance.
    _write_lance_table(
        lance,
        _table_from_rows(pa, episode_metadata_rows, build_episode_metadata_pyarrow_schema()),
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
        _table_from_rows(
            pa,
            train_episode_rows,
            build_episodes_pyarrow_schema(camera_feature_keys),
        ),
        table_paths["train_episodes"],
    )
    if materialize_skill_clips:
        _write_lance_table(
            lance,
            _table_from_rows(pa, skill_rows, build_skills_pyarrow_schema()),
            table_paths["skills"],
        )
        _write_lance_table(
            lance,
            _table_from_rows(pa, skill_segment_rows, build_skill_segments_pyarrow_schema()),
            table_paths["skill_segments"],
        )
        _write_lance_table(
            lance,
            _table_from_rows(
                pa,
                frame_skill_label_rows,
                build_frame_skill_labels_pyarrow_schema(),
            ),
            table_paths["frame_skill_labels"],
        )
        _write_lance_table(
            lance,
            _table_from_rows(
                pa,
                train_skill_clip_rows,
                build_train_skill_clips_pyarrow_schema(camera_feature_keys),
            ),
            table_paths["train_skill_clips"],
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
    if write_legacy:
        _write_lance_table(
            lance,
            _table_from_rows(pa, legacy_video_rows, build_raw_videos_pyarrow_schema()),
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
        "total_episodes": len(train_episode_rows),
        "total_frames": len(frame_rows),
        "total_media": len(media_rows),
        "total_skill_segments": len(skill_segment_rows),
        "total_skills": len(skill_rows) if materialize_skill_clips else 0,
        "total_frame_skill_labels": len(frame_skill_label_rows),
        "total_train_skill_clips": len(train_skill_clip_rows),
        "total_videos": len(legacy_video_rows) if write_legacy else 0,
        "total_annotations": len(annotation_rows),
        "total_annotation_events": len(annotation_event_rows),
        "state_dim": state_dim,
        "action_dim": action_dim,
        "fps": fps,
        "primary_training_table": (
            table_paths["train_skill_clips"].name
            if train_skill_clip_rows
            else table_paths["train_episodes"].name
        ),
        "training_row_unit": "skill_clip" if train_skill_clip_rows else "episode",
        "training_index_column": "episode_index",
        "source_episode_column": "source_episode_index" if train_skill_clip_rows else None,
        "video_frame_offset_column": "video_frame_offset" if train_skill_clip_rows else None,
        "training_columns": {
            "state": "observation_state",
            "action": "actions",
        },
        "skill_vocabulary": (
            {
                "table": table_paths["skills"].name,
                "source": "packages/robot_schema/humanoid_skills.json",
            }
            if materialize_skill_clips
            else None
        ),
        "camera_keys": camera_feature_keys,
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
        "blob_storage": {
            "episodes": "metadata_only",
            "train_episodes": "video_blob_columns",
            "train_skill_clips": "source_video_blob_columns" if train_skill_clip_rows else "absent",
            "media": "video_blob_column" if write_media_blobs else "metadata_only",
        },
        "clip_export": {
            **clip_export,
            "skill_segments": len(skill_segment_rows),
            "skills": len(skill_rows) if materialize_skill_clips else 0,
            "frame_skill_labels": len(frame_skill_label_rows),
            "train_skill_clips": len(train_skill_clip_rows),
        },
        "tables": {name: path.name for name, path in table_paths.items()},
        "canonical_tables": {name: path.name for name, path in canonical_paths.items()},
        "legacy_tables": {name: path.name for name, path in legacy_paths.items()},
    }
    manifest_path = root / MANIFEST_JSON_PATH
    metadata_path = root / METADATA_JSON_PATH
    manifest_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    validation = validate_lance_subset(root)
    validation_path = root / "validation.json"
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

    files: dict[str, str] = {
        "manifest": str(manifest_path),
        "metadata": str(metadata_path),
        "validation": str(validation_path),
    }
    files.update({name: str(path) for name, path in table_paths.items()})

    materialized: dict[str, int] = {
        "episode_rows": len(episode_metadata_rows),
        "frame_rows": len(frame_rows),
        "media_rows": len(media_rows),
        "train_episode_rows": len(train_episode_rows),
        "skill_rows": len(skill_rows) if materialize_skill_clips else 0,
        "skill_segment_rows": len(skill_segment_rows),
        "frame_skill_label_rows": len(frame_skill_label_rows),
        "train_skill_clip_rows": len(train_skill_clip_rows),
        "annotation_current_rows": len(annotation_rows),
        "annotation_event_rows": len(annotation_event_rows),
    }
    if write_legacy:
        materialized["video_rows"] = len(legacy_video_rows)
        materialized["annotation_rows"] = len(annotation_rows)

    return {
        "format": LANCE_SUBSET_VERSION,
        "root": str(root),
        "validation": validation,
        "files": files,
        "materialized": materialized,
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
        "skills": root / SKILLS_LANCE_PATH,
        "skill_segments": root / SKILL_SEGMENTS_LANCE_PATH,
        "frame_skill_labels": root / FRAME_SKILL_LABELS_LANCE_PATH,
        "train_skill_clips": root / TRAIN_SKILL_CLIPS_LANCE_PATH,
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
                "skills": int(metadata.get("total_skills") or 0),
                "skill_segments": int(metadata.get("total_skill_segments") or 0),
                "frame_skill_labels": int(metadata.get("total_frame_skill_labels") or 0),
                "train_skill_clips": int(metadata.get("total_train_skill_clips") or 0),
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
        "skill_count": int(metadata.get("total_skills") or 0),
        "skill_segment_count": int(metadata.get("total_skill_segments") or 0),
        "frame_skill_label_count": int(metadata.get("total_frame_skill_labels") or 0),
        "train_skill_clip_count": int(metadata.get("total_train_skill_clips") or 0),
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
        "skills": "skills.lance",
        "skill_segments": "skill_segments.lance",
        "frame_skill_labels": "frame_skill_labels.lance",
        "train_skill_clips": "train_skill_clips.lance",
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


def _episode_metadata_rows(
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    frames_by_episode: dict[int, list[FrameRecord]],
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
        rows.append(row)
    return rows


def _train_episode_rows(
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    frames_by_episode: dict[int, list[FrameRecord]],
    video_blobs_by_episode: dict[int, dict[str, bytes]],
) -> list[dict[str, Any]]:
    rows = _episode_metadata_rows(episodes, annotations_by_episode, frames_by_episode)
    for row, episode in zip(rows, episodes, strict=False):
        frames = sorted(
            frames_by_episode.get(episode.episode_index, []),
            key=lambda frame: frame.frame_index,
        )
        row["timestamps"] = [frame.timestamp for frame in frames]
        row["observation_state"] = [frame.observation_state for frame in frames]
        row["actions"] = [frame.action for frame in frames]
        for camera, blob in sorted(video_blobs_by_episode.get(episode.episode_index, {}).items()):
            if not blob:
                continue
            key = _normalize_feature_key(camera)
            row[f"{key}_video_blob"] = blob
            row[f"{key}_from_timestamp"] = row["start_time"]
            row[f"{key}_to_timestamp"] = row["end_time"]
    return rows


def _skill_segment_rows(
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    *,
    clip_label_type: str,
    accepted_only: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode_index, annotations in sorted(annotations_by_episode.items()):
        for annotation in sorted(annotations, key=lambda row: (row.start_frame, row.end_frame)):
            if annotation.label_type != clip_label_type:
                continue
            if accepted_only and annotation.review_status.value != "accepted":
                continue
            metadata = dict(annotation.metadata or {})
            rows.append(
                {
                    "clip_id": annotation.annotation_id,
                    "source_episode_index": int(episode_index),
                    "skill_id": _int_or_none(metadata.get("skillId", metadata.get("skill_id"))),
                    "skill_name": annotation.label_value,
                    "start_frame": int(annotation.start_frame),
                    "end_frame": int(annotation.end_frame),
                    "length": int(annotation.end_frame - annotation.start_frame + 1),
                    "quality_score": _float_or_none(
                        metadata.get("qualityScore", metadata.get("quality_score"))
                    ),
                    "success_label": _bool_or_none(
                        metadata.get("successLabel", metadata.get("success_label"))
                    ),
                    "failure_reason": _string_or_none(
                        metadata.get("failureReason", metadata.get("failure_reason"))
                    ),
                    "review_status": annotation.review_status.value,
                    "split": _string_or_none(metadata.get("split")),
                    "metadata_json": json.dumps(metadata, sort_keys=True),
                }
            )
    return rows


def _skill_vocabulary_rows() -> list[dict[str, Any]]:
    try:
        raw = json.loads(
            resource_files("packages.robot_schema")
            .joinpath("humanoid_skills.json")
            .read_text(encoding="utf-8")
        )
    except Exception:
        raw = [
            {"skill_id": 0, "skill_name": "approach", "display_label": "Approach"},
            {"skill_id": 1, "skill_name": "grasp_part", "display_label": "Grasp Part"},
            {"skill_id": 2, "skill_name": "grasp_bolt", "display_label": "Grasp Bolt"},
            {"skill_id": 3, "skill_name": "insert_bolt", "display_label": "Insert Bolt"},
            {"skill_id": 4, "skill_name": "place", "display_label": "Place"},
            {"skill_id": 5, "skill_name": "push_button", "display_label": "Push Button"},
            {"skill_id": 6, "skill_name": "grasp_drill", "display_label": "Grasp Drill"},
            {"skill_id": 7, "skill_name": "drill_trigger", "display_label": "Drill Trigger"},
            {"skill_id": 8, "skill_name": "bimanual_grasp", "display_label": "Bimanual Grasp"},
            {"skill_id": 9, "skill_name": "insert_tire", "display_label": "Insert Tire"},
        ]
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "skill_id": int(item.get("skill_id", len(rows))),
                "skill_name": str(item.get("skill_name") or ""),
                "display_label": str(item.get("display_label") or item.get("skill_name") or ""),
                "start_condition": _string_or_none(item.get("start_condition")),
                "end_condition": _string_or_none(item.get("end_condition")),
                "mission_section": _string_or_none(item.get("mission_section")),
                "color": _string_or_none(item.get("color")),
            }
        )
    return rows


def _frame_skill_label_rows(skill_segment_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in skill_segment_rows:
        start_frame = int(segment["start_frame"])
        end_frame = int(segment["end_frame"])
        denominator = max(1, end_frame - start_frame)
        for frame_index in range(start_frame, end_frame + 1):
            rows.append(
                {
                    "episode_index": int(segment["source_episode_index"]),
                    "frame_index": frame_index,
                    "segment_id": str(segment["clip_id"]),
                    "skill_id": _int_or_none(segment.get("skill_id")),
                    "skill_name": str(segment["skill_name"]),
                    "progress_in_skill": float(frame_index - start_frame) / float(denominator),
                    "review_status": str(segment["review_status"]),
                }
            )
    return rows


def _train_skill_clip_rows(
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    frames_by_episode: dict[int, list[FrameRecord]],
    video_blobs_by_episode: dict[int, dict[str, bytes]],
    *,
    clip_label_type: str,
    accepted_only: bool,
) -> list[dict[str, Any]]:
    episodes_by_index = {int(episode.episode_index): episode for episode in episodes}
    rows: list[dict[str, Any]] = []
    clip_index = 0
    for source_episode_index, annotations in sorted(annotations_by_episode.items()):
        episode = episodes_by_index.get(int(source_episode_index))
        if episode is None:
            continue
        frames = sorted(
            frames_by_episode.get(source_episode_index, []),
            key=lambda frame: frame.frame_index,
        )
        if not frames:
            continue
        frames_by_index = {int(frame.frame_index): frame for frame in frames}
        for annotation in sorted(annotations, key=lambda row: (row.start_frame, row.end_frame)):
            if annotation.label_type != clip_label_type:
                continue
            if accepted_only and annotation.review_status.value != "accepted":
                continue
            start_frame = max(0, int(annotation.start_frame))
            end_frame = min(int(annotation.end_frame), max(frames_by_index))
            clip_frames = [
                frames_by_index[index]
                for index in range(start_frame, end_frame + 1)
                if index in frames_by_index
            ]
            if not clip_frames:
                continue
            timestamps = [frame.timestamp for frame in clip_frames]
            timestamp_values = [timestamp for timestamp in timestamps if timestamp is not None]
            metadata = dict(annotation.metadata or {})
            row: dict[str, Any] = {
                "clip_id": annotation.annotation_id,
                "source_episode_index": int(source_episode_index),
                "skill_id": _int_or_none(metadata.get("skillId", metadata.get("skill_id"))),
                "skill_name": annotation.label_value,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "video_frame_offset": start_frame,
                "episode_id": f"skill_clip_{clip_index:06d}",
                "episode_index": clip_index,
                "task_id": _task_id(episode.task_index),
                "task_index": episode.task_index,
                "num_frames": len(clip_frames),
                "fps": episode.fps,
                "length": len(clip_frames),
                "start_time": min(timestamp_values) if timestamp_values else None,
                "end_time": max(timestamp_values) if timestamp_values else None,
                "timestamps": timestamps,
                "observation_state": [frame.observation_state for frame in clip_frames],
                "actions": [frame.action for frame in clip_frames],
                "language_instruction": episode.language_instruction,
                "episode_caption": episode.caption,
                "success_label": _bool_or_none(
                    metadata.get("successLabel", metadata.get("success_label"))
                ),
                "failure_reason": _string_or_none(
                    metadata.get("failureReason", metadata.get("failure_reason"))
                ),
                "quality_score": _float_or_none(
                    metadata.get("qualityScore", metadata.get("quality_score"))
                ),
                "review_status": annotation.review_status.value,
                "train_val_test_split": _string_or_none(metadata.get("split")) or episode.split,
                "split": _string_or_none(metadata.get("split")) or episode.split,
                "created_at": datetime.now(timezone.utc),
                "dataset_version": None,
            }
            for camera, blob in sorted(video_blobs_by_episode.get(source_episode_index, {}).items()):
                if not blob:
                    continue
                key = _normalize_feature_key(camera)
                row[f"{key}_video_blob"] = blob
                row[f"{key}_from_timestamp"] = row["start_time"]
                row[f"{key}_to_timestamp"] = row["end_time"]
            rows.append(row)
            clip_index += 1
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
    *,
    include_blobs: bool,
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
                    "video_blob": blob if include_blobs else None,
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
            _normalize_feature_key(camera)
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


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _representative_fps(episodes: list[EpisodeDetail]) -> float | None:
    for episode in episodes:
        if episode.fps is not None:
            return episode.fps
    return None


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}
