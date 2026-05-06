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

    def test_open_dataset_indexes_episode_summary_and_state_action(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0, 0.05, 0.1],
                "actions": [[1.0, 0.0], [0.0, 2.0], [3.0, 4.0]],
                "observation_state": [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]],
                "language_instruction": "Fold the cloth.",
                "episode_caption": "Clean fold",
                "cam_high_video_blob": b"not-loaded-in-metadata",
                "cam_left_wrist_video_blob": b"not-loaded-in-metadata",
            },
            {
                "episode_index": 1,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0, 0.05],
                "actions": [[0.0, 0.0], [0.0, 1.0]],
                "observation_state": [[0.0, 0.0], [1.0, 0.0]],
                "episode_caption": "Cloth slip",
                "cam_high_video_blob": b"not-loaded-in-metadata",
                "cam_left_wrist_video_blob": b"not-loaded-in-metadata",
            },
        ]
        fake_tables = {
            "/datasets/xvla/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/xvla/frames.lance": FakeDataset(
                [{"episode_index": 0}, {"episode_index": 0}, {"episode_index": 1}],
                ["episode_index"],
            ),
            "/datasets/xvla/videos.lance": FakeDataset([], ["camera_angle", "video_blob"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/xvla", name="xvla"))
        summary = store.get_summary(record.dataset_id)
        episodes = store.list_episodes(record.dataset_id, limit=10, offset=0)
        detail = store.get_episode(record.dataset_id, 0)
        state_action = store.get_state_action_summary(record.dataset_id, 0)
        video_blob = store.get_video_blob(record.dataset_id, 0, "cam_high")

        self.assertEqual(record.status, "indexed")
        self.assertIsNotNone(summary)
        self.assertEqual(summary.episode_count, 2)
        self.assertEqual(summary.frame_count, 3)
        self.assertEqual(summary.camera_names, ["cam_high", "cam_left_wrist"])
        self.assertEqual([episode.episode_index for episode in episodes], [0, 1])
        self.assertEqual(episodes[0].length, 3)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.caption, "Clean fold")
        self.assertEqual(detail.duration_seconds, 0.15)
        self.assertIsNotNone(state_action)
        self.assertEqual(state_action.state_dim, 2)
        self.assertEqual(state_action.action_dim, 2)
        self.assertEqual(state_action.action_norm_max, 5.0)
        self.assertEqual(video_blob, b"not-loaded-in-metadata")

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

    def test_opened_dataset_registry_reloads_across_store_instances(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0, 0.05],
                "actions": [[0.0], [1.0]],
                "observation_state": [[0.0], [1.0]],
            }
        ]
        fake_tables = {
            "/datasets/persisted/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/persisted/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/persisted/videos.lance": FakeDataset([], ["camera_angle"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "dataset_registry.jsonl"
            first_store = LanceDatasetStore(
                dataset_registry_path=registry_path,
                persist_dataset_registry=True,
            )
            first_record = first_store.open_dataset(
                DatasetOpenRequest(uri="/datasets/persisted", name="persisted")
            )

            second_store = LanceDatasetStore(
                dataset_registry_path=registry_path,
                persist_dataset_registry=True,
            )
            reloaded = second_store.get_summary(first_record.dataset_id)
            registry_rows = [
                json.loads(line)
                for line in registry_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(first_record.status, "indexed")
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.episode_count, 1)
            self.assertEqual(registry_rows[0]["dataset_id"], "persisted")
            self.assertEqual(registry_rows[0]["uri"], "/datasets/persisted")

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

    def test_reload_dataset_reindexes_existing_uri(self) -> None:
        episode_rows = [{"episode_index": 0, "timestamps": [0.0]}]
        fake_tables = {
            "/datasets/reloadable/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/reloadable/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/reloadable/videos.lance": FakeDataset([], ["camera_angle"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/reloadable", name="reloadable"))
        episode_rows.append({"episode_index": 1, "timestamps": [0.0, 0.05]})
        reloaded = store.reload_dataset(record.dataset_id)
        summary = store.get_summary(record.dataset_id)

        self.assertIsNotNone(reloaded)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.episode_count, 2)

    def test_dataset_health_reports_lance_tables_and_non_contiguous_episode_warning(self) -> None:
        episode_rows = [
            {"episode_index": 0, "timestamps": [0.0], "actions": [[0.0]], "observation_state": [[0.0]]},
            {"episode_index": 2, "timestamps": [0.0], "actions": [[0.0]], "observation_state": [[0.0]]},
        ]
        fake_tables = {
            "/datasets/health/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/health/frames.lance": FakeDataset(
                [{"episode_index": 0, "frame_index": 0}],
                ["episode_index", "frame_index"],
            ),
            "/datasets/health/videos.lance": FakeDataset([], ["camera_name", "video_path"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/health", name="health"))
        shallow = store.get_health(record.dataset_id)
        health = store.get_health(record.dataset_id, level="deep")

        self.assertIsNotNone(shallow)
        assert shallow is not None
        self.assertEqual(shallow.level, "shallow")
        self.assertFalse(
            any("non-contiguous" in warning for warning in shallow.warnings),
            shallow.warnings,
        )
        self.assertIsNotNone(health)
        assert health is not None
        self.assertTrue(health.ok)
        self.assertEqual(health.level, "deep")
        self.assertEqual(health.storage_model, "lance")
        self.assertEqual([table.table for table in health.tables], ["frames", "episodes", "videos"])
        self.assertTrue(
            any("non-contiguous" in warning for warning in health.warnings),
            health.warnings,
        )

    def test_reload_keeps_builtin_sample_dataset_available(self) -> None:
        store = LanceDatasetStore()
        reloaded = store.reload_dataset("sample-xvla-soft-fold")
        summary = store.get_summary("sample-xvla-soft-fold")

        self.assertIsNotNone(reloaded)
        self.assertIsNotNone(summary)
        self.assertEqual(reloaded.status, "sample")
        self.assertEqual(summary.episode_count, 3)

    def test_video_blob_uses_episode_index_filter_before_row_offset(self) -> None:
        episode_rows = [
            {
                "episode_index": 42,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "cam_high_video_blob": b"sparse-index-video",
            },
            {
                "episode_index": 7,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "cam_high_video_blob": b"other-video",
            },
        ]
        fake_tables = {
            "/datasets/sparse/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/sparse/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/sparse/videos.lance": FakeDataset([], ["camera_angle", "video_blob"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/sparse", name="sparse"))
        video_blob = store.get_video_blob(record.dataset_id, 42, "cam_high")

        self.assertEqual(video_blob, b"sparse-index-video")

    def test_video_blob_resolves_observation_image_camera_suffix(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "observation_images_cam_high_video_blob": b"prefixed-video",
            },
        ]
        fake_tables = {
            "/datasets/prefixed/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/prefixed/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/prefixed/videos.lance": FakeDataset([], ["camera_angle", "video_blob"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/prefixed", name="prefixed"))
        video_blob = store.get_video_blob(record.dataset_id, 0, "cam_high")

        self.assertEqual(video_blob, b"prefixed-video")

    def test_video_source_uses_seekable_episode_blob_reader_when_available(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "cam_high_video_blob": b"seekable-video",
            },
        ]
        episodes = FakeSeekableBlobDataset(
            episode_rows,
            list(episode_rows[0].keys()),
            "cam_high_video_blob",
        )
        fake_tables = {
            "/datasets/seekable/episodes.lance": episodes,
            "/datasets/seekable/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/seekable/videos.lance": FakeDataset([], ["camera_angle", "video_blob"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/seekable", name="seekable"))
        source = store.get_video_source(record.dataset_id, 0, "cam_high")

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.size, len(b"seekable-video"))
        self.assertIsNone(source.data)
        self.assertIsNone(source.path)
        self.assertEqual(source.read_all(), b"seekable-video")
        self.assertEqual(episodes.blob_take_count, 1)

    def test_video_blob_falls_back_to_videos_lance_episode_rows(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
            },
            {
                "episode_index": 1,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
            },
        ]
        video_rows = [
            {
                "episode_index": 0,
                "camera_angle": "cam_high",
                "video_blob": b"episode-0-high",
            },
            {
                "episode_index": 1,
                "camera_angle": "cam_high",
                "video_blob": b"episode-1-high",
            },
            {
                "episode_index": 0,
                "camera_angle": "cam_left_wrist",
                "video_blob": b"episode-0-left",
            },
        ]
        fake_tables = {
            "/datasets/videos/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/videos/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/videos/videos.lance": FakeDataset(
                video_rows,
                list(video_rows[0].keys()),
            ),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/videos", name="videos"))
        summary = store.get_summary(record.dataset_id)
        detail = store.get_episode(record.dataset_id, 0)
        high_blob = store.get_video_blob(record.dataset_id, 1, "cam_high")
        left_blob = store.get_video_blob(record.dataset_id, 0, "cam_left_wrist")

        self.assertIsNotNone(summary)
        self.assertEqual(summary.camera_names, ["cam_high", "cam_left_wrist"])
        self.assertIsNotNone(detail)
        self.assertEqual(detail.camera_names, ["cam_high", "cam_left_wrist"])
        self.assertEqual(high_blob, b"episode-1-high")
        self.assertEqual(left_blob, b"episode-0-left")

    def test_video_source_uses_seekable_videos_lance_blob_reader_when_available(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
            },
        ]
        video_rows = [
            {
                "episode_index": 0,
                "camera_angle": "cam_high",
                "video_blob": b"seekable-videos-table",
            },
        ]
        videos = FakeSeekableBlobDataset(
            video_rows,
            list(video_rows[0].keys()),
            "video_blob",
        )
        fake_tables = {
            "/datasets/seekable-videos/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/seekable-videos/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/seekable-videos/videos.lance": videos,
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/seekable-videos", name="seekable-videos"))
        source = store.get_video_source(record.dataset_id, 0, "cam_high")

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.size, len(b"seekable-videos-table"))
        self.assertIsNone(source.data)
        self.assertIsNone(source.path)
        self.assertEqual(source.read_all(), b"seekable-videos-table")
        self.assertEqual(videos.blob_take_count, 1)

    def test_video_blob_falls_back_to_videos_lance_shard_refs(self) -> None:
        episode_rows = [
            {
                "episode_index": 3,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "videos/cam_high/chunk_index": 2,
                "videos/cam_high/file_index": 5,
            },
        ]
        video_rows = [
            {
                "camera_angle": "cam_high",
                "chunk_index": 2,
                "file_index": 4,
                "video_blob": b"wrong-file",
            },
            {
                "camera_angle": "cam_high",
                "chunk_index": 2,
                "file_index": 5,
                "video_blob": b"shard-video",
            },
            {
                "camera_angle": "cam_left_wrist",
                "chunk_index": 2,
                "file_index": 5,
                "video_blob": b"wrong-camera",
            },
        ]
        fake_tables = {
            "/datasets/shards/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/shards/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/shards/videos.lance": FakeDataset(
                video_rows,
                list(video_rows[0].keys()),
            ),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/shards", name="shards"))
        video_blob = store.get_video_blob(record.dataset_id, 3, "cam_high")

        self.assertEqual(video_blob, b"shard-video")

    def test_video_blob_falls_back_to_videos_lance_relative_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_root = Path(tmpdir) / "dataset"
            video_path = dataset_root / "videos" / "cam_high" / "episode_000003.mp4"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"file-video")
            episode_rows = [
                {
                    "episode_index": 3,
                    "task_index": 3,
                    "fps": 20.0,
                    "timestamps": [0.0],
                    "videos/cam_high/chunk_index": 0,
                    "videos/cam_high/file_index": 3,
                },
            ]
            video_rows = [
                {
                    "camera_angle": "cam_high",
                    "chunk_index": 0,
                    "file_index": 3,
                    "relative_path": "videos/cam_high/episode_000003.mp4",
                    "file_size_bytes": len(b"file-video"),
                },
            ]
            fake_tables = {
                str(dataset_root / "episodes.lance"): FakeDataset(
                    episode_rows,
                    list(episode_rows[0].keys()),
                ),
                str(dataset_root / "frames.lance"): FakeDataset([], ["episode_index"]),
                str(dataset_root / "videos.lance"): FakeDataset(
                    video_rows,
                    list(video_rows[0].keys()),
                ),
            }
            sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri=str(dataset_root), name="path-videos"))
            video_source = store.get_video_source(record.dataset_id, 3, "cam_high")
            video_blob = store.get_video_blob(record.dataset_id, 3, "cam_high")

        self.assertIsNotNone(video_source)
        self.assertEqual(video_source.path, video_path)
        self.assertEqual(video_source.size, len(b"file-video"))
        self.assertIsNone(video_source.data)
        self.assertEqual(video_blob, b"file-video")

    def test_video_source_streams_remote_http_relative_file_by_range(self) -> None:
        episode_rows = [
            {
                "episode_index": 3,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "videos/cam_high/chunk_index": 0,
                "videos/cam_high/file_index": 3,
            },
        ]
        video_rows = [
            {
                "camera_angle": "cam_high",
                "chunk_index": 0,
                "file_index": 3,
                "relative_path": "videos/cam_high/episode_000003.mp4",
                "file_size_bytes": len(b"0123456789abcdef"),
            },
        ]
        base_uri = "https://example.test/datasets/root/data"
        fake_tables = {
            f"{base_uri}/episodes.lance": FakeDataset(episode_rows, list(episode_rows[0].keys())),
            f"{base_uri}/frames.lance": FakeDataset([], ["episode_index"]),
            f"{base_uri}/videos.lance": FakeDataset(video_rows, list(video_rows[0].keys())),
        }
        requests: list[tuple[str, str, str | None]] = []

        def fake_urlopen(request, timeout=0):
            url = request.full_url
            method = request.get_method()
            range_header = request.headers.get("Range")
            requests.append((method, url, range_header))
            if method == "HEAD":
                return FakeHttpResponse(headers={"Content-Length": str(len(b"0123456789abcdef"))})
            if range_header == "bytes=5-8":
                return FakeHttpResponse(b"5678", status_code=206)
            raise AssertionError(f"unexpected HTTP request: {method} {url} {range_header}")

        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        with patch("apps.api.services.lance_store.urlopen", side_effect=fake_urlopen):
            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri=base_uri, name="remote-videos"))
            video_source = store.get_video_source(record.dataset_id, 3, "cam_high")
            assert video_source is not None
            chunks = list(video_source.iter_range(5, 8, chunk_size=2))

        self.assertEqual(video_source.size, len(b"0123456789abcdef"))
        self.assertEqual(b"".join(chunks), b"5678")
        self.assertEqual(requests[0], ("HEAD", f"{base_uri}/videos/cam_high/episode_000003.mp4", None))
        self.assertEqual(requests[1], ("GET", f"{base_uri}/videos/cam_high/episode_000003.mp4", "bytes=5-8"))

    def test_video_source_streams_hf_relative_file_by_range_when_available(self) -> None:
        FakeHfFileSystem.opened_paths = []
        episode_rows = [
            {
                "episode_index": 3,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "videos/cam_high/chunk_index": 0,
                "videos/cam_high/file_index": 3,
            },
        ]
        video_rows = [
            {
                "camera_angle": "cam_high",
                "chunk_index": 0,
                "file_index": 3,
                "relative_path": "videos/cam_high/episode_000003.mp4",
            },
        ]
        base_uri = "hf://datasets/org/repo/data"
        fake_tables = {
            f"{base_uri}/episodes.lance": FakeDataset(episode_rows, list(episode_rows[0].keys())),
            f"{base_uri}/frames.lance": FakeDataset([], ["episode_index"]),
            f"{base_uri}/videos.lance": FakeDataset(video_rows, list(video_rows[0].keys())),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])
        sys.modules["huggingface_hub"] = types.SimpleNamespace(HfFileSystem=FakeHfFileSystem)

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri=base_uri, name="hf-videos"))
        video_source = store.get_video_source(record.dataset_id, 3, "cam_high")
        assert video_source is not None
        chunks = list(video_source.iter_range(3, 8, chunk_size=2))

        self.assertEqual(video_source.size, len(b"hf-remote-video"))
        self.assertEqual(b"".join(chunks), b"remote")
        self.assertEqual(
            FakeHfFileSystem.opened_paths,
            ["datasets/org/repo/data/videos/cam_high/episode_000003.mp4"],
        )

    def test_video_source_streams_fsspec_absolute_file_by_range_when_available(self) -> None:
        fs = FakeObjectStoreFs()
        FakeObjectStoreFs.opened_paths = []
        episode_rows = [
            {
                "episode_index": 3,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
            },
        ]
        video_rows = [
            {
                "episode_index": 3,
                "camera_angle": "cam_high",
                "path": "s3://bucket/videos/cam_high/episode_000003.mp4",
            },
        ]
        fake_tables = {
            "/datasets/object/episodes.lance": FakeDataset(episode_rows, list(episode_rows[0].keys())),
            "/datasets/object/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/object/videos.lance": FakeDataset(video_rows, list(video_rows[0].keys())),
        }
        fsspec_module = types.ModuleType("fsspec")
        fsspec_core = types.ModuleType("fsspec.core")
        fsspec_core.url_to_fs = lambda uri: (fs, uri.removeprefix("s3://"))
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        with patch.dict(sys.modules, {"fsspec": fsspec_module, "fsspec.core": fsspec_core}):
            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri="/datasets/object", name="object-videos"))
            video_source = store.get_video_source(record.dataset_id, 3, "cam_high")
            assert video_source is not None
            chunks = list(video_source.iter_range(7, 11, chunk_size=2))

        self.assertEqual(video_source.size, len(b"object-store-video"))
        self.assertEqual(b"".join(chunks), b"store")
        self.assertEqual(FakeObjectStoreFs.opened_paths, ["bucket/videos/cam_high/episode_000003.mp4"])

    def test_episode_video_columns_take_precedence_over_videos_lance(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 3,
                "fps": 20.0,
                "timestamps": [0.0],
                "cam_high_video_blob": b"episode-table-video",
            },
        ]
        video_rows = [
            {
                "episode_index": 0,
                "camera_angle": "cam_high",
                "video_blob": b"videos-table-video",
            },
        ]
        fake_tables = {
            "/datasets/precedence/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/precedence/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/precedence/videos.lance": FakeDataset(
                video_rows,
                list(video_rows[0].keys()),
            ),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/precedence", name="precedence"))
        video_blob = store.get_video_blob(record.dataset_id, 0, "cam_high")

        self.assertEqual(video_blob, b"episode-table-video")

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

    def test_norm_series_downsamples_long_episodes(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 0,
                "fps": 30.0,
                "timestamps": [frame / 30.0 for frame in range(2000)],
                "actions": [[1.0, 0.0] for _ in range(2000)],
                "observation_state": [[0.0, 1.0] for _ in range(2000)],
            },
        ]
        fake_tables = {
            "/datasets/long/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/long/frames.lance": FakeDataset([], ["episode_index"]),
            "/datasets/long/videos.lance": FakeDataset([], ["camera_angle"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/long", name="long"))
        series = store.get_episode_norm_series(record.dataset_id, 0)

        self.assertIsNotNone(series)
        self.assertEqual(series.frame_count, 2000)
        self.assertLessEqual(series.sample_count, 601)
        self.assertEqual(series.sample_indices[0], 0)
        self.assertEqual(series.sample_indices[-1], 1999)
        self.assertEqual(series.state_values[0], [0.0, 1.0])
        self.assertEqual(series.action_values[0], [1.0, 0.0])

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

    def test_list_frames_prefers_frames_lance_table(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 9,
                "fps": 20.0,
                "timestamps": [0.0, 0.05, 0.1, 0.15],
            },
        ]
        frame_rows = [
            {
                "episode_index": 0,
                "frame_index": 0,
                "timestamp": 0.0,
                "task_index": 9,
                "observation_state": [0.0, 0.0],
                "action": [0.0, 1.0],
            },
            {
                "episode_index": 0,
                "frame_index": 1,
                "timestamp": 0.05,
                "task_index": 9,
                "observation_state": [3.0, 4.0],
                "action": [1.0, 1.0],
            },
            {
                "episode_index": 0,
                "frame_index": 2,
                "timestamp": 0.1,
                "task_index": 9,
                "observation_state": [0.0, 12.0],
                "action": [2.0, 0.0],
                "is_bad_frame": True,
            },
            {
                "episode_index": 1,
                "frame_index": 0,
                "timestamp": 0.0,
                "task_index": 3,
                "observation_state": [99.0],
                "action": [99.0],
            },
        ]
        fake_tables = {
            "/datasets/frames/episodes.lance": FakeDataset(
                episode_rows,
                list(episode_rows[0].keys()),
            ),
            "/datasets/frames/frames.lance": FakeDataset(
                frame_rows,
                [
                    "episode_index",
                    "frame_index",
                    "timestamp",
                    "task_index",
                    "observation_state",
                    "action",
                    "is_bad_frame",
                ],
            ),
            "/datasets/frames/videos.lance": FakeDataset([], ["camera_angle"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/frames", name="frames"))
        frames = store.list_frames(record.dataset_id, 0, start_frame=1, end_frame=2, limit=10)

        self.assertIsNotNone(frames)
        self.assertEqual([frame.frame_index for frame in frames], [1, 2])
        self.assertEqual(frames[0].task_index, 9)
        self.assertEqual(frames[0].state_norm, 5.0)
        self.assertAlmostEqual(frames[0].action_norm or 0.0, 2**0.5)
        self.assertTrue(frames[1].is_bad_frame)

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

    def test_state_action_summary_returns_partial_when_array_fetch_fails(self) -> None:
        episode_rows = [
            {
                "episode_index": 0,
                "task_index": 1,
                "fps": 20.0,
                "timestamps": [0.0, 0.05, 0.1, 0.15, 0.2],
                "actions": [[0.0, 1.0]] * 5,
                "observation_state": [[1.0, 0.0]] * 5,
            },
        ]
        frame_rows = [
            {"episode_index": 0, "frame_index": 0, "observation_state": [0.1, 0.2], "action": [0.3, 0.4]},
        ]
        fake_tables = {
            "/datasets/x/episodes.lance": ArrayFetchFailingDataset(
                episode_rows, list(episode_rows[0].keys())
            ),
            "/datasets/x/frames.lance": FakeDataset(
                frame_rows, list(frame_rows[0].keys())
            ),
            "/datasets/x/videos.lance": FakeDataset([], ["camera_angle", "video_blob"]),
        }
        sys.modules["lance"] = types.SimpleNamespace(dataset=lambda uri: fake_tables[uri])

        store = LanceDatasetStore()
        record = store.open_dataset(DatasetOpenRequest(uri="/datasets/x", name="x"))
        summary = store.get_state_action_summary(record.dataset_id, 0)

        self.assertIsNotNone(summary)
        self.assertEqual(summary.frame_count, 5)
        self.assertEqual(summary.state_dim, 2)
        self.assertEqual(summary.action_dim, 2)
        self.assertIsNone(summary.state_norm_min)
        self.assertIsNone(summary.action_norm_min)

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
