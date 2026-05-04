from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import math
import re
from pathlib import Path
from typing import Any

from apps.api.schemas.datasets import DatasetOpenRequest, DatasetRecord, DatasetSummary
from apps.api.schemas.episodes import EpisodeDetail, EpisodeListItem, StateActionSummary
from apps.api.schemas.search import FilterSearchRequest, SearchResult, SemanticSearchRequest

TABLE_NAMES = ("frames", "episodes", "videos")
STATE_COLUMNS = ("observation_state", "observation.state", "state")
ACTION_COLUMNS = ("actions", "action")
TIMESTAMP_COLUMNS = ("timestamps", "timestamp")
EPISODE_TEXT_COLUMNS = ("episode_caption", "caption", "language_instruction", "instruction")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "dataset"


def _has_uri_scheme(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value))


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

    def __init__(self) -> None:
        self._datasets: dict[str, DatasetRecord] = {}
        self._summaries: dict[str, DatasetSummary] = {}
        self._episodes: dict[str, list[EpisodeDetail]] = {}
        self._bundles: dict[str, LanceBundle] = {}
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

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[EpisodeListItem]:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return self._list_lance_episodes(dataset_id, bundle, limit=limit, offset=offset)
        episodes = self._episodes.get(dataset_id, [])
        return [EpisodeListItem(**episode.dict()) for episode in episodes[offset : offset + limit]]

    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        bundle = self._bundles.get(dataset_id)
        if bundle is not None:
            return self._get_lance_episode(dataset_id, bundle, episode_index)
        for episode in self._episodes.get(dataset_id, []):
            if episode.episode_index == episode_index:
                return episode
        return None

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
        row = _read_episode_row_by_index(
            bundle.tables["episodes"],
            episode_index,
            columns=["episode_index", column],
        )
        if row is None:
            return None
        return _blob_to_bytes(row.get(column))

    def filter_search(self, payload: FilterSearchRequest) -> list[SearchResult]:
        episodes = self.list_episodes(payload.dataset_id, limit=payload.limit, offset=0)
        return [
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=None,
                match_type="filter_stub",
                label=payload.query,
            )
            for episode in episodes
        ]

    def semantic_search(self, payload: SemanticSearchRequest) -> list[SearchResult]:
        episodes = self.list_episodes(payload.dataset_id, limit=payload.limit, offset=0)
        return [
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=0.5,
                match_type="semantic_stub",
                label=payload.text,
            )
            for episode in episodes
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
            EpisodeListItem(**self._episode_payload(dataset_id, row, bundle.schemas["episodes"]))
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
        payload = self._episode_payload(dataset_id, row, bundle.schemas["episodes"])
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


store = LanceDatasetStore()
