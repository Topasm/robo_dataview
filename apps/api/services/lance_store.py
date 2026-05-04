from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
import math
import re
from pathlib import Path
from typing import Any

from apps.api.schemas.datasets import DatasetOpenRequest, DatasetRecord, DatasetSummary
from apps.api.schemas.episodes import (
    EpisodeDetail,
    EpisodeLabelUpdate,
    EpisodeListItem,
    EpisodeTimeseries,
    StateActionSummary,
)
from apps.api.schemas.frames import FrameRecord
from apps.api.schemas.search import FilterSearchRequest, SearchResult
from apps.api.services.lerobot_io import read_lerobot_snapshot_episodes
from apps.api.services.pydantic_compat import model_dump

NORM_SERIES_MAX_POINTS = 600
EPISODE_LABEL_STORAGE_ROOT = Path("data/lance/episode_labels")
TABLE_NAMES = ("frames", "episodes", "videos")
STATE_COLUMNS = ("observation_state", "observation.state", "state")
ACTION_COLUMNS = ("actions", "action")
TIMESTAMP_COLUMNS = ("timestamps", "timestamp")
FRAME_INDEX_COLUMNS = ("frame_index", "frame_idx", "index")
FRAME_TIMESTAMP_COLUMNS = ("timestamp", "timestamps")
EPISODE_TEXT_COLUMNS = ("episode_caption", "caption", "language_instruction", "instruction")
FILTER_ALIASES = {
    "success": "success_label",
    "quality": "quality_score",
    "status": "review_status",
    "review": "review_status",
    "task": "task_index",
    "episode": "episode_index",
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


def _camera_names_from_schema(names: list[str]) -> list[str]:
    cameras = []
    for name in names:
        if name.endswith("_video_blob"):
            cameras.append(name[: -len("_video_blob")])
        elif name.endswith("_video"):
            cameras.append(name[: -len("_video")])
    return cameras


def _video_column_for_camera(names: list[str], camera: str) -> str | None:
    candidates = (
        f"{camera}_video_blob",
        f"{camera}_video",
        f"{camera}_mp4_blob",
        f"{camera}_mp4",
        camera,
    )
    for candidate in candidates:
        if candidate in names:
            return candidate
    return None


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


@dataclass
class LanceBundle:
    base_uri: str
    tables: dict[str, Any]
    schemas: dict[str, list[str]]


class LanceDependencyError(RuntimeError):
    pass


class LanceDatasetStore:
    """Thin service boundary for Lance-backed dataset access.

    Lance itself is an optional dependency. When it is installed this service
    indexes `frames.lance`, `episodes.lance`, and `videos.lance` from a dataset
    root URI. A small sample fixture stays available for local UI development.
    """

    def __init__(
        self,
        label_storage_root: Path = EPISODE_LABEL_STORAGE_ROOT,
        *,
        persist_episode_labels: bool = False,
    ) -> None:
        self.label_storage_root = label_storage_root
        self.persist_episode_labels = persist_episode_labels
        self._datasets: dict[str, DatasetRecord] = {}
        self._summaries: dict[str, DatasetSummary] = {}
        self._episodes: dict[str, list[EpisodeDetail]] = {}
        self._bundles: dict[str, LanceBundle] = {}
        self._episode_label_overrides: dict[str, dict[int, dict[str, Any]]] = {}
        if self.persist_episode_labels:
            self._load_episode_label_overrides()
        self._seed_demo_dataset()

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
        name = payload.name or self._name_from_uri(payload.uri)
        dataset_id = _slug(name)
        lerobot_episodes = self._try_open_lerobot_snapshot(payload.uri, dataset_id)
        if lerobot_episodes is not None:
            record = DatasetRecord(
                dataset_id=dataset_id,
                name=name,
                uri=payload.uri,
                status="indexed",
                message="LeRobot v3 metadata snapshot indexed.",
            )
            self._datasets[dataset_id] = record
            self._bundles.pop(dataset_id, None)
            self._episodes[dataset_id] = lerobot_episodes
            self._summaries[dataset_id] = self._summary_from_episodes(record, lerobot_episodes)
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
            self._episodes.setdefault(dataset_id, [])
            self._summaries[dataset_id] = self._empty_summary(record)
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
            self._episodes.setdefault(dataset_id, [])
            self._summaries[dataset_id] = self._empty_summary(record)
            return record

        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            uri=payload.uri,
            status="indexed",
            message="Lance dataset indexed.",
        )
        self._datasets[dataset_id] = record
        self._bundles[dataset_id] = bundle
        self._episodes.pop(dataset_id, None)
        self._summaries[dataset_id] = self._build_summary(record, bundle)
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

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[EpisodeListItem]:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return self._list_lance_episodes(dataset_id, bundle, limit=limit, offset=offset)
        episodes = self._episodes.get(dataset_id, [])
        return [
            EpisodeListItem(**self._apply_episode_overrides(dataset_id, model_dump(episode)))
            for episode in episodes[offset : offset + limit]
        ]

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
        if "review_status" in updates and updates["review_status"] is not None:
            updates["review_status"] = getattr(updates["review_status"], "value", updates["review_status"])
        if not updates:
            return existing

        dataset_overrides = self._episode_label_overrides.setdefault(dataset_id, {})
        current = dataset_overrides.get(episode_index, {})
        dataset_overrides[episode_index] = {
            **current,
            **updates,
            "has_human_label": True,
        }
        self._persist_episode_label_overrides(dataset_id)
        self._refresh_episode_summary(dataset_id)
        return self.get_episode(dataset_id, episode_index)

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
        return StateActionSummary(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_count=episode.length or 0,
            state_dim=14,
            action_dim=14,
            state_norm_min=0.0,
            state_norm_max=1.0,
            action_norm_min=0.0,
            action_norm_max=1.0,
        )

    def get_video_blob(
        self,
        dataset_id: str,
        episode_index: int,
        camera: str,
    ) -> bytes | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is None:
            return None
        schema = bundle.schemas["episodes"]
        column = _video_column_for_camera(schema, camera)
        if column is None:
            return None
        dataset = bundle.tables["episodes"]

        row = _read_episode_row_by_index(
            dataset,
            episode_index,
            columns=["episode_index", column],
        )
        if row is not None:
            blob = _blob_to_bytes(row.get(column))
            if blob is not None:
                return blob

        if hasattr(dataset, "take_blobs"):
            try:
                offset_rows = _read_rows(dataset, columns=["episode_index"], limit=1, offset=episode_index)
                if not offset_rows or int(offset_rows[0].get("episode_index", -1)) != episode_index:
                    return None
                blob_file = dataset.take_blobs(column, indices=[episode_index])[0]
                try:
                    return blob_file.read()
                finally:
                    blob_file.close()
            except Exception:
                pass
        return None

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
            )

        stride = max(1, math.ceil(frame_count / NORM_SERIES_MAX_POINTS))
        sample_indices = list(range(0, frame_count, stride))
        if sample_indices[-1] != frame_count - 1:
            sample_indices.append(frame_count - 1)

        state_norms = [_norm_at(states, index) for index in sample_indices]
        action_norms = [_norm_at(actions, index) for index in sample_indices]
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
            state_dim=_vector_dim(states),
            action_dim=_vector_dim(actions),
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
        episodes = self.list_episodes(payload.dataset_id, limit=payload.limit, offset=0)
        try:
            filters = _parse_filter_query(payload.query)
        except ValueError:
            return []
        matched = [
            episode
            for episode in episodes
            if all(_matches_filter(episode, field, operator, expected) for field, operator, expected in filters)
        ]
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
        return read_lerobot_snapshot_episodes(path, dataset_id=dataset_id)

    def _open_lance_bundle(self, uri: str) -> LanceBundle:
        try:
            lance = import_module("lance")
        except ImportError as exc:
            raise LanceDependencyError(
                "Python package 'lance' is not installed. Install the optional Lance dependencies "
                "before opening real .lance datasets."
            ) from exc

        tables: dict[str, Any] = {}
        for table_name in TABLE_NAMES:
            candidate_uri = _table_uri(uri, table_name)
            try:
                tables[table_name] = lance.dataset(candidate_uri)
            except Exception:
                if table_name == "episodes" and uri.rstrip("/").endswith(".lance"):
                    tables[table_name] = lance.dataset(uri)
                elif table_name == "episodes":
                    raise
        return LanceBundle(
            base_uri=uri,
            tables=tables,
            schemas={name: _schema_names(dataset) for name, dataset in tables.items()},
        )

    def _build_summary(self, record: DatasetRecord, bundle: LanceBundle) -> DatasetSummary:
        episodes = bundle.tables["episodes"]
        episode_count = _count_rows(episodes)
        frames = bundle.tables.get("frames")
        frame_count = _count_rows(frames) if frames is not None else 0
        episode_schema = bundle.schemas["episodes"]
        camera_names = _camera_names_from_schema(episode_schema)
        sample = self._get_lance_episode(record.dataset_id, bundle, 0)
        if frame_count == 0 and sample is not None and sample.length is not None:
            frame_count = sum(episode.length or 0 for episode in self._list_lance_episodes(record.dataset_id, bundle, 10000, 0))
        return DatasetSummary(
            dataset_id=record.dataset_id,
            name=record.name,
            uri=record.uri,
            status=record.status,
            episode_count=episode_count,
            frame_count=frame_count,
            fps=sample.fps if sample is not None else None,
            camera_names=camera_names,
            reviewed_count=0,
            accepted_count=0,
            rejected_count=0,
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
        return [
            EpisodeListItem(
                **self._apply_episode_overrides(
                    dataset_id,
                    self._episode_payload(dataset_id, row, bundle.schemas["episodes"]),
                )
            )
            for row in rows
        ]

    def _get_lance_episode(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> EpisodeDetail | None:
        columns = _metadata_columns(bundle.schemas["episodes"], include_arrays=False)
        row = _read_episode_row_by_index(bundle.tables["episodes"], episode_index, columns=columns)
        if row is None:
            return None
        payload = self._apply_episode_overrides(
            dataset_id,
            self._episode_payload(dataset_id, row, bundle.schemas["episodes"]),
        )
        return EpisodeDetail(**payload)

    def _get_lance_state_action_summary(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> StateActionSummary | None:
        schema = bundle.schemas["episodes"]
        state_name = _first_present_name(schema, STATE_COLUMNS)
        action_name = _first_present_name(schema, ACTION_COLUMNS)
        timestamp_name = _first_present_name(schema, TIMESTAMP_COLUMNS)
        columns = [column for column in (state_name, action_name, timestamp_name, "episode_index") if column]
        row = _read_episode_row_by_index(bundle.tables["episodes"], episode_index, columns=columns)
        if row is None:
            return None
        states = row.get(state_name) if state_name else None
        actions = row.get(action_name) if action_name else None
        state_min, state_max = _norm_bounds(states)
        action_min, action_max = _norm_bounds(actions)
        return StateActionSummary(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_count=_episode_length(row) or 0,
            state_dim=_vector_dim(states),
            action_dim=_vector_dim(actions),
            state_norm_min=state_min,
            state_norm_max=state_max,
            action_norm_min=action_min,
            action_norm_max=action_max,
        )

    def _get_lance_episode_timeseries(
        self,
        dataset_id: str,
        bundle: LanceBundle,
        episode_index: int,
    ) -> dict[str, Any] | None:
        schema = bundle.schemas["episodes"]
        state_name = _first_present_name(schema, STATE_COLUMNS)
        action_name = _first_present_name(schema, ACTION_COLUMNS)
        timestamp_name = _first_present_name(schema, TIMESTAMP_COLUMNS)
        columns = [
            column
            for column in (state_name, action_name, timestamp_name, "episode_index")
            if column is not None
        ]
        row = _read_episode_row_by_index(bundle.tables["episodes"], episode_index, columns=columns)
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
        state_name = _first_present_name(schema, STATE_COLUMNS)
        action_name = _first_present_name(schema, ACTION_COLUMNS)
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
            "camera_names": _camera_names_from_schema(schema_names),
            "duration_seconds": (length / float(fps)) if length is not None and fps else None,
            "language_instruction": row.get("language_instruction") or row.get("instruction"),
        }

    def _apply_episode_overrides(self, dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        episode_index = int(payload.get("episode_index", 0))
        overrides = self._episode_label_overrides.get(dataset_id, {}).get(episode_index)
        if not overrides:
            return payload
        return {**payload, **overrides}

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


store = LanceDatasetStore(persist_episode_labels=True)
