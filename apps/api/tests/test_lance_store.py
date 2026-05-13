from __future__ import annotations

import json
from io import BytesIO
import sys
import tempfile
import types
from pathlib import Path
import unittest
from unittest.mock import patch

from apps.api.schemas.common import ReviewStatus
from apps.api.schemas.datasets import DatasetOpenRequest
from apps.api.schemas.episodes import EpisodeDetail, EpisodeLabelUpdate
from apps.api.schemas.search import FilterSearchRequest
from apps.api.services import lance_store
from apps.api.services.lance_store import LanceDatasetStore
from apps.api.services.lerobot_io import write_lerobot_v3_snapshot


class FakeSchema:
    def __init__(self, names: list[str]) -> None:
        self.names = names


class FakeTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.num_rows = len(rows)

    def to_pylist(self) -> list[dict[str, object]]:
        return self._rows


class FakePyArrowTable:
    def __init__(self, rows: list[dict[str, object]], schema: list[object]) -> None:
        self.rows = rows
        self.schema = schema

    @classmethod
    def from_pylist(cls, rows: list[dict[str, object]], schema: list[object]) -> "FakePyArrowTable":
        return cls(rows, schema)

    @classmethod
    def from_arrays(cls, arrays: list[object], schema: list[object]) -> "FakePyArrowTable":
        return cls([], schema)


class FakePyArrowModule(types.SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            Table=FakePyArrowTable,
            field=lambda name, type_, nullable=True: types.SimpleNamespace(
                name=name,
                type=type_,
                nullable=nullable,
            ),
            schema=lambda fields, metadata=None: fields,
            string=lambda: "string",
            int64=lambda: "int64",
            float32=lambda: "float32",
            bool_=lambda: "bool",
            timestamp=lambda unit, tz=None: f"timestamp:{unit}:{tz}",
            list_=lambda value_type: f"list:{value_type}",
            array=lambda values, type=None: values,
        )


class FakeScanner:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def to_table(self) -> FakeTable:
        return FakeTable(self._rows)


class FakeBlobFile:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.closed = False

    def read(self) -> bytes:
        return self.payload

    def close(self) -> None:
        self.closed = True


class FakeSeekableBlobFile:
    def __init__(self, payload: bytes) -> None:
        self._handle = BytesIO(payload)
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self._handle.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._handle.seek(offset, whence)

    def tell(self) -> int:
        return self._handle.tell()

    def close(self) -> None:
        self.closed = True
        self._handle.close()


class FakeHttpResponse:
    def __init__(
        self,
        payload: bytes = b"",
        *,
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self._handle = BytesIO(payload)
        self.headers = headers or {}
        self.status_code = status_code

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self._handle.close()

    def read(self, size: int = -1) -> bytes:
        return self._handle.read(size)

    def getcode(self) -> int:
        return self.status_code


class FakeHfFileSystem:
    opened_paths: list[str] = []

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def info(self, path: str) -> dict[str, object]:
        return {"size": len(b"hf-remote-video")}

    def open(self, path: str, mode: str) -> BytesIO:
        self.opened_paths.append(path)
        return BytesIO(b"hf-remote-video")


class FakeObjectStoreFs:
    opened_paths: list[str] = []

    def info(self, path: str) -> dict[str, object]:
        return {"size": len(b"object-store-video")}

    def open(self, path: str, mode: str) -> BytesIO:
        self.opened_paths.append(path)
        return BytesIO(b"object-store-video")


class FakeDataset:
    def __init__(self, rows: list[dict[str, object]], names: list[str]) -> None:
        self._rows = rows
        self.schema = FakeSchema(names)

    def count_rows(self) -> int:
        return len(self._rows)

    def take(self, indices: list[int], columns: list[str] | None = None) -> FakeTable:
        rows = []
        for index in indices:
            row = self._rows[index]
            rows.append(self._project(row, columns))
        return FakeTable(rows)

    def scanner(
        self,
        columns: list[str] | None = None,
        filter: str | None = None,
        limit: int | None = None,
        **_: object,
    ) -> FakeScanner:
        rows = self._rows
        if filter and filter.startswith("episode_index = "):
            episode_index = int(filter.removeprefix("episode_index = "))
            rows = [row for row in rows if row.get("episode_index") == episode_index]
        if limit is not None:
            rows = rows[:limit]
        return FakeScanner([self._project(row, columns) for row in rows])

    def take_blobs(self, blob_column: str, indices: list[int]) -> list[FakeBlobFile]:
        return [FakeBlobFile(self._rows[index][blob_column]) for index in indices]

    @staticmethod
    def _project(row: dict[str, object], columns: list[str] | None) -> dict[str, object]:
        if columns is None:
            return row
        return {column: row[column] for column in columns if column in row}


class NoScannerDataset(FakeDataset):
    """Drops the `scanner` API to force the offset / linear-scan fallback in
    `_read_episode_row_by_index`."""

    scanner = None  # type: ignore[assignment]


class ArrayFetchFailingDataset(FakeDataset):
    """FakeDataset where reads that include `STATE_COLUMNS` or `ACTION_COLUMNS`
    raise IOError, simulating an HF rate-limit or network failure on heavy
    fragment fetches."""

    HEAVY_COLUMNS = frozenset({"observation_state", "actions", "action", "state"})

    def take(self, indices: list[int], columns: list[str] | None = None) -> FakeTable:
        if columns and any(column in self.HEAVY_COLUMNS for column in columns):
            raise IOError("simulated rate limit")
        return super().take(indices, columns)

    def scanner(
        self,
        columns: list[str] | None = None,
        filter: str | None = None,
        limit: int | None = None,
        **_: object,
    ) -> FakeScanner:
        if columns and any(column in self.HEAVY_COLUMNS for column in columns):
            raise IOError("simulated rate limit")
        return super().scanner(columns=columns, filter=filter, limit=limit)


class FakeSeekableBlobDataset(FakeDataset):
    def __init__(self, rows: list[dict[str, object]], names: list[str], blob_column: str) -> None:
        super().__init__(rows, names)
        self.blob_column = blob_column
        self.blob_take_count = 0

    def take(self, indices: list[int], columns: list[str] | None = None) -> FakeTable:
        if columns is not None and self.blob_column in columns:
            raise AssertionError("blob column should be read with take_blobs")
        return super().take(indices, columns)

    def take_blobs(self, blob_column: str, indices: list[int]) -> list[FakeSeekableBlobFile]:
        self.blob_take_count += 1
        return [FakeSeekableBlobFile(self._rows[index][blob_column]) for index in indices]


class LanceDatasetStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_lance = sys.modules.get("lance")
        self.previous_pyarrow = sys.modules.get("pyarrow")
        self.previous_huggingface_hub = sys.modules.get("huggingface_hub")

    def tearDown(self) -> None:
        if self.previous_lance is None:
            sys.modules.pop("lance", None)
        else:
            sys.modules["lance"] = self.previous_lance
        if self.previous_pyarrow is None:
            sys.modules.pop("pyarrow", None)
        else:
            sys.modules["pyarrow"] = self.previous_pyarrow
        if self.previous_huggingface_hub is None:
            sys.modules.pop("huggingface_hub", None)
        else:
            sys.modules["huggingface_hub"] = self.previous_huggingface_hub

    def test_open_dataset_indexes_lerobot_v3_metadata_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=7,
                        task_index=4,
                        length=30,
                        review_status="accepted",
                        fps=15.0,
                        camera_names=["cam_high"],
                        language_instruction="Place the cloth.",
                    )
                ],
                annotations_by_episode={},
                version_description="import test",
            )
            store = LanceDatasetStore()
            record = store.open_dataset(
                DatasetOpenRequest(uri=artifact["root"], name="snapshot-import")
            )
            summary = store.get_summary(record.dataset_id)
            episodes = store.list_episodes(record.dataset_id, limit=10, offset=0)

            self.assertEqual(record.status, "indexed")
            self.assertEqual(record.message, "LeRobot metadata snapshot indexed.")
            self.assertIsNotNone(summary)
            self.assertEqual(summary.episode_count, 1)
            self.assertEqual(summary.frame_count, 30)
            self.assertEqual(summary.camera_names, ["cam_high"])
            self.assertEqual(episodes[0].episode_index, 7)
            self.assertEqual(episodes[0].task_index, 4)

    def test_open_dataset_indexes_lerobot_v2_1_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "ffw"
            (root / "meta").mkdir(parents=True)
            (root / "data" / "chunk-000").mkdir(parents=True)
            (root / "videos" / "chunk-000" / "observation.images.cam_head").mkdir(parents=True)
            info = {
                "codebase_version": "v2.1",
                "robot_type": "ffw_bg2_rev4",
                "total_episodes": 2,
                "total_frames": 50,
                "total_tasks": 1,
                "fps": 30,
                "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
                "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
                "features": {
                    "observation.images.cam_head": {
                        "dtype": "video",
                        "shape": [376, 672, 3],
                        "info": {
                            "video.fps": 30,
                            "video.codec": "libx264",
                            "video.pix_fmt": "yuv420p",
                        },
                    },
                    "observation.state": {"dtype": "float32", "shape": [19]},
                    "action": {"dtype": "float32", "shape": [19]},
                },
            }
            (root / "meta" / "info.json").write_text(json.dumps(info), encoding="utf-8")
            (root / "meta" / "tasks.jsonl").write_text(
                json.dumps({"task_index": 0, "task": "put a block in the orange bin"}) + "\n",
                encoding="utf-8",
            )
            (root / "meta" / "episodes.jsonl").write_text(
                json.dumps({"episode_index": 0, "tasks": ["put a block in the orange bin"], "length": 30}) + "\n"
                + json.dumps({"episode_index": 1, "tasks": ["put a block in the orange bin"], "length": 20}) + "\n",
                encoding="utf-8",
            )

            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri=str(root), name="ffw"))
            summary = store.get_summary(record.dataset_id)
            episodes = store.list_episodes(record.dataset_id, limit=10, offset=0)
            episode_detail = store.get_episode(record.dataset_id, 0)
            sa = store.get_state_action_summary(record.dataset_id, 0)

        self.assertEqual(record.status, "indexed")
        self.assertEqual(summary.episode_count, 2)
        self.assertEqual(summary.frame_count, 50)
        self.assertEqual(summary.fps, 30.0)
        self.assertEqual(summary.camera_names, ["observation_images_cam_head"])
        self.assertIsNotNone(summary.camera_info)
        cam = summary.camera_info["observation_images_cam_head"]
        self.assertEqual(cam["height"], 376)
        self.assertEqual(cam["width"], 672)
        self.assertEqual(cam["codec"], "libx264")
        self.assertEqual(episodes[0].caption, "put a block in the orange bin")
        self.assertEqual(episodes[0].task_index, 0)
        self.assertEqual(episodes[0].length, 30)
        self.assertEqual(episode_detail.duration_seconds, 1.0)
        self.assertEqual(sa.state_dim, 19)
        self.assertEqual(sa.action_dim, 19)

    def test_episode_page_returns_pagination_metadata(self) -> None:
        store = LanceDatasetStore()
        page = store.list_episode_page("sample-xvla-soft-fold", limit=2, offset=0)
        next_page = store.list_episode_page("sample-xvla-soft-fold", limit=2, offset=2)

        self.assertEqual(page.dataset_id, "sample-xvla-soft-fold")
        self.assertEqual(page.total, 3)
        self.assertEqual(page.limit, 2)
        self.assertEqual(page.offset, 0)
        self.assertEqual(page.next_offset, 2)
        self.assertIsNone(page.previous_offset)
        self.assertEqual([episode.episode_index for episode in page.items], [0, 1])
        self.assertEqual([episode.episode_index for episode in next_page.items], [2])
        self.assertIsNone(next_page.next_offset)
        self.assertEqual(next_page.previous_offset, 0)

    def test_episode_page_supports_sort_and_filter_query(self) -> None:
        store = LanceDatasetStore()
        page = store.list_episode_page(
            "sample-xvla-soft-fold",
            limit=10,
            offset=0,
            sort_by="length",
            sort_order="desc",
            filter_query='success_label == true AND review_status == "accepted"',
        )

        self.assertEqual(page.total, 2)
        self.assertEqual(page.sort_by, "length")
        self.assertEqual(page.sort_order, "desc")
        self.assertEqual(page.filter_query, 'success_label == true AND review_status == "accepted"')
        self.assertEqual([episode.episode_index for episode in page.items], [2, 0])

    def test_episode_page_rejects_unsupported_sort_field(self) -> None:
        store = LanceDatasetStore()

        with self.assertRaises(ValueError):
            store.list_episode_page(
                "sample-xvla-soft-fold",
                limit=10,
                offset=0,
                sort_by="not_a_column",
            )

    def test_close_dataset_removes_registry_entry(self) -> None:
        episode_rows = [{"episode_index": 0, "timestamps": [0.0]}]
        fake_tables = {
            "/datasets/closable/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/closable/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/closable/videos.lance": FakeDataset([], ["camera_angle"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "dataset_registry.jsonl"
            store = LanceDatasetStore(
                dataset_registry_path=registry_path,
                persist_dataset_registry=True,
            )
            record = store.open_dataset(DatasetOpenRequest(uri="/datasets/closable", name="closable"))
            closed = store.close_dataset(record.dataset_id)

            self.assertIsNotNone(closed)
            self.assertIsNone(store.get_summary(record.dataset_id))
            self.assertNotIn(record.dataset_id, [dataset.dataset_id for dataset in store.list_datasets()])
            self.assertEqual(registry_path.read_text(encoding="utf-8"), "")

    def test_reload_keeps_builtin_sample_dataset_available(self) -> None:
        store = LanceDatasetStore()
        reloaded = store.reload_dataset("sample-xvla-soft-fold")
        summary = store.get_summary("sample-xvla-soft-fold")

        self.assertIsNotNone(reloaded)
        self.assertIsNotNone(summary)
        self.assertEqual(reloaded.status, "sample")
        self.assertEqual(summary.episode_count, 3)

    def test_applied_deleted_episode_is_hidden_from_curated_view(self) -> None:
        with patch.object(LanceDatasetStore, "_hidden_episode_indices", return_value={0}):
            store = LanceDatasetStore()
            summary = store.get_summary("sample-xvla-soft-fold")
            page = store.list_episode_page("sample-xvla-soft-fold", limit=10, offset=0)

            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.episode_count, 2)
            self.assertEqual(page.total, 2)
            self.assertNotIn(0, [episode.episode_index for episode in page.items])
            self.assertIsNone(store.get_episode("sample-xvla-soft-fold", 0))

    def test_v2_camera_segments_resolve_video_by_stable_media_id(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "camera_segments": [
                    {
                        "camera_key": "observation.images.cam_head",
                        "camera_column": "observation_images_cam_head",
                        "media_id": "episode_00000000_observation_images_cam_head",
                    }
                ],
                "task_segments": [
                    {
                        "task_index": 3,
                        "language_instruction": "Fold the cloth.",
                        "start_frame": 0,
                        "end_frame_exclusive": 1,
                        "start_timestamp": 0.0,
                        "end_timestamp_exclusive": 0.05,
                    }
                ],
            },
        ]
        video_rows = [
            {
                "media_id": "episode_00000000_observation_images_cam_head_old",
                "episode_index": 0,
                "camera_id": "observation_images_cam_head",
                "video_blob": b"wrong-media-id",
            },
            {
                "media_id": "episode_00000000_observation_images_cam_head",
                "episode_index": 0,
                "camera_id": "observation_images_cam_head",
                "video_blob": b"right-media-id",
            },
        ]
        videos = FakeSeekableBlobDataset(video_rows, list(video_rows[0].keys()), "video_blob")
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = Path(tmp) / "v2"
            dataset_root.mkdir()
            (dataset_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "format": "rllab_published_lance_dataset_v2",
                        "schema_version": "2.0",
                        "dataset_id": "v2",
                        "tables": {
                            "episodes": "data/episodes.lance",
                            "frames": "data/frames.lance",
                            "videos": "data/videos.lance",
                        },
                        "modalities": {
                            "state.body": {
                                "kind": "state",
                                "column": "observation_state",
                                "frame_column": "observation_state",
                                "shape": [2],
                            },
                            "video.cam_head": {
                                "kind": "video",
                                "camera_key": "observation.images.cam_head",
                                "camera_column": "observation_images_cam_head",
                            },
                        },
                        "actions": {
                            "action.body": {
                                "kind": "action",
                                "column": "actions",
                                "frame_column": "action",
                                "shape": [2],
                            }
                        },
                        "counts": {"episodes": 1, "frames": 1, "videos": 2},
                    }
                ),
                encoding="utf-8",
            )
            data_root = dataset_root / "data"
            fake_tables = {
                str(data_root / "episodes.lance"): FakeDataset(
                    episode_rows,
                    list(episode_rows[0].keys()),
                ),
                str(data_root / "frames.lance"): FakeDataset([], ["episode_index"]),
                str(data_root / "videos.lance"): videos,
            }
            sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri=str(dataset_root), name="v2"))
            summary = store.get_summary(record.dataset_id)
            detail = store.get_episode(record.dataset_id, 0)
            blob = store.get_video_blob(record.dataset_id, 0, "cam_head")

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(summary.camera_names, ["cam_head"])
        self.assertEqual(len(detail.task_segments), 1)
        self.assertEqual(detail.task_segments[0].start_frame, 0)
        self.assertEqual(detail.task_segments[0].end_frame_exclusive, 1)
        self.assertEqual(blob, b"right-media-id")
        self.assertEqual(videos.blob_take_count, 1)

    def test_v2_dataset_summary_surfaces_action_semantics(self) -> None:
        """B2.7: a v2 manifest with `actions.action.body.semantics` should
        end up exposed on ``DatasetSummary.action_semantics`` so the UI can
        label joint-position vs EE-pose, units, etc."""

        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 0,
                "fps": 20.0,
                "timestamps": [0.0],
                "camera_segments": [],
                "task_segments": [],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = Path(tmp) / "v2_semantics"
            dataset_root.mkdir()
            (dataset_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "format": "rllab_published_lance_dataset_v2",
                        "schema_version": "2.0",
                        "dataset_id": "v2_semantics",
                        "tables": {
                            "episodes": "data/episodes.lance",
                            "frames": "data/frames.lance",
                        },
                        "modalities": {
                            "state.body": {
                                "kind": "state",
                                "column": "observation_state",
                                "shape": [2],
                            },
                        },
                        "actions": {
                            "action.body": {
                                "kind": "action",
                                "column": "actions",
                                "shape": [2],
                                "semantics": {
                                    "command_type": "joint_position",
                                    "absolute_or_delta": "absolute",
                                    "units": "rad",
                                    "control_frame": "robot_base",
                                    "applies_to_interval": "[t_i, t_{i+1})",
                                    "normalized": False,
                                },
                            }
                        },
                        "counts": {"episodes": 1, "frames": 1, "videos": 0},
                    }
                ),
                encoding="utf-8",
            )
            data_root = dataset_root / "data"
            fake_tables = {
                str(data_root / "episodes.lance"): FakeDataset(
                    episode_rows,
                    list(episode_rows[0].keys()),
                ),
                str(data_root / "frames.lance"): FakeDataset([], ["episode_index"]),
            }
            sys.modules["lance"] = types.SimpleNamespace(
                dataset=lambda uri: fake_tables[uri]
            )

            store = LanceDatasetStore()
            record = store.open_dataset(
                DatasetOpenRequest(uri=str(dataset_root), name="v2_semantics")
            )
            summary = store.get_summary(record.dataset_id)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIsNotNone(summary.action_semantics)
        assert summary.action_semantics is not None
        self.assertEqual(summary.action_semantics.command_type, "joint_position")
        self.assertEqual(summary.action_semantics.absolute_or_delta, "absolute")
        self.assertEqual(summary.action_semantics.units, "rad")
        self.assertEqual(summary.action_semantics.control_frame, "robot_base")
        self.assertFalse(summary.action_semantics.normalized)

    def test_filter_search_evaluates_basic_episode_predicates(self) -> None:
        store = LanceDatasetStore()
        results = store.filter_search(
            FilterSearchRequest(
                dataset_id="sample-xvla-soft-fold",
                query="success_label == true AND quality_score >= 0.8",
            )
        )

        self.assertEqual([result.episode_index for result in results], [2])
        self.assertEqual(results[0].match_type, "episode_filter")

    def test_lance_filter_expression_skips_overlay_fields(self) -> None:
        expression = lance_store._lance_filter_expression(
            [("success_label", "==", True)],
            ["episode_index", "success_label"],
        )

        self.assertIsNone(expression)

    def test_filter_search_supports_aliases_and_contains(self) -> None:
        store = LanceDatasetStore()
        results = store.filter_search(
            FilterSearchRequest(
                dataset_id="sample-xvla-soft-fold",
                query='status contains "accept" AND task = 3',
            )
        )

        self.assertEqual([result.episode_index for result in results], [0, 2])

    def test_norm_series_uses_sample_fallback_for_built_in_dataset(self) -> None:
        store = LanceDatasetStore()
        series = store.get_episode_norm_series("sample-xvla-soft-fold", 0)

        self.assertIsNotNone(series)
        self.assertEqual(series.episode_index, 0)
        self.assertGreater(series.frame_count, 0)
        self.assertEqual(len(series.sample_indices), series.sample_count)
        self.assertEqual(len(series.state_norms), series.sample_count)
        self.assertEqual(len(series.action_norms), series.sample_count)
        self.assertEqual(series.sample_indices[0], 0)
        self.assertEqual(series.sample_indices[-1], series.frame_count - 1)
        for value in series.state_norms + series.action_norms:
            self.assertIsNotNone(value)

    def test_list_frames_uses_sample_timeseries_fallback(self) -> None:
        store = LanceDatasetStore()
        frames = store.list_frames(
            "sample-xvla-soft-fold",
            0,
            start_frame=2,
            end_frame=4,
            limit=2,
        )

        self.assertIsNotNone(frames)
        self.assertEqual([frame.frame_index for frame in frames], [2, 3])
        self.assertEqual(frames[0].task_index, 3)
        self.assertAlmostEqual(frames[0].timestamp or 0.0, 0.1)
        self.assertIsNotNone(frames[0].observation_state)
        self.assertIsNotNone(frames[0].action)
        self.assertIsNotNone(frames[0].state_norm)
        self.assertIsNotNone(frames[0].action_norm)

    def test_episode_label_updates_persist_as_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first_store = LanceDatasetStore(
                label_storage_root=storage_root,
                persist_episode_labels=True,
            )

            updated = first_store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(
                    caption="Reviewed fold",
                    success_label=False,
                    failure_reason="cloth slipped",
                    quality_score=0.35,
                    split="val",
                    review_status=ReviewStatus.edited,
                ),
            )

            self.assertIsNotNone(updated)
            self.assertEqual(updated.caption, "Reviewed fold")
            self.assertFalse(updated.success_label)
            self.assertEqual(updated.failure_reason, "cloth slipped")
            self.assertEqual(updated.quality_score, 0.35)
            self.assertEqual(updated.split, "val")
            self.assertEqual(updated.review_status, "edited")
            self.assertTrue(updated.has_human_label)

            second_store = LanceDatasetStore(
                label_storage_root=storage_root,
                persist_episode_labels=True,
            )
            reloaded = second_store.get_episode("sample-xvla-soft-fold", 0)

            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.caption, "Reviewed fold")
            self.assertFalse(reloaded.success_label)
            self.assertEqual(reloaded.failure_reason, "cloth slipped")
            self.assertEqual(reloaded.quality_score, 0.35)
            self.assertEqual(reloaded.split, "val")
            self.assertEqual(reloaded.review_status, "edited")

    def test_episode_label_update_ignores_null_review_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceDatasetStore(
                label_storage_root=Path(tmpdir),
                persist_episode_labels=True,
            )

            first = store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(
                    caption="Reviewed fold",
                    review_status=ReviewStatus.accepted,
                ),
            )
            second = store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(
                    caption="Reviewed fold with note",
                    review_status=None,
                ),
            )

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(second.caption, "Reviewed fold with note")
            self.assertEqual(second.review_status, "accepted")

    def test_episode_label_updates_mirror_lance_table_when_available(self) -> None:
        writes: list[dict[str, object]] = []
        sys.modules["pyarrow"] = FakePyArrowModule()
        sys.modules["lance"] = types.SimpleNamespace(
            write_dataset=lambda table, path, mode: writes.append(
                {"table": table, "path": path, "mode": mode}
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceDatasetStore(
                label_storage_root=Path(tmpdir),
                persist_episode_labels=True,
            )
            store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(
                    caption="Reviewed fold",
                    success_label=None,
                    quality_score=None,
                    split=None,
                    review_status=ReviewStatus.edited,
                ),
            )

        labels_writes = [
            entry for entry in writes if str(entry["path"]).endswith("episode_labels.lance")
        ]
        history_writes = [
            entry for entry in writes if str(entry["path"]).endswith("episode_label_history.lance")
        ]
        self.assertEqual(len(labels_writes), 1)
        self.assertEqual(len(history_writes), 1)
        labels_table = labels_writes[0]["table"]
        self.assertEqual(labels_writes[0]["mode"], "overwrite")
        self.assertEqual(labels_table.rows[0]["dataset_id"], "sample-xvla-soft-fold")
        self.assertEqual(labels_table.rows[0]["episode_index"], 0)
        self.assertEqual(labels_table.rows[0]["caption"], "Reviewed fold")
        self.assertIsNone(labels_table.rows[0]["success_label"])
        self.assertIsNone(labels_table.rows[0]["quality_score"])
        self.assertIsNone(labels_table.rows[0]["split"])
        self.assertEqual(labels_table.rows[0]["review_status"], "edited")
        self.assertTrue(labels_table.rows[0]["has_human_label"])
        history_table = history_writes[0]["table"]
        self.assertEqual(history_writes[0]["mode"], "overwrite")
        self.assertEqual(history_table.rows[0]["action"], "update")
        self.assertEqual(history_table.rows[0]["actor"], "local")

    def test_camera_info_extracted_from_lerobot_info_features(self) -> None:
        from apps.api.services.lance_store import _camera_info_from_features

        features = {
            "observation.images.cam_high": {
                "dtype": "video",
                "shape": [480, 640, 3],
                "info": {
                    "video.fps": 20,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.has_audio": False,
                },
            },
            "observation.images.cam_left_wrist": {
                "dtype": "video",
                "shape": [240, 320, 3],
                "video_info": {"video.fps": 20.0, "video.codec": "av1"},
            },
            "observation.state": {"dtype": "float32", "shape": [14]},
        }

        result = _camera_info_from_features(features)

        self.assertIsNotNone(result)
        self.assertIn("observation_images_cam_high", result)
        cam_high = result["observation_images_cam_high"]
        self.assertEqual(cam_high["height"], 480)
        self.assertEqual(cam_high["width"], 640)
        self.assertEqual(cam_high["channels"], 3)
        self.assertEqual(cam_high["codec"], "h264")
        self.assertEqual(cam_high["pix_fmt"], "yuv420p")
        self.assertEqual(cam_high["fps"], 20)
        self.assertEqual(cam_high["has_audio"], False)
        cam_left = result["observation_images_cam_left_wrist"]
        self.assertEqual(cam_left["codec"], "av1")
        self.assertEqual(cam_left["fps"], 20.0)
        self.assertNotIn("observation_state", result)

    def test_camera_info_returns_none_when_no_video_features(self) -> None:
        from apps.api.services.lance_store import _camera_info_from_features

        self.assertIsNone(_camera_info_from_features(None))
        self.assertIsNone(_camera_info_from_features({"observation.state": {"dtype": "float32"}}))

    def test_read_episode_row_by_index_handles_gappy_indices(self) -> None:
        from apps.api.services.lance_store import _read_episode_row_by_index

        rows = [
            {"episode_index": 0, "task_index": 1, "fps": 20.0},
            {"episode_index": 2, "task_index": 1, "fps": 20.0},
            {"episode_index": 5, "task_index": 1, "fps": 20.0},
        ]
        dataset = NoScannerDataset(rows, ["episode_index", "task_index", "fps"])

        row_5 = _read_episode_row_by_index(dataset, 5, columns=["episode_index", "fps"])
        row_0 = _read_episode_row_by_index(dataset, 0, columns=["episode_index", "fps"])
        row_missing = _read_episode_row_by_index(dataset, 4, columns=["episode_index", "fps"])

        self.assertIsNotNone(row_5)
        self.assertEqual(row_5["episode_index"], 5)
        self.assertIsNotNone(row_0)
        self.assertEqual(row_0["episode_index"], 0)
        self.assertIsNone(row_missing)

    def test_episode_label_history_records_actor_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            store = LanceDatasetStore(
                label_storage_root=storage_root,
                persist_episode_labels=True,
                mirror_episode_labels_lance=False,
            )
            store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(
                    caption="Reviewed fold",
                    review_status=ReviewStatus.accepted,
                    updated_by="alice",
                ),
            )
            store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(
                    caption="Reviewed fold (revised)",
                    updated_by="bob",
                ),
            )

            history = store.list_episode_label_history(
                "sample-xvla-soft-fold", episode_index=0
            )

        self.assertEqual([event.actor for event in history], ["alice", "bob"])
        self.assertEqual([event.action for event in history], ["update", "update"])
        first_after = history[0].after or {}
        self.assertEqual(first_after.get("caption"), "Reviewed fold")
        self.assertEqual(first_after.get("review_status"), "accepted")
        second_before = history[1].before or {}
        second_after = history[1].after or {}
        self.assertEqual(second_before.get("caption"), "Reviewed fold")
        self.assertEqual(second_after.get("caption"), "Reviewed fold (revised)")

    def test_episode_label_history_round_trips_after_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first = LanceDatasetStore(
                label_storage_root=storage_root,
                persist_episode_labels=True,
                mirror_episode_labels_lance=False,
            )
            first.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(caption="Round-trip", updated_by="alice"),
            )

            second = LanceDatasetStore(
                label_storage_root=storage_root,
                persist_episode_labels=True,
                mirror_episode_labels_lance=False,
            )
            history = second.list_episode_label_history(
                "sample-xvla-soft-fold", episode_index=0
            )

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].actor, "alice")
        self.assertEqual((history[0].after or {}).get("caption"), "Round-trip")

    def test_episode_label_update_does_not_leak_updated_by_into_episode_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceDatasetStore(
                label_storage_root=Path(tmpdir),
                persist_episode_labels=True,
                mirror_episode_labels_lance=False,
            )
            updated = store.update_episode_labels(
                "sample-xvla-soft-fold",
                0,
                EpisodeLabelUpdate(caption="No leak", updated_by="alice"),
            )

        self.assertIsNotNone(updated)
        self.assertFalse(hasattr(updated, "updated_by"))
        overrides = store._episode_label_overrides["sample-xvla-soft-fold"][0]
        self.assertNotIn("updated_by", overrides)


if __name__ == "__main__":
    unittest.main()
