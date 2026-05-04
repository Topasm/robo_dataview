from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.pydantic_compat import model_dump


def write_jsonl_export(
    export_dir: Path,
    *,
    dataset_id: str,
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    version_description: str | None,
) -> dict[str, Any]:
    root = export_dir / "jsonl_export"
    root.mkdir(parents=True, exist_ok=True)
    episodes_path = root / "episodes.jsonl"
    captions_path = root / "captions.jsonl"
    annotations_path = root / "annotations.jsonl"
    metadata_path = root / "metadata.json"

    episode_rows = [_episode_row(episode) for episode in episodes]
    caption_rows = [_caption_row(episode) for episode in episodes]
    annotation_rows = [
        _annotation_row(annotation)
        for annotations in annotations_by_episode.values()
        for annotation in annotations
    ]
    _write_jsonl(episodes_path, episode_rows)
    _write_jsonl(captions_path, caption_rows)
    _write_jsonl(annotations_path, annotation_rows)
    metadata = _metadata(
        dataset_id=dataset_id,
        format_name="robot_data_studio_jsonl_export_v1",
        version_description=version_description,
        episode_rows=len(episode_rows),
        annotation_rows=len(annotation_rows),
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "format": metadata["format"],
        "root": str(root),
        "files": {
            "metadata": str(metadata_path),
            "episodes": str(episodes_path),
            "captions": str(captions_path),
            "annotations": str(annotations_path),
        },
        "materialized": {
            "episode_rows": len(episode_rows),
            "caption_rows": len(caption_rows),
            "annotation_rows": len(annotation_rows),
        },
    }


def write_vla_jsonl_export(
    export_dir: Path,
    *,
    dataset_id: str,
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    timeseries_by_episode: dict[int, dict[str, Any]],
    version_description: str | None,
) -> dict[str, Any]:
    root = export_dir / "vla_export"
    root.mkdir(parents=True, exist_ok=True)
    examples_path = root / "examples.jsonl"
    metadata_path = root / "metadata.json"
    rows = [
        _vla_row(
            episode,
            annotations_by_episode.get(episode.episode_index, []),
            timeseries_by_episode.get(episode.episode_index, {}),
        )
        for episode in episodes
    ]
    _write_jsonl(examples_path, rows)
    metadata = _metadata(
        dataset_id=dataset_id,
        format_name="robot_data_studio_vla_jsonl_v1",
        version_description=version_description,
        episode_rows=len(rows),
        annotation_rows=sum(len(annotations_by_episode.get(episode.episode_index, [])) for episode in episodes),
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "format": metadata["format"],
        "root": str(root),
        "files": {
            "metadata": str(metadata_path),
            "examples": str(examples_path),
        },
        "materialized": {
            "example_rows": len(rows),
        },
    }


def _metadata(
    *,
    dataset_id: str,
    format_name: str,
    version_description: str | None,
    episode_rows: int,
    annotation_rows: int,
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "format": format_name,
        "version_description": version_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "episode_rows": episode_rows,
        "annotation_rows": annotation_rows,
    }


def _episode_row(episode: EpisodeDetail) -> dict[str, Any]:
    return model_dump(episode)


def _caption_row(episode: EpisodeDetail) -> dict[str, Any]:
    return {
        "dataset_id": episode.dataset_id,
        "episode_index": episode.episode_index,
        "task_index": episode.task_index,
        "instruction": episode.language_instruction or episode.caption,
        "caption": episode.caption,
        "success_label": episode.success_label,
        "failure_reason": episode.failure_reason,
        "quality_score": episode.quality_score,
        "review_status": episode.review_status,
        "split": episode.split,
    }


def _annotation_row(annotation: AnnotationRecord) -> dict[str, Any]:
    row = model_dump(annotation)
    row["source"] = annotation.source.value
    row["review_status"] = annotation.review_status.value
    row["created_at"] = annotation.created_at.isoformat()
    row["updated_at"] = annotation.updated_at.isoformat()
    return row


def _vla_row(
    episode: EpisodeDetail,
    annotations: list[AnnotationRecord],
    timeseries: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dataset_id": episode.dataset_id,
        "episode_index": episode.episode_index,
        "task_index": episode.task_index,
        "instruction": episode.language_instruction or episode.caption,
        "caption": episode.caption,
        "success_label": episode.success_label,
        "failure_reason": episode.failure_reason,
        "quality_score": episode.quality_score,
        "review_status": episode.review_status,
        "split": episode.split,
        "fps": episode.fps,
        "frame_count": episode.length,
        "timestamps": timeseries.get("timestamps"),
        "observation_state": timeseries.get("states"),
        "action": timeseries.get("actions"),
        "accepted_annotations": [_annotation_row(annotation) for annotation in annotations],
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )
