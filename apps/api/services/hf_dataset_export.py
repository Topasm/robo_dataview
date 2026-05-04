from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.pydantic_compat import model_dump


HF_DATASET_EXPORT_FORMAT = "robot_data_studio_hf_dataset_frames_v1"


class HFDatasetExportDependencyError(RuntimeError):
    pass


def write_hf_dataset_export(
    export_dir: Path,
    *,
    dataset_id: str,
    episodes: list[EpisodeDetail],
    annotations_by_episode: dict[int, list[AnnotationRecord]],
    timeseries_by_episode: dict[int, dict[str, Any]],
    version_description: str | None,
) -> dict[str, Any]:
    rows = [
        row
        for episode in episodes
        for row in _frame_rows(
            episode,
            annotations_by_episode.get(episode.episode_index, []),
            timeseries_by_episode.get(episode.episode_index, {}),
        )
    ]
    if not rows:
        raise HFDatasetExportDependencyError(
            "Hugging Face Dataset export requires materialized frame time-series rows."
        )

    datasets = _datasets_module()
    root = export_dir / "hf_dataset"
    dataset_dir = root / "dataset"
    metadata_path = root / "metadata.json"
    rows_path = root / "frames.jsonl"
    root.mkdir(parents=True, exist_ok=True)

    dataset = datasets.Dataset.from_list(rows)
    dataset.save_to_disk(str(dataset_dir))
    _write_jsonl(rows_path, rows)

    annotation_count = sum(
        len(annotations_by_episode.get(episode.episode_index, []))
        for episode in episodes
    )
    metadata = {
        "dataset_id": dataset_id,
        "format": HF_DATASET_EXPORT_FORMAT,
        "version_description": version_description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "episode_rows": len(episodes),
        "frame_rows": len(rows),
        "annotation_rows": annotation_count,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    validation = validate_hf_dataset_export(root, expected_frame_rows=len(rows))
    return {
        "format": HF_DATASET_EXPORT_FORMAT,
        "root": str(root),
        "validation": validation,
        "files": {
            "metadata": str(metadata_path),
            "dataset": str(dataset_dir),
            "frames_jsonl": str(rows_path),
        },
        "materialized": {
            "episode_rows": len(episodes),
            "frame_rows": len(rows),
            "annotation_rows": metadata["annotation_rows"],
        },
    }


def validate_hf_dataset_export(root: Path, *, expected_frame_rows: int | None = None) -> dict[str, Any]:
    dataset_dir = root / "dataset"
    metadata_path = root / "metadata.json"
    rows_path = root / "frames.jsonl"
    present = {
        "dataset": dataset_dir.exists(),
        "metadata": metadata_path.exists(),
        "frames_jsonl": rows_path.exists(),
    }
    errors: list[str] = []
    warnings: list[str] = []
    if not present["dataset"]:
        errors.append("missing saved Hugging Face dataset directory")
    if not present["metadata"]:
        errors.append("missing metadata.json")
    if not present["frames_jsonl"]:
        errors.append("missing frames.jsonl readability copy")

    frame_rows = _read_jsonl(rows_path) if present["frames_jsonl"] else []
    metadata: dict[str, Any] = {}
    if present["metadata"]:
        try:
            loaded_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"metadata.json is not valid JSON: {exc}")
        else:
            if not isinstance(loaded_metadata, dict):
                errors.append("metadata.json must contain a JSON object")
            else:
                metadata = loaded_metadata
                errors.extend(
                    _validate_metadata_contract(
                        metadata,
                        frame_row_count=len(frame_rows),
                        expected_frame_rows=expected_frame_rows,
                    )
                )

    if expected_frame_rows is not None and len(frame_rows) != expected_frame_rows:
        errors.append("frames.jsonl row count does not match expected frame count")

    load_result = _validate_hf_dataset_load(dataset_dir)
    if load_result["available"] and load_result["ok"]:
        loaded_rows = load_result["num_rows"]
        if expected_frame_rows is not None and loaded_rows != expected_frame_rows:
            errors.append("saved Hugging Face dataset row count does not match expected frame count")
    elif not load_result["available"]:
        warnings.append("datasets is unavailable; saved dataset load validation was skipped")
    else:
        errors.append(f"saved Hugging Face dataset is not loadable: {load_result['error']}")

    return {
        "metadata_ok": not errors,
        "loadable": bool(load_result["available"] and load_result["ok"] and not errors),
        "load": load_result,
        "frame_count": len(frame_rows),
        "metadata": metadata,
        "files": {
            "dataset": str(dataset_dir),
            "metadata": str(metadata_path),
            "frames_jsonl": str(rows_path),
        },
        "present": present,
        "errors": errors,
        "warnings": warnings,
    }


def _datasets_module() -> Any:
    try:
        import datasets
    except ImportError as exc:
        raise HFDatasetExportDependencyError(
            "Hugging Face Dataset export requires the optional `datasets` dependency. "
            'Install it with `python3 -m pip install -e ".[export]"`.'
        ) from exc
    return datasets


def _validate_metadata_contract(
    metadata: dict[str, Any],
    *,
    frame_row_count: int,
    expected_frame_rows: int | None,
) -> list[str]:
    errors: list[str] = []
    if metadata.get("format") != HF_DATASET_EXPORT_FORMAT:
        errors.append("metadata format does not match HF Dataset export format")
    for key in ("episode_rows", "frame_rows", "annotation_rows"):
        value = metadata.get(key)
        if not isinstance(value, int) or value < 0:
            errors.append(f"metadata {key} must be a non-negative integer")
    frame_rows = metadata.get("frame_rows")
    if isinstance(frame_rows, int):
        if frame_rows != frame_row_count:
            errors.append("metadata frame_rows does not match frames.jsonl row count")
        if expected_frame_rows is not None and frame_rows != expected_frame_rows:
            errors.append("metadata frame_rows does not match expected frame count")
    if not isinstance(metadata.get("dataset_id"), str) or not metadata.get("dataset_id"):
        errors.append("metadata dataset_id must be a non-empty string")
    return errors


def _validate_hf_dataset_load(dataset_dir: Path) -> dict[str, Any]:
    try:
        datasets = _datasets_module()
    except HFDatasetExportDependencyError as exc:
        return {
            "available": False,
            "ok": None,
            "num_rows": None,
            "error": str(exc),
        }
    try:
        dataset = datasets.load_from_disk(str(dataset_dir))
    except Exception as exc:
        return {
            "available": True,
            "ok": False,
            "num_rows": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "available": True,
        "ok": True,
        "num_rows": len(dataset),
        "error": None,
    }


def _frame_rows(
    episode: EpisodeDetail,
    annotations: list[AnnotationRecord],
    timeseries: dict[str, Any],
) -> list[dict[str, Any]]:
    timestamps = _sequence(timeseries.get("timestamps"))
    states = _sequence(timeseries.get("states"))
    actions = _sequence(timeseries.get("actions"))
    frame_count = max(len(timestamps), len(states), len(actions), episode.length or 0)
    if frame_count <= 0:
        return []
    fps = episode.fps or 20.0
    annotation_rows = [_annotation_row(annotation) for annotation in annotations]
    annotation_json = json.dumps(annotation_rows, sort_keys=True, default=str)
    return [
        {
            "dataset_id": episode.dataset_id,
            "episode_index": episode.episode_index,
            "frame_index": frame_index,
            "timestamp": _timestamp_at(timestamps, frame_index, fps),
            "task_index": episode.task_index,
            "observation_state": _numeric_list_at(states, frame_index),
            "action": _numeric_list_at(actions, frame_index),
            "instruction": episode.language_instruction or episode.caption,
            "caption": episode.caption,
            "success_label": episode.success_label,
            "failure_reason": episode.failure_reason,
            "quality_score": episode.quality_score,
            "review_status": episode.review_status,
            "split": episode.split,
            "accepted_annotation_count": len(annotation_rows),
            "accepted_annotations_json": annotation_json,
        }
        for frame_index in range(frame_count)
    ]


def _annotation_row(annotation: AnnotationRecord) -> dict[str, Any]:
    row = model_dump(annotation)
    row["source"] = annotation.source.value
    row["review_status"] = annotation.review_status.value
    row["created_at"] = annotation.created_at.isoformat()
    row["updated_at"] = annotation.updated_at.isoformat()
    return row


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
