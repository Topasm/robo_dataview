from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from apps.api.schemas.datasets import (
    ActionSemantics,
    DatasetHealth,
    DatasetOpenRequest,
    DatasetRecord,
    DatasetSummary,
    DatasetTableHealth,
)
from apps.api.schemas.episodes import (
    EpisodeDetail,
    EpisodeLabelHistoryRecord,
    EpisodeLabelUpdate,
    EpisodeListItem,
    EpisodeListPage,
    EpisodeTimeseries,
    StateActionSummary,
)
from apps.api.schemas.frames import FrameRecord
from apps.api.schemas.search import FilterSearchRequest, SearchResult
from apps.api.services.lance_filter import LanceFilterEngine
from apps.api.services.lerobot_io import read_lerobot_snapshot_episodes
from apps.api.services.pydantic_compat import model_dump
from packages.robot_schema import (
    build_episode_label_history_pyarrow_schema,
    build_episode_labels_pyarrow_schema,
)

NORM_SERIES_MAX_POINTS = 600
EPISODE_LABEL_STORAGE_ROOT = Path("data/lance/episode_labels")
DATASET_REGISTRY_PATH = Path("data/lance/dataset_registry.jsonl")
TABLE_NAMES = (
    "episodes",
    "frames",
    "videos",
)
STATE_COLUMNS = ("observation_state", "observation.state", "state")
ACTION_COLUMNS = ("actions", "action")
TIMESTAMP_COLUMNS = ("timestamps", "timestamp")
FRAME_INDEX_COLUMNS = ("frame_index", "frame_idx", "index")
FRAME_TIMESTAMP_COLUMNS = ("timestamp", "timestamps")
VIDEO_CAMERA_COLUMNS = ("camera_id", "camera_angle", "camera", "camera_name", "video_key")
VIDEO_BLOB_COLUMNS = ("video_blob", "blob", "mp4_blob", "video")
VIDEO_CHUNK_COLUMNS = ("chunk_index", "chunk")
VIDEO_FILE_COLUMNS = ("file_index", "file")
VIDEO_PATH_COLUMNS = ("video_file", "relative_path", "path", "filename")
EPISODE_TEXT_COLUMNS = ("episode_caption", "caption", "language_instruction", "instruction")
FILTER_ALIASES = {
    "success": "success_label",
    "quality": "quality_score",
    "status": "review_status",
    "review": "review_status",
    "task": "task_index",
    "episode": "episode_index",
}
EPISODE_SORT_FIELDS = {
    "episode_index",
    "task_index",
    "length",
    "success_label",
    "quality_score",
    "review_status",
    "caption",
    "failure_reason",
    "split",
}
EPISODE_OVERLAY_FIELDS = {
    "success_label",
    "quality_score",
    "review_status",
    "caption",
    "failure_reason",
    "split",
    "language_instruction",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "dataset"


def _has_uri_scheme(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value))


def _local_path_from_uri(value: str) -> Path | None:
    if value.startswith("file://"):
        return Path(value.removeprefix("file://"))
    if _has_uri_scheme(value):
        return None
    return Path(value)


def _join_uri(base_uri: str, child: str) -> str:
    if _has_uri_scheme(base_uri):
        return f"{base_uri.rstrip('/')}/{child}"
    return str(Path(base_uri) / child)


def _table_uri(base_uri: str, table_name: str) -> str:
    if base_uri.rstrip("/").endswith(".lance"):
        return base_uri
    return _join_uri(base_uri, f"{table_name}.lance")


def _normalize_camera_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", value)


def _fetch_text_uri(uri: str) -> str | None:
    if uri.startswith("hf://"):
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            return None
        parts = uri.removeprefix("hf://").rstrip("/").split("/")
        if len(parts) < 4 or parts[0] != "datasets":
            return None
        repo_id = f"{parts[1]}/{parts[2]}"
        filename = "/".join(parts[3:])
        try:
            local_path = hf_hub_download(repo_id=repo_id, filename=filename, repo_type="dataset")
        except Exception:
            return None
        try:
            return Path(local_path).read_text(encoding="utf-8")
        except OSError:
            return None
    if uri.startswith(("http://", "https://")):
        try:
            with urlopen(uri, timeout=15) as response:
                return response.read().decode("utf-8")
        except Exception:
            return None
    candidate = _local_path_from_uri(uri)
    if candidate is not None and candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def _lerobot_info_candidate_uris(uri: str | None) -> list[str]:
    if not uri:
        return []
    base = uri.rstrip("/")
    candidates: list[str] = [_join_uri(base, "meta/info.json")]
    if "/" in base:
        parent = base.rsplit("/", 1)[0]
        if parent and parent != base:
            candidates.append(_join_uri(parent, "meta/info.json"))
    return candidates


def _iter_lerobot_info(uri: str | None) -> Iterator[dict[str, Any]]:
    for candidate in _lerobot_info_candidate_uris(uri):
        try:
            text = _fetch_text_uri(candidate)
        except Exception:
            continue
        if text is None:
            continue
        try:
            info = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(info, dict):
            yield info


def _load_lerobot_camera_info(uri: str) -> dict[str, dict[str, Any]] | None:
    """Read a sibling LeRobot ``meta/info.json`` (when present) and extract
    per-camera encoding metadata. Returns ``None`` if no info.json is found
    or no video features can be parsed. Best-effort: any unexpected error
    while probing degrades to ``None`` rather than raising."""

    for info in _iter_lerobot_info(uri):
        camera_info = _camera_info_from_features(info.get("features"))
        if camera_info is not None:
            return camera_info
    return None


def _state_action_dims_from_info(uri: str | None) -> tuple[int | None, int | None]:
    """Read ``meta/info.json`` and return ``(state_dim, action_dim)`` derived
    from the ``observation.state`` and ``action`` feature shapes. Returns
    ``(None, None)`` when info.json or the features can't be parsed."""

    for info in _iter_lerobot_info(uri):
        state_dim, action_dim = _state_action_dims_from_features(info.get("features"))
        if state_dim is not None or action_dim is not None:
            return state_dim, action_dim
    return None, None


def _state_action_dims_from_features(features: Any) -> tuple[int | None, int | None]:
    if not isinstance(features, dict):
        return None, None

    def _dim(key: str) -> int | None:
        feature = features.get(key)
        if not isinstance(feature, dict):
            return None
        shape = feature.get("shape")
        if isinstance(shape, (list, tuple)) and shape:
            try:
                return int(shape[0])
            except (TypeError, ValueError):
                return None
        return None

    return _dim("observation.state"), _dim("action")


def _joint_names_from_features(
    features: Any,
) -> tuple[list[str] | None, list[str] | None]:
    if not isinstance(features, dict):
        return None, None

    def _names(key: str) -> list[str] | None:
        feature = features.get(key)
        if not isinstance(feature, dict):
            return None
        names = feature.get("names")
        if isinstance(names, (list, tuple)) and names:
            return [str(n) for n in names]
        return None

    return _names("observation.state"), _names("action")


def _joint_names_from_info(
    uri: str | None,
) -> tuple[list[str] | None, list[str] | None]:
    """LeRobot v2.1+ info.json features carry per-dim names — pull them out
    so charts can label series with joint names instead of s0/s1/..."""
    for info in _iter_lerobot_info(uri):
        state_names, action_names = _joint_names_from_features(info.get("features"))
        if state_names or action_names:
            return state_names, action_names
    return None, None


PUBLISHED_LANCE_FORMAT = "rllab_published_lance_dataset_v2"
PUBLISHED_LANCE_FORMATS = {PUBLISHED_LANCE_FORMAT}


def _read_manifest(uri: str | None) -> dict[str, Any] | None:
    if not uri:
        return None
    candidate = _join_uri(uri.rstrip("/"), "manifest.json")
    try:
        text = _fetch_text_uri(candidate)
    except Exception:
        return None
    if text is None:
        return None
    try:
        manifest = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    return manifest


def _read_published_manifest(uri: str) -> dict[str, Any] | None:
    """Return manifest.json only when it carries the published Lance marker."""

    manifest = _read_manifest(uri)
    if manifest is None or manifest.get("format") not in PUBLISHED_LANCE_FORMATS:
        return None
    schema_version = str(manifest.get("schema_version", ""))
    if not schema_version.startswith("2."):
        return None
    return manifest


def _manifest_table_path(manifest: dict[str, Any], logical_name: str) -> str | None:
    tables = manifest.get("tables")
    if not isinstance(tables, dict):
        return None
    entry = tables.get(logical_name)
    if isinstance(entry, str) and entry:
        return entry
    if isinstance(entry, dict):
        path = entry.get("path")
        if isinstance(path, str) and path:
            return path
    return None


def _manifest_registry_entry(
    manifest: dict[str, Any] | None,
    registry_name: str,
    key: str,
) -> str | None:
    if not isinstance(manifest, dict):
        return None
    registry = manifest.get("modalities") if registry_name == "modalities" else manifest.get("actions")
    if not isinstance(registry, dict):
        return None
    entry_name = "state.body" if registry_name == "modalities" else "action.body"
    entry = registry.get(entry_name)
    if not isinstance(entry, dict):
        return None
    value = entry.get(key)
    return str(value) if isinstance(value, str) and value else None


def _bundle_state_column(bundle: "LanceBundle") -> str | None:
    return _manifest_registry_entry(bundle.published_manifest, "modalities", "column")


def _bundle_action_column(bundle: "LanceBundle") -> str | None:
    return _manifest_registry_entry(bundle.published_manifest, "actions", "column")


def _bundle_frame_state_column(bundle: "LanceBundle") -> str | None:
    return _manifest_registry_entry(bundle.published_manifest, "modalities", "frame_column")


def _bundle_frame_action_column(bundle: "LanceBundle") -> str | None:
    return _manifest_registry_entry(bundle.published_manifest, "actions", "frame_column")


def _joint_names_from_manifest(
    uri: str | None,
) -> tuple[list[str] | None, list[str] | None]:
    """Pull joint labels from RLLAB manifests.

    v2 published bundles keep names in meta/info.json and point to them via
    registry names_ref fields. v1/raw collection bundles carry joint_order.
    """
    manifest = _read_manifest(uri)
    if manifest is None:
        return None, None

    def _names_from_ref(ref: Any) -> list[str] | None:
        if not isinstance(ref, str) or not ref.startswith("meta/info.json#/"):
            return None
        for info in _iter_lerobot_info(uri):
            value: Any = info
            for part in ref.removeprefix("meta/info.json#/").split("/"):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return None
            if isinstance(value, (list, tuple)) and value:
                return [str(n) for n in value]
        return None

    def _generic_vector_names(names: list[str] | None) -> bool:
        if not names:
            return True
        return all(
            re.fullmatch(r"(?:joint|state|action|dim|q)_\d+", name) is not None
            for name in names
        )

    def _layout_names(entry: dict[str, Any]) -> list[str] | None:
        semantics = entry.get("semantics")
        if not isinstance(semantics, dict):
            return None
        layout = semantics.get("joint_layout")
        if not isinstance(layout, dict):
            return None
        joint_order = layout.get("joint_order")
        if isinstance(joint_order, list) and joint_order:
            return [str(n) for n in joint_order]
        return None

    modalities = manifest.get("modalities")
    actions = manifest.get("actions")
    state_names: list[str] | None = None
    action_names: list[str] | None = None
    if isinstance(modalities, dict):
        state_entry = modalities.get("state.body")
        if isinstance(state_entry, dict):
            state_names = _names_from_ref(state_entry.get("names_ref"))
            if _generic_vector_names(state_names):
                state_names = _layout_names(state_entry) or state_names
    if isinstance(actions, dict):
        training_targets = manifest.get("training_targets")
        action_key = None
        if isinstance(training_targets, list) and training_targets:
            action_key = training_targets[0]
        elif len(actions) == 1:
            action_key = next(iter(actions))
        action_entry = actions.get(action_key) if isinstance(action_key, str) else None
        if isinstance(action_entry, dict):
            action_names = _names_from_ref(action_entry.get("names_ref"))
            if _generic_vector_names(action_names):
                action_names = _layout_names(action_entry) or action_names
    if state_names is not None or action_names is not None:
        return state_names, action_names

    joint_order = manifest.get("joint_order")
    if isinstance(joint_order, list) and joint_order:
        names = [str(n) for n in joint_order]
        return names, names
    return None, None


def _camera_info_from_features(
    features: dict[str, Any] | None,
) -> dict[str, dict[str, Any]] | None:
    if not isinstance(features, dict):
        return None
    cameras: dict[str, dict[str, Any]] = {}
    for key, feature in features.items():
        if not isinstance(feature, dict) or feature.get("dtype") != "video":
            continue
        details: dict[str, Any] = {}
        shape = feature.get("shape")
        if isinstance(shape, (list, tuple)) and len(shape) >= 2:
            details["height"] = int(shape[0]) if shape[0] is not None else None
            details["width"] = int(shape[1]) if shape[1] is not None else None
            if len(shape) >= 3 and shape[2] is not None:
                details["channels"] = int(shape[2])
        # Both our writer (`video_info`) and standard LeRobot (`info`) store
        # the codec details under a sub-dict keyed by `video.*` names.
        sub = feature.get("info") or feature.get("video_info") or {}
        if isinstance(sub, dict):
            for source_key, target_key in (
                ("video.fps", "fps"),
                ("video.codec", "codec"),
                ("video.pix_fmt", "pix_fmt"),
                ("video.height", "height"),
                ("video.width", "width"),
                ("video.channels", "channels"),
                ("video.is_depth_map", "is_depth_map"),
                ("video.has_audio", "has_audio"),
            ):
                if source_key in sub and sub[source_key] is not None:
                    details[target_key] = sub[source_key]
        if details:
            cameras[_normalize_camera_name(key)] = details
    return cameras or None


def _schema_names(dataset: Any) -> list[str]:
    schema = getattr(dataset, "schema", None)
    if schema is None:
        return []
    names = getattr(schema, "names", None)
    if names is not None:
        return list(names)
    return [field.name for field in schema]


def _count_rows(dataset: Any) -> int:
    if hasattr(dataset, "count_rows"):
        return int(dataset.count_rows())
    table = dataset.to_table()
    return int(getattr(table, "num_rows", 0))


_DIRTY_REVIEW_STATES = {"accepted", "edited"}


def _count_dirty_annotations(dataset_id: str, episode_index: int) -> int:
    """Count human annotations that have not been included in any export yet.

    Imported lazily inside the function so the lance_store module stays free
    of import cycles with annotation_service.
    """

    from apps.api.services.annotation_service import annotation_store

    count = 0
    for record in annotation_store.list(dataset_id, episode_index=episode_index):
        if record.applied_export_id is not None:
            continue
        status = getattr(record.review_status, "value", record.review_status)
        if status in _DIRTY_REVIEW_STATES:
            count += 1
    return count


def _rows_from_table(table: Any) -> list[dict[str, Any]]:
    if table is None:
        return []
    if hasattr(table, "to_pylist"):
        return table.to_pylist()
    if hasattr(table, "to_pydict"):
        pydict = table.to_pydict()
        keys = list(pydict)
        row_count = len(pydict[keys[0]]) if keys else 0
        return [{key: pydict[key][idx] for key in keys} for idx in range(row_count)]
    return list(table)


def _read_rows(
    dataset: Any,
    columns: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    row_count = _count_rows(dataset)
    if row_count == 0 or limit <= 0 or offset >= row_count:
        return []
    end = min(offset + limit, row_count)
    indices = list(range(offset, end))
    if hasattr(dataset, "take"):
        return _rows_from_table(dataset.take(indices, columns=columns))
    if hasattr(dataset, "head") and offset == 0:
        return _rows_from_table(dataset.head(limit, columns=columns))
    table = dataset.to_table(columns=columns)
    return _rows_from_table(table)[offset:end]


def _iter_binary_range(
    handle: Any,
    start: int,
    end: int,
    chunk_size: int,
) -> Iterator[bytes]:
    if hasattr(handle, "seek"):
        handle.seek(start)
    else:
        remaining_skip = start
        while remaining_skip > 0:
            skipped = handle.read(min(chunk_size, remaining_skip))
            if not skipped:
                return
            remaining_skip -= len(skipped)
    remaining = end - start + 1
    while remaining > 0:
        chunk = handle.read(min(chunk_size, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        yield chunk


def _video_source_from_blob_file(blob_file: Any) -> VideoSource | None:
    try:
        if hasattr(blob_file, "seek") and hasattr(blob_file, "tell"):
            blob_file.seek(0, 2)
            size = int(blob_file.tell())
            blob_file.seek(0)
            if size <= 0:
                blob_file.close()
                return None
            return VideoSource(size=size, reader=blob_file)
        blob = blob_file.read()
        blob_file.close()
        if not blob:
            return None
        return VideoSource(size=len(blob), data=blob)
    except Exception:
        if hasattr(blob_file, "close"):
            blob_file.close()
        raise


def _read_episode_row_by_index(
    dataset: Any,
    episode_index: int,
    columns: list[str] | None = None,
) -> dict[str, Any] | None:
    if hasattr(dataset, "scanner"):
        try:
            scanner = dataset.scanner(
                columns=columns,
                filter=f"episode_index = {episode_index}",
                limit=1,
            )
            rows = _rows_from_table(scanner.to_table())
            if rows:
                return rows[0]
        except Exception:
            pass
    try:
        rows = _read_rows(dataset, columns=columns, limit=1, offset=episode_index)
    except Exception:
        rows = []
    if rows and int(rows[0].get("episode_index", episode_index)) == episode_index:
        return rows[0]
    # Fallback for gappy / non-contiguous episode_index: locate the actual
    # row offset by scanning only the episode_index column, then re-fetch
    # with the requested column projection.
    try:
        index_rows = _read_rows(
            dataset, columns=["episode_index"], limit=_count_rows(dataset)
        )
    except Exception:
        return None
    target_offset: int | None = None
    for offset, row in enumerate(index_rows):
        if int(row.get("episode_index", -1)) == episode_index:
            target_offset = offset
            break
    if target_offset is None:
        return None
    try:
        rows = _read_rows(dataset, columns=columns, limit=1, offset=target_offset)
    except Exception:
        return None
    if rows and int(rows[0].get("episode_index", episode_index)) == episode_index:
        return rows[0]
    return None


def _safe_len(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return len(value)
    except TypeError:
        return None


def _first_present(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _first_present_name(names: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in names:
            return candidate
    return None


def _unique_columns(schema_names: list[str], candidates: list[str | None]) -> list[str]:
    columns: list[str] = []
    for candidate in candidates:
        if candidate is not None and candidate in schema_names and candidate not in columns:
            columns.append(candidate)
    return columns


def _numeric_vector(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return []
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


def _norm_from_vector(vector: list[float] | None) -> float | None:
    if not vector:
        return None
    return math.sqrt(sum(value * value for value in vector))


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _vector_dim(sequence: Any) -> int | None:
    if sequence is None:
        return None
    if isinstance(sequence, (int, float)):
        return 1
    for item in sequence:
        vector = _numeric_vector(item)
        if vector:
            return len(vector)
    return None


def _norm_bounds(sequence: Any) -> tuple[float | None, float | None]:
    length = _safe_len(sequence)
    if not length:
        return None, None
    stride = max(1, length // 2000)
    norms: list[float] = []
    for item in sequence[::stride]:
        vector = _numeric_vector(item)
        if vector:
            norms.append(math.sqrt(sum(value * value for value in vector)))
    if not norms:
        return None, None
    return min(norms), max(norms)


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)
    except TypeError:
        return []


def _norm_at(sequence: list[Any], index: int) -> float | None:
    if index < 0 or index >= len(sequence):
        return None
    vector = _numeric_vector(sequence[index])
    if not vector:
        return None
    return math.sqrt(sum(item * item for item in vector))


def _vector_at(sequence: list[Any], index: int) -> list[float | None] | None:
    if index < 0 or index >= len(sequence):
        return None
    vector = _numeric_vector(sequence[index])
    if not vector:
        return None
    return [value if math.isfinite(value) else None for value in vector]


def _timestamp_at(timestamps: list[Any], index: int) -> float | None:
    if index < 0 or index >= len(timestamps):
        return None
    value = timestamps[index]
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _episode_length(row: dict[str, Any]) -> int | None:
    for key in ("length", "num_frames", "frame_count"):
        value = row.get(key)
        if value is not None:
            return int(value)
    for value in (
        _first_present(row, TIMESTAMP_COLUMNS),
        _first_present(row, ACTION_COLUMNS),
        _first_present(row, STATE_COLUMNS),
    ):
        length = _safe_len(value)
        if length is not None:
            return length
    return None


def _normalize_camera_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _camera_matches(left: Any, right: str) -> bool:
    normalized_left = _normalize_camera_key(left)
    normalized_right = _normalize_camera_key(right)
    return bool(
        normalized_left == normalized_right
        or normalized_left.endswith(f"_{normalized_right}")
        or normalized_right.endswith(f"_{normalized_left}")
    )


def _display_camera_name(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("observation.images."):
        return text.removeprefix("observation.images.")
    if text.startswith("observation_images_"):
        return text.removeprefix("observation_images_")
    return text


def _video_modalities_from_manifest(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    modalities = manifest.get("modalities")
    if not isinstance(modalities, dict):
        return []
    out: list[dict[str, Any]] = []
    for name, entry in modalities.items():
        if not isinstance(entry, dict) or entry.get("kind") != "video":
            continue
        out.append({**entry, "_registry_name": name})
    return out


def _camera_names_from_manifest(manifest: dict[str, Any] | None) -> list[str]:
    cameras: set[str] = set()
    for entry in _video_modalities_from_manifest(manifest):
        value = (
            entry.get("camera_key")
            or entry.get("camera_column")
            or str(entry.get("_registry_name") or "").removeprefix("video.")
        )
        if value:
            cameras.add(_display_camera_name(value))
    return sorted(cameras)


def _camera_names_from_segments(row: dict[str, Any]) -> list[str]:
    cameras: set[str] = set()
    segments = row.get("camera_segments")
    if not isinstance(segments, list):
        return []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        value = segment.get("camera_key") or segment.get("camera_column") or segment.get("camera_id")
        if value:
            cameras.add(_display_camera_name(value))
    return sorted(cameras)


def _camera_segment_media_id(row: dict[str, Any] | None, camera: str) -> str | None:
    if not isinstance(row, dict):
        return None
    segments = row.get("camera_segments")
    if not isinstance(segments, list):
        return None
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        candidates = (
            segment.get("camera_key"),
            segment.get("camera_column"),
            segment.get("camera_id"),
            segment.get("camera_name"),
        )
        if any(candidate is not None and _camera_matches(candidate, camera) for candidate in candidates):
            media_id = segment.get("media_id")
            return str(media_id) if media_id not in (None, "") else None
    return None


def _video_shard_ref(row: dict[str, Any], camera: str) -> tuple[int, int] | None:
    camera_keys = {
        camera,
        _normalize_camera_key(camera),
    }
    for key in list(camera_keys):
        if key.startswith("observation_images_"):
            camera_keys.add(key.removeprefix("observation_images_"))
        else:
            camera_keys.add(f"observation_images_{key}")
    for key in camera_keys:
        chunk = _int_or_none(row.get(f"videos/{key}/chunk_index"))
        file_index = _int_or_none(row.get(f"videos/{key}/file_index"))
        if chunk is not None and file_index is not None:
            return chunk, file_index
    return None


def _read_video_file_from_row(
    base_uri: str,
    row: dict[str, Any],
    path_name: str | None,
) -> bytes | None:
    source = _video_file_source_from_row(base_uri, row, path_name)
    if source is None:
        return None
    return source.read_all()


def _video_file_path_from_row(
    base_uri: str,
    row: dict[str, Any],
    path_name: str | None,
) -> Path | None:
    if path_name is None:
        return None
    raw_path = row.get(path_name)
    if not raw_path:
        return None
    path_text = str(raw_path)
    for candidate in _video_path_candidates(base_uri, path_text):
        if candidate.is_file():
            return candidate
    return None


def _video_file_source_from_row(
    base_uri: str,
    row: dict[str, Any],
    path_name: str | None,
) -> VideoSource | None:
    path = _video_file_path_from_row(base_uri, row, path_name)
    if path is not None:
        return VideoSource(size=path.stat().st_size, path=path)
    if path_name is None:
        return None
    raw_path = row.get(path_name)
    if not raw_path:
        return None
    path_text = str(raw_path)
    for candidate in _video_uri_candidates(base_uri, path_text):
        source = _remote_video_source_from_uri(candidate)
        if source is not None:
            return source
    return None


def _video_path_candidates(base_uri: str, path_text: str) -> list[Path]:
    path = _local_path_from_uri(path_text)
    if path is not None and path.is_absolute():
        return [path]

    base_path = _local_path_from_uri(base_uri)
    if base_path is None:
        return []
    if base_path.suffix == ".lance":
        base_path = base_path.parent

    relative_path = path if path is not None else Path(path_text)
    candidates = [
        base_path / relative_path,
        base_path.parent / relative_path,
    ]
    if len(relative_path.parts) == 1:
        candidates.extend(
            [
                base_path / "videos" / relative_path,
                base_path.parent / "videos" / relative_path,
            ]
        )

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)
    return unique_candidates


def _video_uri_candidates(base_uri: str, path_text: str) -> list[str]:
    local_path = _local_path_from_uri(path_text)
    if local_path is not None and local_path.is_absolute():
        return []
    if _has_uri_scheme(path_text):
        return [path_text]
    if not _has_uri_scheme(base_uri):
        return []

    base_dir = _remote_base_dir(base_uri)
    relative = path_text.strip("/")
    candidates = [
        _join_remote_uri(base_dir, relative),
        _join_remote_uri(_remote_parent_dir(base_dir), relative),
    ]
    if "/" not in relative:
        candidates.extend(
            [
                _join_remote_uri(base_dir, f"videos/{relative}"),
                _join_remote_uri(_remote_parent_dir(base_dir), f"videos/{relative}"),
            ]
        )

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)
    return unique_candidates


def _remote_base_dir(uri: str) -> str:
    base = uri.rstrip("/")
    if base.endswith(".lance"):
        return base.rsplit("/", 1)[0]
    return base


def _remote_parent_dir(uri: str) -> str:
    base = uri.rstrip("/")
    if "/" not in base:
        return base
    return base.rsplit("/", 1)[0]


def _join_remote_uri(base_uri: str, child: str) -> str:
    return f"{base_uri.rstrip('/')}/{child.lstrip('/')}"


def _remote_video_source_from_uri(uri: str) -> VideoSource | None:
    if uri.startswith(("http://", "https://")):
        return _http_video_source_from_uri(uri)
    if uri.startswith("hf://"):
        return _hf_video_source_from_uri(uri)
    return _fsspec_video_source_from_uri(uri)


def _http_video_source_from_uri(uri: str) -> VideoSource | None:
    size = _http_content_length(uri)
    if size is None:
        return None
    return VideoSource(
        size=size,
        range_reader=lambda start, end, chunk_size: _http_range_chunks(uri, start, end, chunk_size),
    )


def _http_content_length(uri: str) -> int | None:
    try:
        request = Request(uri, headers=_remote_auth_headers(uri), method="HEAD")
        with urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length is not None:
                return int(length)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        pass

    try:
        request = Request(
            uri,
            headers={**_remote_auth_headers(uri), "Range": "bytes=0-0"},
            method="GET",
        )
        with urlopen(request, timeout=30) as response:
            content_range = response.headers.get("Content-Range")
            if content_range and "/" in content_range:
                return int(content_range.rsplit("/", 1)[1])
            length = response.headers.get("Content-Length")
            if length is not None:
                return int(length)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return None
    return None


def _http_range_chunks(uri: str, start: int, end: int, chunk_size: int) -> Iterator[bytes]:
    request = Request(
        uri,
        headers={**_remote_auth_headers(uri), "Range": f"bytes={start}-{end}"},
        method="GET",
    )
    with urlopen(request, timeout=60) as response:
        if getattr(response, "getcode", lambda: None)() == 206:
            remaining = end - start + 1
            while remaining > 0:
                chunk = response.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
            return
        yield from _iter_binary_range(response, start, end, chunk_size)


def _remote_auth_headers(uri: str) -> dict[str, str]:
    if "huggingface.co" not in uri and "hf.co" not in uri:
        return {}
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _hf_video_source_from_uri(uri: str) -> VideoSource | None:
    try:
        from huggingface_hub import HfFileSystem
    except ImportError:
        return None
    try:
        fs = HfFileSystem(token=os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN"))
        path = uri.removeprefix("hf://").strip("/")
        size = int(fs.info(path)["size"])
    except Exception:
        return None

    def range_reader(start: int, end: int, chunk_size: int) -> Iterator[bytes]:
        with fs.open(path, "rb") as handle:
            yield from _iter_binary_range(handle, start, end, chunk_size)

    return VideoSource(size=size, range_reader=range_reader)


def _fsspec_video_source_from_uri(uri: str) -> VideoSource | None:
    try:
        from fsspec.core import url_to_fs
    except ImportError:
        return None
    try:
        fs, path = url_to_fs(uri)
        size = int(fs.info(path)["size"])
    except Exception:
        return None

    def range_reader(start: int, end: int, chunk_size: int) -> Iterator[bytes]:
        with fs.open(path, "rb") as handle:
            yield from _iter_binary_range(handle, start, end, chunk_size)

    return VideoSource(size=size, range_reader=range_reader)


def _blob_to_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if hasattr(value, "to_pybytes"):
        return value.to_pybytes()
    if hasattr(value, "read"):
        data = value.read()
        if isinstance(data, bytes):
            return data
    return None


def _metadata_columns(schema_names: list[str], include_arrays: bool = False) -> list[str]:
    columns = []
    for name in schema_names:
        lower_name = name.lower()
        is_blob = "blob" in lower_name or lower_name.endswith("_mp4") or lower_name == "video"
        if is_blob:
            continue
        if not include_arrays and name in set(STATE_COLUMNS + ACTION_COLUMNS):
            continue
        columns.append(name)
    return columns


def _action_semantics_from_manifest(
    manifest: dict[str, Any] | None,
) -> ActionSemantics | None:
    """Pull `manifest.actions.action.body.semantics` out of a v2 manifest.

    Returns None when the registry is absent (legacy bundles, or non-v2
    manifests) so the UI can hide the panel rather than show empty fields.
    """

    if not isinstance(manifest, dict):
        return None
    actions = manifest.get("actions")
    if not isinstance(actions, dict):
        return None
    body = actions.get("action.body")
    if not isinstance(body, dict):
        return None
    semantics = body.get("semantics")
    if not isinstance(semantics, dict):
        return None
    normalized_raw = semantics.get("normalized")
    normalized: bool | None = None
    if isinstance(normalized_raw, bool):
        normalized = normalized_raw

    def _str_or_none(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    return ActionSemantics(
        command_type=_str_or_none(semantics.get("command_type")),
        absolute_or_delta=_str_or_none(semantics.get("absolute_or_delta")),
        units=_str_or_none(semantics.get("units")),
        control_frame=_str_or_none(semantics.get("control_frame")),
        applies_to_interval=_str_or_none(semantics.get("applies_to_interval")),
        normalized=normalized,
    )


def _task_segments_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw_segments = row.get("task_segments")
    if not isinstance(raw_segments, list):
        return []
    segments: list[dict[str, Any]] = []
    for raw in raw_segments:
        if not isinstance(raw, dict):
            continue
        start_frame = _int_or_none(raw.get("start_frame"))
        end_frame_exclusive = _int_or_none(raw.get("end_frame_exclusive"))
        if start_frame is None:
            continue
        if end_frame_exclusive is None:
            legacy_end = _int_or_none(raw.get("end_frame"))
            if legacy_end is None:
                continue
            end_frame_exclusive = legacy_end + 1
        if end_frame_exclusive <= start_frame:
            continue
        segments.append(
            {
                "task_index": _int_or_none(raw.get("task_index")),
                "language_instruction": raw.get("language_instruction"),
                "start_frame": start_frame,
                "end_frame_exclusive": end_frame_exclusive,
                "start_timestamp": _number_or_none(raw.get("start_timestamp")),
                "end_timestamp_exclusive": _number_or_none(
                    raw.get("end_timestamp_exclusive", raw.get("end_timestamp"))
                ),
            }
        )
    return segments


def _parse_filter_query(query: str) -> list[tuple[str, str, Any]]:
    clauses = [clause.strip() for clause in re.split(r"\s+AND\s+", query, flags=re.IGNORECASE)]
    filters: list[tuple[str, str, Any]] = []
    for clause in clauses:
        if not clause:
            continue
        match = re.match(
            r"^\s*([A-Za-z_][\w.]*)\s*(contains|==|!=|>=|<=|=|>|<)\s*(.+?)\s*$",
            clause,
            flags=re.IGNORECASE,
        )
        if match is None:
            raise ValueError(f"Unsupported filter clause: {clause}")
        left, operator, right = match.groups()
        field = FILTER_ALIASES.get(left.strip(), left.strip())
        filters.append((field, "==" if operator == "=" else operator.lower(), _parse_filter_value(right)))
    return filters


def _parse_filter_value(value: str) -> Any:
    stripped = value.strip()
    if (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        return stripped[1:-1]
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped


def _lance_filter_expression(
    filters: list[tuple[str, str, Any]],
    schema_names: list[str],
) -> str | None:
    clauses: list[str] = []
    schema = set(schema_names)
    for field, operator, expected in filters:
        if field in EPISODE_OVERLAY_FIELDS:
            return None
        if field not in schema or operator == "contains":
            return None
        clause = _lance_filter_clause(field, operator, expected)
        if clause is None:
            return None
        clauses.append(clause)
    return " AND ".join(clauses) if clauses else None


def _lance_filter_clause(field: str, operator: str, expected: Any) -> str | None:
    if operator not in {"==", "!=", ">", ">=", "<", "<="}:
        return None
    if expected is None:
        if operator == "==":
            return f"{field} IS NULL"
        if operator == "!=":
            return f"{field} IS NOT NULL"
        return None
    value = _lance_literal(expected)
    if value is None:
        return None
    sql_operator = "=" if operator == "==" else operator
    return f"{field} {sql_operator} {value}"


def _lance_literal(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _matches_simple_lance_filter(row: dict[str, Any], filter: str | None) -> bool:
    if not filter:
        return True
    match = re.match(r"^\s*([A-Za-z_][\w.]*)\s*=\s*(.+?)\s*$", filter)
    if match is None:
        return True
    field, raw_expected = match.groups()
    expected = _parse_filter_value(raw_expected)
    return row.get(field) == expected


def _matches_filter(
    episode: EpisodeListItem,
    field: str,
    operator: str,
    expected: Any,
) -> bool:
    actual = model_dump(episode).get(field)
    if operator == "contains":
        return str(expected).lower() in str(actual or "").lower()
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if actual is None:
        return False
    if operator in {">", ">=", "<", "<="}:
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if operator == ">":
            return actual_number > expected_number
        if operator == ">=":
            return actual_number >= expected_number
        if operator == "<":
            return actual_number < expected_number
        if operator == "<=":
            return actual_number <= expected_number
    return False


def _sort_episodes(
    episodes: list[EpisodeListItem],
    sort_by: str,
    sort_order: str,
) -> list[EpisodeListItem]:
    if sort_by not in EPISODE_SORT_FIELDS:
        raise ValueError(f"Unsupported episode sort field: {sort_by}")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be 'asc' or 'desc'")

    non_null = [episode for episode in episodes if model_dump(episode).get(sort_by) is not None]
    nulls = [episode for episode in episodes if model_dump(episode).get(sort_by) is None]
    non_null.sort(
        key=lambda episode: _sortable_episode_value(model_dump(episode).get(sort_by)),
        reverse=sort_order == "desc",
    )
    return non_null + nulls


def _sortable_episode_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return float(value)
    return str(value).lower()


@dataclass
class LanceBundle:
    base_uri: str
    tables: dict[str, Any]
    schemas: dict[str, list[str]]
    camera_info: dict[str, dict[str, Any]] | None = None
    published_manifest: dict[str, Any] | None = None


@dataclass
class VideoSource:
    size: int
    data: bytes | None = None
    path: Path | None = None
    reader: Any | None = None
    range_reader: Callable[[int, int, int], Iterator[bytes]] | None = None

    def read_all(self) -> bytes | None:
        try:
            if self.data is not None:
                return self.data
            if self.path is not None:
                return self.path.read_bytes()
            if self.reader is not None:
                if hasattr(self.reader, "seek"):
                    self.reader.seek(0)
                return self.reader.read()
            if self.range_reader is not None and self.size > 0:
                return b"".join(self.range_reader(0, self.size - 1, 1024 * 1024))
            return None
        finally:
            self.close()

    def iter_range(
        self,
        start: int,
        end: int,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        try:
            if self.data is not None:
                yield self.data[start : end + 1]
                return
            if self.path is not None:
                with self.path.open("rb") as handle:
                    yield from _iter_binary_range(handle, start, end, chunk_size)
                return
            if self.reader is not None:
                yield from _iter_binary_range(self.reader, start, end, chunk_size)
                return
            if self.range_reader is not None:
                yield from self.range_reader(start, end, chunk_size)
        finally:
            self.close()

    def close(self) -> None:
        if self.reader is not None and hasattr(self.reader, "close"):
            self.reader.close()


class LanceDependencyError(RuntimeError):
    pass


class LanceHealthService:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    def get_health(self, dataset_id: str, *, level: str = "shallow") -> DatasetHealth | None:
        if level not in {"shallow", "deep"}:
            raise ValueError("health level must be 'shallow' or 'deep'")
        record = self.owner._datasets.get(dataset_id)
        if record is None:
            return None
        summary = self.owner._summaries.get(dataset_id)
        bundle = self.owner._bundles.get(dataset_id)
        warnings: list[str] = []
        errors: list[str] = []
        tables: list[DatasetTableHealth] = []

        if record.status != "indexed" and record.status != "sample":
            errors.append(record.message or f"dataset status is {record.status}")
        if summary is None:
            errors.append("dataset summary is missing")

        if bundle is None:
            storage_model = "sample_or_metadata"
            if record.status == "indexed":
                warnings.append("dataset is metadata-backed; Lance raw tables are not open")
        else:
            storage_model = "lance"
            tables = self.table_health(bundle)
            for table in tables:
                for missing in table.missing_required_columns:
                    errors.append(f"{table.table}.lance missing required column: {missing}")
            if "episodes" not in bundle.tables:
                errors.append("episodes.lance is missing")

        episode_count = summary.episode_count if summary is not None else 0
        frame_count = summary.frame_count if summary is not None else 0
        camera_names = summary.camera_names if summary is not None else []
        if episode_count <= 0:
            errors.append("dataset has no episodes")
        if not camera_names:
            warnings.append("dataset has no detected cameras")

        if level == "deep" and bundle is not None and episode_count > 0:
            index_cache = self.owner._build_episode_row_offsets(bundle)
            if len(index_cache) != episode_count:
                warnings.append(
                    "episode_index values are duplicated or unavailable for some rows"
                )
            if index_cache:
                sorted_indices = sorted(index_cache)
                expected = list(range(sorted_indices[0], sorted_indices[0] + len(sorted_indices)))
                if sorted_indices != expected:
                    warnings.append("episode_index is non-contiguous; row-offset cache is active")

            sample_page = self.owner.list_episode_page(dataset_id, limit=min(10, episode_count), offset=0)
            missing_timeseries = [
                episode.episode_index
                for episode in sample_page.items
                if self.owner.get_episode_timeseries(dataset_id, episode.episode_index) is None
            ]
            if missing_timeseries:
                warnings.append(
                    "sample episodes without state/action timeseries: "
                    + ", ".join(str(index) for index in missing_timeseries[:10])
                )

            sample_video_missing: list[str] = []
            for episode in sample_page.items:
                for camera in episode.camera_names[:3]:
                    source = self.owner.get_video_source(dataset_id, episode.episode_index, camera)
                    if source is None or source.size <= 0:
                        sample_video_missing.append(f"ep{episode.episode_index}:{camera}")
            if sample_video_missing:
                warnings.append(
                    "sample camera streams without readable video source: "
                    + ", ".join(sample_video_missing[:10])
                )

        return DatasetHealth(
            dataset_id=dataset_id,
            ok=not errors,
            status=record.status,
            storage_model=storage_model,
            level=level,
            episode_count=episode_count,
            frame_count=frame_count,
            camera_count=len(camera_names),
            tables=tables,
            warnings=warnings,
            errors=errors,
        )

    def table_health(self, bundle: "LanceBundle") -> list[DatasetTableHealth]:
        required = {
            "episodes": ["episode_index", "camera_segments"],
            "frames": ["episode_index", "frame_index"],
            "videos": ["media_id", "video_blob"],
        }
        health: list[DatasetTableHealth] = []
        for table_name in TABLE_NAMES:
            dataset = bundle.tables.get(table_name)
            columns = bundle.schemas.get(table_name, [])
            missing_required = [
                column for column in required.get(table_name, []) if column not in columns
            ]
            table_warnings: list[str] = []
            if dataset is not None and table_name == "episodes":
                state_name = _bundle_state_column(bundle)
                action_name = _bundle_action_column(bundle)
                has_state = state_name in columns if state_name else False
                has_action = action_name in columns if action_name else False
                if not has_state:
                    table_warnings.append("registry state column missing from episodes table")
                if not has_action:
                    table_warnings.append("registry action column missing from episodes table")
            health.append(
                DatasetTableHealth(
                    table=table_name,
                    present=dataset is not None,
                    row_count=_count_rows(dataset) if dataset is not None else None,
                    columns=columns,
                    missing_required_columns=missing_required,
                    warnings=table_warnings,
                )
            )
        return health


class LanceMediaStore:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    def media_table(self, bundle: "LanceBundle") -> tuple[str, Any | None]:
        return "videos", bundle.tables.get("videos")

    def camera_names_from_media_table(self, bundle: "LanceBundle") -> list[str]:
        table_name, media = self.media_table(bundle)
        if media is None or _count_rows(media) == 0:
            return []
        schema = bundle.schemas.get(table_name, [])
        camera_name = _first_present_name(schema, VIDEO_CAMERA_COLUMNS)
        if camera_name is None:
            return []
        rows = self.owner._read_video_rows(
            media,
            schema,
            columns=[camera_name],
            limit=_count_rows(media),
        )
        return sorted(
            {
                _display_camera_name(row[camera_name])
                for row in rows
                if row.get(camera_name) not in (None, "")
            }
        )

    def video_blob_from_media_table(
        self,
        bundle: "LanceBundle",
        episode_row: dict[str, Any] | None,
        episode_index: int,
        camera: str,
    ) -> bytes | None:
        source = self.video_source_from_media_table(bundle, episode_row, episode_index, camera)
        if source is None:
            return None
        return source.read_all()

    def video_source_from_media_table(
        self,
        bundle: "LanceBundle",
        episode_row: dict[str, Any] | None,
        episode_index: int,
        camera: str,
    ) -> VideoSource | None:
        table_name, media = self.media_table(bundle)
        if media is None or _count_rows(media) == 0:
            return None
        schema = bundle.schemas.get(table_name, [])
        media_id_name = "media_id" if "media_id" in schema else None
        blob_name = _first_present_name(schema, VIDEO_BLOB_COLUMNS)
        if media_id_name is None or blob_name is None:
            return None

        segment_media_id = _camera_segment_media_id(episode_row, camera)
        if not segment_media_id:
            return None

        rows = self.owner._read_video_rows(
            media,
            schema,
            columns=[media_id_name],
            filter=f"media_id = {_lance_literal(segment_media_id)}",
            limit=1,
            include_offsets=True,
        )
        for row in rows:
            if str(row.get(media_id_name)) != segment_media_id:
                continue
            source = self.owner._get_video_blob_source_by_offset(
                media,
                blob_name,
                _int_or_none(row.get("__row_offset")),
            )
            if source is not None:
                return source
        return None


class LanceDatasetStore:
    """Thin service boundary for Lance-backed dataset access.

    Lance itself is an optional dependency. When it is installed this service
    indexes RLLAB Lance v2 `data/episodes.lance`, `data/frames.lance`, and
    `data/videos.lance` tables from a dataset root URI. v1/flat Lance bundles
    must be re-converted before opening. A small sample fixture stays available
    for local UI development.
    """

    def __init__(
        self,
        label_storage_root: Path = EPISODE_LABEL_STORAGE_ROOT,
        dataset_registry_path: Path = DATASET_REGISTRY_PATH,
        *,
        persist_episode_labels: bool = False,
        persist_dataset_registry: bool = False,
        mirror_episode_labels_lance: bool = True,
    ) -> None:
        self.label_storage_root = label_storage_root
        self.dataset_registry_path = dataset_registry_path
        self.persist_episode_labels = persist_episode_labels
        self.persist_dataset_registry = persist_dataset_registry
        self.mirror_episode_labels_lance = mirror_episode_labels_lance
        self._datasets: dict[str, DatasetRecord] = {}
        self._summaries: dict[str, DatasetSummary] = {}
        self._episodes: dict[str, list[EpisodeDetail]] = {}
        self._bundles: dict[str, LanceBundle] = {}
        self._episode_row_offsets: dict[str, dict[int, int]] = {}
        self._episode_label_overrides: dict[str, dict[int, dict[str, Any]]] = {}
        self._episode_label_history: list[EpisodeLabelHistoryRecord] = []
        self.health = LanceHealthService(self)
        self.media = LanceMediaStore(self)
        self.filter_engine = LanceFilterEngine(
            self,
            parse_filter_query=_parse_filter_query,
            lance_filter_expression=_lance_filter_expression,
            matches_filter=_matches_filter,
            metadata_columns=lambda schema: _metadata_columns(schema, include_arrays=False),
            count_rows=_count_rows,
            rows_from_table=_rows_from_table,
        )
        if self.persist_episode_labels:
            self._load_episode_label_overrides()
            self._load_episode_label_history()
        self._seed_demo_dataset()
        if self.persist_dataset_registry:
            self._load_dataset_registry()
        default_dataset_uri = os.environ.get("ROBOT_DATA_STUDIO_DEFAULT_DATASET_URI")
        if default_dataset_uri:
            self._open_dataset(
                DatasetOpenRequest(
                    uri=default_dataset_uri,
                    name=os.environ.get("ROBOT_DATA_STUDIO_DEFAULT_DATASET_NAME"),
                ),
                persist_registry=False,
            )

    def _seed_demo_dataset(self) -> None:
        dataset_id = "sample-xvla-soft-fold"
        record = DatasetRecord(
            dataset_id=dataset_id,
            name="sample-xvla-soft-fold",
            uri="sample://xvla-soft-fold",
            status="sample",
            message="Built-in sample dataset for UI development.",
        )
        episodes = [
            EpisodeDetail(
                dataset_id=dataset_id,
                episode_index=idx,
                task_index=3,
                length=180 + idx * 12,
                success_label=idx % 2 == 0,
                quality_score=0.72 + idx * 0.05,
                review_status="pending" if idx == 1 else "accepted",
                caption="Soft cloth folding trajectory",
                has_vlm_label=idx != 0,
                has_human_label=idx == 2,
                split="train",
                fps=20.0,
                camera_names=["cam_high", "cam_left_wrist", "cam_right_wrist"],
                duration_seconds=(180 + idx * 12) / 20.0,
                language_instruction="Fold the soft cloth neatly.",
            )
            for idx in range(3)
        ]
        self._datasets[dataset_id] = record
        self._episodes[dataset_id] = episodes
        self._summaries[dataset_id] = DatasetSummary(
            dataset_id=dataset_id,
            name=record.name,
            uri=record.uri,
            status=record.status,
            episode_count=len(episodes),
            frame_count=sum(episode.length or 0 for episode in episodes),
            fps=20.0,
            camera_names=["cam_high", "cam_left_wrist", "cam_right_wrist"],
            reviewed_count=2,
            accepted_count=2,
            rejected_count=0,
            message=record.message,
        )

    def list_datasets(self) -> list[DatasetRecord]:
        return list(self._datasets.values())

    def open_dataset(self, payload: DatasetOpenRequest) -> DatasetRecord:
        return self._open_dataset(payload, persist_registry=True)

    def reload_dataset(self, dataset_id: str) -> DatasetRecord | None:
        record = self._datasets.get(dataset_id)
        if record is None:
            return None
        payload = DatasetOpenRequest(uri=record.uri, name=record.name)
        self._drop_dataset(dataset_id)
        return self._open_dataset(payload, persist_registry=True)

    def close_dataset(self, dataset_id: str) -> DatasetRecord | None:
        record = self._datasets.get(dataset_id)
        if record is None:
            return None
        self._drop_dataset(dataset_id)
        self._persist_dataset_registry()
        return record

    def _open_dataset(
        self,
        payload: DatasetOpenRequest,
        *,
        persist_registry: bool,
    ) -> DatasetRecord:
        name = payload.name or self._name_from_uri(payload.uri)
        dataset_id = _slug(name)
        if payload.uri.startswith("sample://") and dataset_id == "sample-xvla-soft-fold":
            self._seed_demo_dataset()
            if persist_registry:
                self._persist_dataset_registry()
            return self._datasets[dataset_id]
        lerobot_episodes = self._try_open_lerobot_snapshot(payload.uri, dataset_id)
        if lerobot_episodes is not None:
            record = DatasetRecord(
                dataset_id=dataset_id,
                name=name,
                uri=payload.uri,
                status="indexed",
                message="LeRobot metadata snapshot indexed.",
            )
            self._datasets[dataset_id] = record
            self._bundles.pop(dataset_id, None)
            self._episode_row_offsets.pop(dataset_id, None)
            self._episodes[dataset_id] = lerobot_episodes
            self._summaries[dataset_id] = self._summary_from_episodes(
                record,
                lerobot_episodes,
                camera_info=_load_lerobot_camera_info(payload.uri),
            )
            if persist_registry:
                self._persist_dataset_registry()
            return record

        try:
            bundle = self._open_lance_bundle(payload.uri)
        except LanceDependencyError as exc:
            record = DatasetRecord(
                dataset_id=dataset_id,
                name=name,
                uri=payload.uri,
                status="dependency_missing",
                message=str(exc),
            )
            self._datasets[dataset_id] = record
            self._bundles.pop(dataset_id, None)
            self._episode_row_offsets.pop(dataset_id, None)
            self._episodes[dataset_id] = []
            self._summaries[dataset_id] = self._empty_summary(record)
            if persist_registry:
                self._persist_dataset_registry()
            return record
        except Exception as exc:
            record = DatasetRecord(
                dataset_id=dataset_id,
                name=name,
                uri=payload.uri,
                status="open_failed",
                message=str(exc),
            )
            self._datasets[dataset_id] = record
            self._bundles.pop(dataset_id, None)
            self._episode_row_offsets.pop(dataset_id, None)
            self._episodes[dataset_id] = []
            self._summaries[dataset_id] = self._empty_summary(record)
            if persist_registry:
                self._persist_dataset_registry()
            return record

        # Published bundles carry the canonical dataset_id inside manifest.json;
        # adopt it so annotation overlays (keyed by dataset_id) follow the
        # bundle across HF clones / local copies regardless of the URI slug.
        if payload.name is None and isinstance(bundle.published_manifest, dict):
            manifest_dataset_id = bundle.published_manifest.get("dataset_id")
            if isinstance(manifest_dataset_id, str) and manifest_dataset_id.strip():
                canonical = _slug(manifest_dataset_id.strip())
                if canonical and canonical != dataset_id:
                    dataset_id = canonical
                    name = manifest_dataset_id.strip()

        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            uri=payload.uri,
            status="indexed",
            message=(
                "Published v2 Lance data/ layout indexed. Annotation edits are "
                "stored as a local overlay; source tables are not modified."
            ),
        )
        self._datasets[dataset_id] = record
        self._bundles[dataset_id] = bundle
        self._episode_row_offsets.pop(dataset_id, None)
        self._episodes.pop(dataset_id, None)
        self._summaries[dataset_id] = self._build_summary(record, bundle)
        if persist_registry:
            self._persist_dataset_registry()
        return record

    def get_summary(self, dataset_id: str) -> DatasetSummary | None:
        return self._summaries.get(dataset_id)

    def get_schema(self, dataset_id: str) -> dict[str, list[str]] | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return bundle.schemas
        if dataset_id in self._datasets:
            return {}
        return None

    def get_health(self, dataset_id: str, *, level: str = "shallow") -> DatasetHealth | None:
        return self.health.get_health(dataset_id, level=level)

    def list_episodes(
        self,
        dataset_id: str,
        limit: int,
        offset: int,
        *,
        sort_by: str = "episode_index",
        sort_order: str = "asc",
        filter_query: str | None = None,
    ) -> list[EpisodeListItem]:
        if sort_by != "episode_index" or sort_order != "asc" or filter_query:
            return self.list_episode_page(
                dataset_id,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order,
                filter_query=filter_query,
            ).items
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            try:
                return self._list_lance_episodes(dataset_id, bundle, limit=limit, offset=offset)
            except (OSError, ValueError) as exc:
                self._invalidate_dead_bundle(dataset_id, exc)
                return []
        episodes = self._episodes.get(dataset_id, [])
        return [
            EpisodeListItem(**self._apply_episode_overrides(dataset_id, model_dump(episode)))
            for episode in episodes[offset : offset + limit]
        ]

    def _invalidate_dead_bundle(self, dataset_id: str, exc: BaseException) -> None:
        # Drop a bundle whose underlying Lance files vanished mid-session
        # (e.g. user deleted the session_* directory after the API loaded it).
        # Mark the record as open_failed so the UI can show why it went empty
        # instead of bubbling a Lance "Not found" up as a 500.
        record = self._datasets.get(dataset_id)
        if record is not None:
            self._datasets[dataset_id] = DatasetRecord(
                dataset_id=record.dataset_id,
                name=record.name,
                uri=record.uri,
                status="open_failed",
                message=f"Underlying Lance dataset is no longer accessible: {exc}",
            )
            self._summaries[dataset_id] = self._empty_summary(self._datasets[dataset_id])
        self._bundles.pop(dataset_id, None)
        self._episode_row_offsets.pop(dataset_id, None)
        self._episodes[dataset_id] = []
        print(
            f"[lance_store] invalidated bundle for {dataset_id}: {exc}",
            file=sys.stderr,
        )

    def list_episode_page(
        self,
        dataset_id: str,
        limit: int,
        offset: int,
        *,
        sort_by: str = "episode_index",
        sort_order: str = "asc",
        filter_query: str | None = None,
    ) -> EpisodeListPage:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must be greater than or equal to zero")
        if sort_by not in EPISODE_SORT_FIELDS:
            raise ValueError(f"Unsupported episode sort field: {sort_by}")
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order must be 'asc' or 'desc'")

        needs_materialized_page = filter_query or sort_by != "episode_index" or sort_order != "asc"
        if needs_materialized_page:
            if filter_query:
                episodes = self.filter_episode_items(dataset_id, filter_query)
            else:
                episodes = self._all_episode_items(dataset_id)
            episodes = _sort_episodes(episodes, sort_by=sort_by, sort_order=sort_order)
            total = len(episodes)
            items = episodes[offset : offset + limit]
        else:
            total = self._episode_count(dataset_id)
            items = self.list_episodes(dataset_id, limit=limit, offset=offset)

        next_offset = offset + limit if offset + limit < total else None
        previous_offset = max(offset - limit, 0) if offset > 0 and total > 0 else None
        return EpisodeListPage(
            dataset_id=dataset_id,
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            next_offset=next_offset,
            previous_offset=previous_offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_query=filter_query,
        )

    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return self._get_lance_episode(dataset_id, bundle, episode_index)
        for episode in self._episodes.get(dataset_id, []):
            if episode.episode_index == episode_index:
                return EpisodeDetail(**self._apply_episode_overrides(dataset_id, model_dump(episode)))
        return None

    def update_episode_labels(
        self,
        dataset_id: str,
        episode_index: int,
        payload: EpisodeLabelUpdate,
    ) -> EpisodeDetail | None:
        existing = self.get_episode(dataset_id, episode_index)
        if existing is None:
            return None

        updates = model_dump(payload, exclude_unset=True)
        actor = str(updates.pop("updated_by", None) or "local")
        if "review_status" in updates and updates["review_status"] is not None:
            updates["review_status"] = getattr(updates["review_status"], "value", updates["review_status"])
        elif "review_status" in updates:
            updates.pop("review_status")
        if not updates:
            return existing

        before_snapshot = {key: getattr(existing, key, None) for key in updates}
        dataset_overrides = self._episode_label_overrides.setdefault(dataset_id, {})
        current = dataset_overrides.get(episode_index, {})
        dataset_overrides[episode_index] = {
            **current,
            **updates,
            "has_human_label": True,
        }
        self._persist_episode_label_overrides(dataset_id)
        self._refresh_episode_summary(dataset_id)
        updated = self.get_episode(dataset_id, episode_index)
        after_snapshot = (
            {key: getattr(updated, key, None) for key in updates}
            if updated is not None
            else None
        )
        self._append_episode_label_history(
            dataset_id=dataset_id,
            episode_index=episode_index,
            action="update",
            actor=actor,
            before=before_snapshot,
            after=after_snapshot,
        )
        return updated

    def list_episode_label_history(
        self,
        dataset_id: str,
        *,
        episode_index: int | None = None,
    ) -> list[EpisodeLabelHistoryRecord]:
        return [
            event
            for event in self._episode_label_history
            if event.dataset_id == dataset_id
            and (episode_index is None or event.episode_index == episode_index)
        ]

    def get_state_action_summary(
        self,
        dataset_id: str,
        episode_index: int,
    ) -> StateActionSummary | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return self._get_lance_state_action_summary(dataset_id, bundle, episode_index)
        episode = self.get_episode(dataset_id, episode_index)
        if episode is None:
            return None
        record = self._datasets.get(dataset_id)
        state_dim, action_dim = _state_action_dims_from_info(
            record.uri if record is not None else None
        )
        return StateActionSummary(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_count=episode.length or 0,
            state_dim=state_dim if state_dim is not None else 14,
            action_dim=action_dim if action_dim is not None else 14,
            state_norm_min=0.0 if state_dim is None else None,
            state_norm_max=1.0 if state_dim is None else None,
            action_norm_min=0.0 if action_dim is None else None,
            action_norm_max=1.0 if action_dim is None else None,
        )

    def get_video_blob(
        self,
        dataset_id: str,
        episode_index: int,
        camera: str,
    ) -> bytes | None:
        source = self.get_video_source(dataset_id, episode_index, camera)
        if source is None:
            return None
        return source.read_all()

    def get_video_source(
        self,
        dataset_id: str,
        episode_index: int,
        camera: str,
    ) -> VideoSource | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is None:
            return None
        schema = bundle.schemas["episodes"]
        episode_row = self._read_lance_episode_row_by_index(
            dataset_id,
            bundle,
            episode_index,
            columns=_metadata_columns(schema, include_arrays=False),
        )
        return self._get_video_source_from_videos_table(bundle, episode_row, episode_index, camera)

    def get_episode_timeseries(
        self,
        dataset_id: str,
        episode_index: int,
    ) -> dict[str, Any] | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return self._get_lance_episode_timeseries(dataset_id, bundle, episode_index)

        episode = self.get_episode(dataset_id, episode_index)
        if episode is None:
            return None
        frame_count = episode.length or 0
        fps = episode.fps or 20.0
        timestamps = [frame / fps for frame in range(frame_count)]
        return {
            "dataset_id": dataset_id,
            "episode_index": episode_index,
            "timestamps": timestamps,
            "states": [[frame / max(1, frame_count), 0.0] for frame in range(frame_count)],
            "actions": [[0.0, frame / max(1, frame_count)] for frame in range(frame_count)],
        }

    def get_episode_norm_series(
        self,
        dataset_id: str,
        episode_index: int,
    ) -> EpisodeTimeseries | None:
        timeseries = self.get_episode_timeseries(dataset_id, episode_index)
        if timeseries is None:
            return None

        states = _sequence(timeseries.get("states"))
        actions = _sequence(timeseries.get("actions"))
        timestamps = _sequence(timeseries.get("timestamps"))
        frame_count = max(len(states), len(actions), len(timestamps))
        if frame_count <= 0:
            episode = self.get_episode(dataset_id, episode_index)
            frame_count = (episode.length or 0) if episode is not None else 0

        episode = self.get_episode(dataset_id, episode_index)
        fps = episode.fps if episode is not None else None

        record = self._datasets.get(dataset_id)
        bundle_uri = record.uri if record is not None else None
        state_names, action_names = _joint_names_from_manifest(bundle_uri)
        if state_names is None and action_names is None:
            state_names, action_names = _joint_names_from_info(bundle_uri)

        if frame_count == 0:
            return EpisodeTimeseries(
                dataset_id=dataset_id,
                episode_index=episode_index,
                frame_count=0,
                fps=fps,
                sample_count=0,
                sample_indices=[],
                timestamps=None,
                state_norms=[],
                action_norms=[],
                state_dim=_vector_dim(states),
                action_dim=_vector_dim(actions),
                state_names=state_names,
                action_names=action_names,
            )

        stride = max(1, math.ceil(frame_count / NORM_SERIES_MAX_POINTS))
        sample_indices = list(range(0, frame_count, stride))
        if sample_indices[-1] != frame_count - 1:
            sample_indices.append(frame_count - 1)

        state_norms = [_norm_at(states, index) for index in sample_indices]
        action_norms = [_norm_at(actions, index) for index in sample_indices]
        state_values = [_vector_at(states, index) for index in sample_indices]
        action_values = [_vector_at(actions, index) for index in sample_indices]
        sample_timestamps: list[float | None] | None = None
        if timestamps:
            sample_timestamps = [_timestamp_at(timestamps, index) for index in sample_indices]

        return EpisodeTimeseries(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_count=frame_count,
            fps=fps,
            sample_count=len(sample_indices),
            sample_indices=sample_indices,
            timestamps=sample_timestamps,
            state_norms=state_norms,
            action_norms=action_norms,
            state_values=state_values,
            action_values=action_values,
            state_dim=_vector_dim(states),
            action_dim=_vector_dim(actions),
            state_names=state_names,
            action_names=action_names,
        )

    def list_frames(
        self,
        dataset_id: str,
        episode_index: int,
        *,
        start_frame: int = 0,
        end_frame: int | None = None,
        limit: int = 100,
    ) -> list[FrameRecord] | None:
        episode = self.get_episode(dataset_id, episode_index)
        if episode is None:
            return None

        bundle = self._bundles.get(dataset_id)
        if bundle is not None and bundle.tables.get("frames") is not None:
            frames = self._list_lance_frames(
                dataset_id,
                bundle,
                episode_index,
                task_index=episode.task_index,
                start_frame=start_frame,
                end_frame=end_frame,
                limit=limit,
            )
            if frames is not None:
                return frames

        return self._list_timeseries_frames(
            dataset_id,
            episode,
            start_frame=start_frame,
            end_frame=end_frame,
            limit=limit,
        )

    def filter_search(self, payload: FilterSearchRequest) -> list[SearchResult]:
        matched = self.filter_episode_items(
            payload.dataset_id,
            payload.query,
            limit=payload.limit,
        )
        return [
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=None,
                match_type="episode_filter",
                label=payload.query,
            )
            for episode in matched
        ]

    def filter_episode_items(
        self,
        dataset_id: str,
        query: str,
        *,
        limit: int | None = None,
    ) -> list[EpisodeListItem]:
        return self.filter_engine.filter_episode_items(dataset_id, query, limit=limit)

    def _filter_lance_episode_items(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        filters: list[tuple[str, str, Any]],
        *,
        limit: int | None,
    ) -> list[EpisodeListItem] | None:
        return self.filter_engine.filter_lance_episode_items(
            dataset_id,
            bundle,
            filters,
            limit=limit,
        )

    def _name_from_uri(self, uri: str) -> str:
        if uri.startswith("hf://datasets/"):
            parts = uri.removeprefix("hf://datasets/").strip("/").split("/")
            if len(parts) >= 2:
                return f"{parts[0]}-{parts[1]}"
        return Path(uri.rstrip("/")).name or _slug(uri)

    def _empty_summary(self, record: DatasetRecord) -> DatasetSummary:
        return DatasetSummary(
            dataset_id=record.dataset_id,
            name=record.name,
            uri=record.uri,
            status=record.status,
            episode_count=0,
            frame_count=0,
            fps=None,
            camera_names=[],
            message=record.message,
        )

    def _summary_from_episodes(
        self,
        record: DatasetRecord,
        episodes: list[EpisodeDetail],
        *,
        camera_info: dict[str, dict[str, Any]] | None = None,
    ) -> DatasetSummary:
        fps_values = {episode.fps for episode in episodes if episode.fps is not None}
        return DatasetSummary(
            dataset_id=record.dataset_id,
            name=record.name,
            uri=record.uri,
            status=record.status,
            episode_count=len(episodes),
            frame_count=sum(episode.length or 0 for episode in episodes),
            fps=fps_values.pop() if len(fps_values) == 1 else None,
            camera_names=sorted({camera for episode in episodes for camera in episode.camera_names}),
            camera_info=camera_info,
            reviewed_count=sum(1 for episode in episodes if episode.review_status != "pending"),
            accepted_count=sum(1 for episode in episodes if episode.review_status == "accepted"),
            rejected_count=sum(1 for episode in episodes if episode.review_status == "rejected"),
            message=record.message,
        )

    def _try_open_lerobot_snapshot(
        self,
        uri: str,
        dataset_id: str,
    ) -> list[EpisodeDetail] | None:
        path = _local_path_from_uri(uri)
        if path is None or not (path / "meta" / "info.json").exists():
            return None
        # Lance tables take precedence: a converted bundle copies the source
        # info.json for camera_info discovery, which would otherwise misroute
        # this dataset to the metadata-only LeRobot snapshot path.
        if (path / "episodes.lance").exists() or (path / "data" / "episodes.lance").exists():
            return None
        return read_lerobot_snapshot_episodes(path, dataset_id=dataset_id)

    def _open_lance_bundle(self, uri: str) -> LanceBundle:
        try:
            lance = import_module("lance")
        except ImportError as exc:
            raise LanceDependencyError(
                "Python package 'lance' is not installed. Install the optional Lance dependencies "
                "before opening real .lance datasets."
            ) from exc

        published_manifest = _read_published_manifest(uri)
        if published_manifest is None:
            manifest = _read_manifest(uri)
            if isinstance(manifest, dict):
                fmt = manifest.get("format")
                version = manifest.get("schema_version")
                raise ValueError(
                    "Unsupported Lance bundle manifest "
                    f"format={fmt!r}, schema_version={version!r}; "
                    f"robo_dataview expects {PUBLISHED_LANCE_FORMAT} v2.x"
                )
            raise ValueError(
                "RLLAB Lance v2 manifest.json is required; reconvert this dataset "
                "with the v2 lerobot2lance converter."
            )

        tables: dict[str, Any] = {}
        for table_name in ("episodes", "frames", "videos"):
            table_path = _manifest_table_path(published_manifest, table_name)
            if table_path is None:
                if table_name == "episodes":
                    raise FileNotFoundError("v2 manifest is missing tables.episodes")
                continue
            try:
                tables[table_name] = lance.dataset(_join_uri(uri, table_path))
            except Exception:
                if table_name == "episodes":
                    raise
        return LanceBundle(
            base_uri=uri,
            tables=tables,
            schemas={name: _schema_names(dataset) for name, dataset in tables.items()},
            camera_info=_load_lerobot_camera_info(uri),
            published_manifest=published_manifest,
        )

    def _table_health(self, bundle: LanceBundle) -> list[DatasetTableHealth]:
        return self.health.table_health(bundle)

    def _build_summary(self, record: DatasetRecord, bundle: LanceBundle) -> DatasetSummary:
        episodes = bundle.tables["episodes"]
        episode_count = _count_rows(episodes)
        frames = bundle.tables.get("frames")
        frame_count = _count_rows(frames) if frames is not None else 0
        episode_schema = bundle.schemas["episodes"]
        camera_names = self._camera_names_for_bundle(bundle)
        sample = self._get_lance_episode(record.dataset_id, bundle, 0)
        if frame_count == 0 and sample is not None and sample.length is not None:
            frame_count = sum(
                episode.length or 0
                for episode in self._all_episode_items(record.dataset_id)
            )

        manifest = bundle.published_manifest if isinstance(bundle.published_manifest, dict) else None
        primary_training_table: str | None = None
        source_session_count: int | None = None
        dataset_id_source = "uri"
        action_semantics = _action_semantics_from_manifest(manifest)
        if manifest is not None:
            primary = manifest.get("primary_training_table")
            if isinstance(primary, str) and primary.strip():
                primary_training_table = primary.strip()
            count = manifest.get("source_session_count")
            if isinstance(count, int):
                source_session_count = count
            manifest_id = manifest.get("dataset_id")
            if (
                isinstance(manifest_id, str)
                and manifest_id.strip()
                and _slug(manifest_id.strip()) == record.dataset_id
            ):
                dataset_id_source = "manifest"

        return DatasetSummary(
            dataset_id=record.dataset_id,
            name=record.name,
            uri=record.uri,
            status=record.status,
            episode_count=episode_count,
            frame_count=frame_count,
            fps=sample.fps if sample is not None else None,
            camera_names=camera_names,
            camera_info=bundle.camera_info,
            reviewed_count=0,
            accepted_count=0,
            rejected_count=0,
            storage_layout="published_hf",
            primary_training_table=primary_training_table,
            annotation_storage="local_overlay",
            source_session_count=source_session_count,
            dataset_id_source=dataset_id_source,
            action_semantics=action_semantics,
            message=record.message,
        )

    def _list_lance_episodes(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        limit: int,
        offset: int,
    ) -> list[EpisodeListItem]:
        dataset = bundle.tables["episodes"]
        columns = _metadata_columns(bundle.schemas["episodes"], include_arrays=False)
        rows = _read_rows(dataset, columns=columns, limit=limit, offset=offset)
        camera_names = self._camera_names_for_bundle(bundle)
        items: list[EpisodeListItem] = []
        for row in rows:
            payload = self._apply_episode_overrides(
                dataset_id,
                self._episode_payload(dataset_id, row, bundle.schemas["episodes"]),
            )
            payload["camera_names"] = camera_names
            items.append(EpisodeListItem(**payload))
        return items

    def _read_lance_episode_row_by_index(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
        columns: list[str] | None = None,
    ) -> dict[str, Any] | None:
        dataset = bundle.tables["episodes"]
        if hasattr(dataset, "scanner"):
            try:
                scanner = dataset.scanner(
                    columns=columns,
                    filter=f"episode_index = {episode_index}",
                    limit=1,
                )
                rows = _rows_from_table(scanner.to_table())
                if rows:
                    return rows[0]
            except Exception:
                pass

        row_offset = self._episode_row_offset(dataset_id, bundle, episode_index)
        if row_offset is None:
            return None
        try:
            rows = _read_rows(dataset, columns=columns, limit=1, offset=row_offset)
        except Exception:
            return None
        if rows and int(rows[0].get("episode_index", episode_index)) == episode_index:
            return rows[0]
        return None

    def _episode_row_offset(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> int | None:
        cache = self._episode_row_offsets.get(dataset_id)
        if cache is None:
            cache = self._build_episode_row_offsets(bundle)
            self._episode_row_offsets[dataset_id] = cache
        return cache.get(int(episode_index))

    @staticmethod
    def _build_episode_row_offsets(bundle: LanceBundle) -> dict[int, int]:
        dataset = bundle.tables["episodes"]
        try:
            rows = _read_rows(
                dataset,
                columns=["episode_index"],
                limit=_count_rows(dataset),
                offset=0,
            )
        except Exception:
            return {}
        offsets: dict[int, int] = {}
        for offset, row in enumerate(rows):
            episode_index = _int_or_none(row.get("episode_index"))
            if episode_index is not None:
                offsets[episode_index] = offset
        return offsets

    def _get_lance_episode(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> EpisodeDetail | None:
        columns = _metadata_columns(bundle.schemas["episodes"], include_arrays=False)
        row = self._read_lance_episode_row_by_index(
            dataset_id,
            bundle,
            episode_index,
            columns=columns,
        )
        if row is None:
            return None
        payload = self._apply_episode_overrides(
            dataset_id,
            self._episode_payload(dataset_id, row, bundle.schemas["episodes"]),
        )
        payload["camera_names"] = self._camera_names_for_bundle(bundle)
        return EpisodeDetail(**payload)

    def _get_lance_state_action_summary(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> StateActionSummary | None:
        schema = bundle.schemas["episodes"]
        state_name = _bundle_state_column(bundle)
        action_name = _bundle_action_column(bundle)

        metadata_row = self._read_lance_episode_row_by_index(
            dataset_id,
            bundle,
            episode_index,
            columns=_metadata_columns(schema, include_arrays=False),
        )
        if metadata_row is None:
            return None

        frame_count = _episode_length(metadata_row) or 0
        state_dim: int | None = None
        action_dim: int | None = None
        state_min: float | None = None
        state_max: float | None = None
        action_min: float | None = None
        action_max: float | None = None

        array_columns = [
            column for column in (state_name, action_name, "episode_index") if column
        ]
        if state_name or action_name:
            array_row = self._read_lance_episode_row_by_index(
                dataset_id,
                bundle,
                episode_index,
                columns=array_columns,
            )
            if array_row is not None:
                states = array_row.get(state_name) if state_name else None
                actions = array_row.get(action_name) if action_name else None
                state_min, state_max = _norm_bounds(states)
                action_min, action_max = _norm_bounds(actions)
                state_dim = _vector_dim(states)
                action_dim = _vector_dim(actions)

        if state_dim is None and action_dim is None:
            sampled_state_dim, sampled_action_dim = self._sample_state_action_dims_from_frames(bundle)
            state_dim = state_dim or sampled_state_dim
            action_dim = action_dim or sampled_action_dim

        return StateActionSummary(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_count=frame_count,
            state_dim=state_dim,
            action_dim=action_dim,
            state_norm_min=state_min,
            state_norm_max=state_max,
            action_norm_min=action_min,
            action_norm_max=action_max,
        )

    def _sample_state_action_dims_from_frames(
        self, bundle: LanceBundle
    ) -> tuple[int | None, int | None]:
        frames = bundle.tables.get("frames")
        if frames is None or _count_rows(frames) == 0:
            return None, None
        state_name = _bundle_frame_state_column(bundle)
        action_name = _bundle_frame_action_column(bundle)
        columns = [column for column in (state_name, action_name) if column]
        if not columns:
            return None, None
        try:
            rows = _read_rows(frames, columns=columns, limit=1, offset=0)
        except Exception:
            return None, None
        if not rows:
            return None, None
        row = rows[0]
        # In frames.lance each row's state/action column is the per-frame
        # vector directly (1D), not the episode-level (T, D) array, so use
        # _safe_len rather than _vector_dim.
        state_dim = _safe_len(row.get(state_name)) if state_name else None
        action_dim = _safe_len(row.get(action_name)) if action_name else None
        return state_dim, action_dim

    def _get_lance_episode_timeseries(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> dict[str, Any] | None:
        schema = bundle.schemas["episodes"]
        state_name = _bundle_state_column(bundle)
        action_name = _bundle_action_column(bundle)
        timestamp_name = _first_present_name(schema, TIMESTAMP_COLUMNS)
        columns = [
            column
            for column in (state_name, action_name, timestamp_name, "episode_index")
            if column is not None
        ]
        row = self._read_lance_episode_row_by_index(
            dataset_id,
            bundle,
            episode_index,
            columns=columns,
        )
        if row is None:
            return None
        return {
            "dataset_id": dataset_id,
            "episode_index": episode_index,
            "timestamps": row.get(timestamp_name) if timestamp_name else None,
            "states": row.get(state_name) if state_name else None,
            "actions": row.get(action_name) if action_name else None,
        }

    def _list_lance_frames(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
        *,
        task_index: int | None,
        start_frame: int,
        end_frame: int | None,
        limit: int,
    ) -> list[FrameRecord] | None:
        dataset = bundle.tables.get("frames")
        if dataset is None or _count_rows(dataset) == 0:
            return None

        schema = bundle.schemas.get("frames", [])
        frame_name = _first_present_name(schema, FRAME_INDEX_COLUMNS)
        timestamp_name = _first_present_name(schema, FRAME_TIMESTAMP_COLUMNS)
        state_name = _bundle_frame_state_column(bundle)
        action_name = _bundle_frame_action_column(bundle)
        columns = _unique_columns(
            schema,
            [
                "episode_index",
                frame_name,
                timestamp_name,
                "task_index",
                state_name,
                action_name,
                "state_norm",
                "action_norm",
                "is_bad_frame",
            ],
        )

        try:
            scanner = dataset.scanner(
                columns=columns or None,
                filter=f"episode_index = {episode_index}",
            )
            rows = _rows_from_table(scanner.to_table())
        except Exception:
            rows = [
                row
                for row in _read_rows(
                    dataset,
                    columns=columns or None,
                    limit=_count_rows(dataset),
                    offset=0,
                )
                if _int_or_none(row.get("episode_index")) == episode_index
            ]
        if not rows:
            return None

        records: list[FrameRecord] = []
        for fallback_index, row in enumerate(rows):
            row_episode_index = _int_or_none(row.get("episode_index"))
            if row_episode_index is not None and row_episode_index != episode_index:
                continue
            frame_index = _int_or_none(row.get(frame_name)) if frame_name else None
            if frame_index is None:
                frame_index = fallback_index
            if frame_index < start_frame:
                continue
            if end_frame is not None and frame_index > end_frame:
                continue

            state_vector = _numeric_vector(row.get(state_name)) if state_name else []
            action_vector = _numeric_vector(row.get(action_name)) if action_name else []
            state_norm = _number_or_none(row.get("state_norm"))
            action_norm = _number_or_none(row.get("action_norm"))
            records.append(
                FrameRecord(
                    dataset_id=dataset_id,
                    episode_index=episode_index,
                    frame_index=frame_index,
                    timestamp=_number_or_none(row.get(timestamp_name)) if timestamp_name else None,
                    task_index=_int_or_none(row.get("task_index")) or task_index,
                    observation_state=state_vector or None,
                    action=action_vector or None,
                    state_norm=state_norm if state_norm is not None else _norm_from_vector(state_vector),
                    action_norm=action_norm if action_norm is not None else _norm_from_vector(action_vector),
                    is_bad_frame=bool(row.get("is_bad_frame", False)),
                )
            )

        records.sort(key=lambda frame: frame.frame_index)
        return records[:limit]

    def _list_timeseries_frames(
        self,
        dataset_id: str,
        episode: EpisodeDetail,
        *,
        start_frame: int,
        end_frame: int | None,
        limit: int,
    ) -> list[FrameRecord]:
        timeseries = self.get_episode_timeseries(dataset_id, episode.episode_index)
        if timeseries is None:
            return []
        states = _sequence(timeseries.get("states"))
        actions = _sequence(timeseries.get("actions"))
        timestamps = _sequence(timeseries.get("timestamps"))
        frame_count = max(len(states), len(actions), len(timestamps), episode.length or 0)
        if frame_count <= 0:
            return []

        last_frame = min(frame_count - 1, end_frame if end_frame is not None else frame_count - 1)
        if start_frame > last_frame:
            return []

        fps = episode.fps or 20.0
        records: list[FrameRecord] = []
        for frame_index in range(start_frame, last_frame + 1):
            if len(records) >= limit:
                break
            state_vector = _numeric_vector(states[frame_index]) if frame_index < len(states) else []
            action_vector = _numeric_vector(actions[frame_index]) if frame_index < len(actions) else []
            timestamp = _timestamp_at(timestamps, frame_index)
            records.append(
                FrameRecord(
                    dataset_id=dataset_id,
                    episode_index=episode.episode_index,
                    frame_index=frame_index,
                    timestamp=timestamp if timestamp is not None else frame_index / fps,
                    task_index=episode.task_index,
                    observation_state=state_vector or None,
                    action=action_vector or None,
                    state_norm=_norm_from_vector(state_vector),
                    action_norm=_norm_from_vector(action_vector),
                )
            )
        return records

    def _episode_payload(
        self,
        dataset_id: str,
        row: dict[str, Any],
        schema_names: list[str],
    ) -> dict[str, Any]:
        episode_index = int(row.get("episode_index", 0))
        caption = _first_present(row, EPISODE_TEXT_COLUMNS)
        fps = row.get("fps")
        length = _episode_length(row)
        return {
            "dataset_id": dataset_id,
            "episode_index": episode_index,
            "task_index": row.get("task_index"),
            "length": length,
            "success_label": row.get("success_label", row.get("success")),
            "failure_reason": row.get("failure_reason"),
            "quality_score": row.get("quality_score"),
            "review_status": row.get("review_status", "pending"),
            "caption": caption,
            "has_vlm_label": bool(row.get("has_vlm_label", False)),
            "has_human_label": bool(row.get("has_human_label", False)),
            "split": row.get("train_val_test_split", row.get("split")),
            "fps": float(fps) if fps is not None else None,
            "camera_names": _camera_names_from_segments(row),
            "duration_seconds": (length / float(fps)) if length is not None and fps else None,
            "language_instruction": row.get("language_instruction") or row.get("instruction"),
            "task_segments": _task_segments_from_row(row),
        }

    def _camera_names_for_bundle(self, bundle: LanceBundle) -> list[str]:
        manifest_cameras = _camera_names_from_manifest(bundle.published_manifest)
        if manifest_cameras:
            return manifest_cameras

        episode_cameras = set(self._camera_names_from_episode_rows(bundle))
        if episode_cameras:
            return sorted(episode_cameras)
        return sorted(self._camera_names_from_videos_table(bundle))

    def _camera_names_from_episode_rows(self, bundle: LanceBundle) -> list[str]:
        # v2 contract: episodes.lance carries `camera_segments` and no
        # legacy `*_video_blob` alias columns. If the registry didn't already
        # surface the cameras (`_camera_names_for_bundle`), scan
        # `camera_segments` here as the second source of truth.
        schema = bundle.schemas["episodes"]
        if "camera_segments" not in schema:
            return []
        episodes = bundle.tables["episodes"]
        row_count = min(_count_rows(episodes), 100)
        rows = _read_rows(
            episodes,
            columns=["episode_index", "camera_segments"],
            limit=row_count,
        )
        cameras: set[str] = set()
        for row in rows:
            cameras.update(_camera_names_from_segments(row))
        return sorted(cameras)

    def _camera_names_from_videos_table(self, bundle: LanceBundle) -> list[str]:
        return self.media.camera_names_from_media_table(bundle)

    def _get_video_blob_from_videos_table(
        self,
        bundle: LanceBundle,
        episode_row: dict[str, Any] | None,
        episode_index: int,
        camera: str,
    ) -> bytes | None:
        return self.media.video_blob_from_media_table(
            bundle,
            episode_row,
            episode_index,
            camera,
        )

    def _get_episode_blob_source_by_offset(
        self,
        dataset: Any,
        column: str,
        row_offset: int | None,
    ) -> VideoSource | None:
        if row_offset is None or row_offset < 0:
            return None
        try:
            blob_file = dataset.take_blobs(column, indices=[row_offset])[0]
            return _video_source_from_blob_file(blob_file)
        except Exception:
            return None

    def _get_video_source_from_videos_table(
        self,
        bundle: LanceBundle,
        episode_row: dict[str, Any] | None,
        episode_index: int,
        camera: str,
    ) -> VideoSource | None:
        return self.media.video_source_from_media_table(
            bundle,
            episode_row,
            episode_index,
            camera,
        )

    def _read_video_rows(
        self,
        dataset: Any,
        schema: list[str],
        *,
        columns: list[str],
        limit: int,
        filter: str | None = None,
        include_offsets: bool = False,
    ) -> list[dict[str, Any]]:
        selected_columns = _unique_columns(schema, columns)
        if include_offsets:
            rows = _read_rows(
                dataset,
                columns=selected_columns or None,
                limit=_count_rows(dataset),
                offset=0,
            )
            rows = [
                {**row, "__row_offset": offset}
                for offset, row in enumerate(rows)
                if _matches_simple_lance_filter(row, filter)
            ]
            return rows[:limit]
        if hasattr(dataset, "scanner"):
            try:
                scanner = dataset.scanner(
                    columns=selected_columns or None,
                    filter=filter,
                    limit=limit,
                    blob_handling="all_binary",
                )
                return _rows_from_table(scanner.to_table())
            except TypeError:
                scanner = dataset.scanner(
                    columns=selected_columns or None,
                    filter=filter,
                    limit=limit,
                )
                return _rows_from_table(scanner.to_table())
            except Exception:
                pass
        rows = _read_rows(
            dataset,
            columns=selected_columns or None,
            limit=limit,
            offset=0,
        )
        if filter:
            rows = [row for row in rows if _matches_simple_lance_filter(row, filter)]
        return rows

    def _get_video_blob_source_by_offset(
        self,
        dataset: Any,
        blob_name: str,
        row_offset: int | None,
    ) -> VideoSource | None:
        if row_offset is None or row_offset < 0:
            return None
        try:
            blob_file = dataset.take_blobs(blob_name, indices=[row_offset])[0]
            return _video_source_from_blob_file(blob_file)
        except Exception:
            return None

    def _apply_episode_overrides(self, dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        episode_index = int(payload.get("episode_index", 0))
        overrides = self._episode_label_overrides.get(dataset_id, {}).get(episode_index)
        merged = payload if not overrides else {**payload, **overrides}
        merged["dirty_annotation_count"] = _count_dirty_annotations(dataset_id, episode_index)
        return merged

    def _refresh_episode_summary(self, dataset_id: str) -> None:
        record = self._datasets.get(dataset_id)
        episodes = self._episodes.get(dataset_id)
        if record is None or episodes is None:
            return
        updated = [
            EpisodeDetail(**self._apply_episode_overrides(dataset_id, model_dump(episode)))
            for episode in episodes
        ]
        self._summaries[dataset_id] = self._summary_from_episodes(record, updated)

    def _drop_dataset(self, dataset_id: str) -> None:
        self._datasets.pop(dataset_id, None)
        self._summaries.pop(dataset_id, None)
        self._episodes.pop(dataset_id, None)
        self._bundles.pop(dataset_id, None)
        self._episode_row_offsets.pop(dataset_id, None)

    def _episode_count(self, dataset_id: str) -> int:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            try:
                return _count_rows(bundle.tables["episodes"])
            except (OSError, ValueError) as exc:
                self._invalidate_dead_bundle(dataset_id, exc)
                return 0
        return len(self._episodes.get(dataset_id, []))

    def _all_episode_items(self, dataset_id: str) -> list[EpisodeListItem]:
        total = self._episode_count(dataset_id)
        if total == 0:
            return []
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            try:
                return self._list_lance_episodes(dataset_id, bundle, limit=total, offset=0)
            except (OSError, ValueError) as exc:
                self._invalidate_dead_bundle(dataset_id, exc)
                return []
        return [
            EpisodeListItem(**self._apply_episode_overrides(dataset_id, model_dump(episode)))
            for episode in self._episodes.get(dataset_id, [])
        ]

    def _load_dataset_registry(self) -> None:
        if not self.dataset_registry_path.exists():
            return
        kept_any_drop = False
        for line in self.dataset_registry_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                payload = DatasetOpenRequest(uri=row["uri"], name=row.get("name"))
            except (KeyError, TypeError, json.JSONDecodeError, ValueError):
                continue
            if payload.uri.startswith("sample://"):
                continue
            record = self._open_dataset(payload, persist_registry=False)
            # If a local dataset disappeared since the registry entry was
            # written, drop the failed reload record and rewrite the registry.
            # We intentionally try opening first so tests and custom stores that
            # mock Lance paths without real directories still work.
            if (
                record.status == "open_failed"
                and "://" not in payload.uri
                and not Path(payload.uri).exists()
            ):
                print(
                    f"[lance_store] skipping registry entry for missing path: {payload.uri}",
                    file=sys.stderr,
                )
                self._drop_dataset(record.dataset_id)
                kept_any_drop = True
        if kept_any_drop and self.persist_dataset_registry:
            self._persist_dataset_registry()

    def _persist_dataset_registry(self) -> None:
        if not self.persist_dataset_registry:
            return
        rows = [
            {
                "dataset_id": record.dataset_id,
                "name": record.name,
                "uri": record.uri,
            }
            for record in sorted(self._datasets.values(), key=lambda item: item.dataset_id)
            if not record.uri.startswith("sample://")
        ]
        self.dataset_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.dataset_registry_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _load_episode_label_overrides(self) -> None:
        if not self.label_storage_root.exists():
            return
        for dataset_dir in self.label_storage_root.glob("*"):
            labels_path = dataset_dir / "labels.jsonl"
            if not labels_path.exists():
                continue
            try:
                dataset_id = json.loads((dataset_dir / "dataset.json").read_text(encoding="utf-8"))[
                    "dataset_id"
                ]
            except (FileNotFoundError, KeyError, json.JSONDecodeError):
                continue
            rows = {}
            for line in labels_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                episode_index = int(row.pop("episode_index"))
                rows[episode_index] = row
            if rows:
                self._episode_label_overrides[dataset_id] = rows

    def _load_episode_label_history(self) -> None:
        if not self.label_storage_root.exists():
            return
        for history_path in self.label_storage_root.glob("*/episode_label_history.jsonl"):
            for line in history_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    self._episode_label_history.append(
                        EpisodeLabelHistoryRecord(**json.loads(line))
                    )
                except (ValueError, json.JSONDecodeError):
                    continue

    def _persist_episode_label_overrides(self, dataset_id: str) -> None:
        if not self.persist_episode_labels:
            return
        dataset_dir = self.label_storage_root / _slug(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        (dataset_dir / "dataset.json").write_text(
            json.dumps({"dataset_id": dataset_id}, sort_keys=True),
            encoding="utf-8",
        )
        rows = [
            {"episode_index": episode_index, **values}
            for episode_index, values in sorted(
                self._episode_label_overrides.get(dataset_id, {}).items(),
                key=lambda item: item[0],
            )
        ]
        (dataset_dir / "labels.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        self._mirror_episode_labels_lance(dataset_dir / "episode_labels.lance", dataset_id, rows)

    def _mirror_episode_labels_lance(
        self,
        lance_path: Path,
        dataset_id: str,
        rows: list[dict[str, Any]],
    ) -> None:
        if not self.mirror_episode_labels_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_episode_labels_pyarrow_schema()
        updated_at = datetime.now(timezone.utc)
        lance_rows = [
            {
                "dataset_id": dataset_id,
                "episode_index": row["episode_index"],
                "caption": row.get("caption"),
                "success_label": row.get("success_label"),
                "failure_reason": row.get("failure_reason"),
                "quality_score": row.get("quality_score"),
                "split": row.get("split"),
                "review_status": row.get("review_status"),
                "language_instruction": row.get("language_instruction"),
                "has_human_label": bool(row.get("has_human_label", True)),
                "updated_at": updated_at,
            }
            for row in rows
        ]
        if lance_rows:
            table = pa.Table.from_pylist(lance_rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")

    def _append_episode_label_history(
        self,
        *,
        dataset_id: str,
        episode_index: int,
        action: str,
        actor: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        event = EpisodeLabelHistoryRecord(
            event_id=str(uuid4()),
            dataset_id=dataset_id,
            episode_index=episode_index,
            action=action,
            actor=actor,
            before=before,
            after=after,
            created_at=datetime.now(timezone.utc),
        )
        self._episode_label_history.append(event)
        if not self.persist_episode_labels:
            return
        dataset_dir = self.label_storage_root / _slug(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        history_path = dataset_dir / "episode_label_history.jsonl"
        row = model_dump(event)
        if isinstance(row.get("created_at"), datetime):
            row["created_at"] = row["created_at"].isoformat()
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        self._mirror_episode_label_history_lance(
            dataset_dir / "episode_label_history.lance", dataset_id
        )

    def _mirror_episode_label_history_lance(self, lance_path: Path, dataset_id: str) -> None:
        if not self.mirror_episode_labels_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_episode_label_history_pyarrow_schema()
        events = [
            event
            for event in self._episode_label_history
            if event.dataset_id == dataset_id
        ]
        lance_rows = [
            {
                "event_id": event.event_id,
                "dataset_id": event.dataset_id,
                "episode_index": event.episode_index,
                "action": event.action,
                "actor": event.actor,
                "before": json.dumps(event.before, sort_keys=True)
                if event.before is not None
                else None,
                "after": json.dumps(event.after, sort_keys=True)
                if event.after is not None
                else None,
                "created_at": event.created_at,
            }
            for event in events
        ]
        if lance_rows:
            table = pa.Table.from_pylist(lance_rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")


store = LanceDatasetStore(persist_episode_labels=True, persist_dataset_registry=True)
