from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
import unittest

from apps.api.schemas.datasets import DatasetOpenRequest
from apps.api.schemas.episodes import EpisodeDetail
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


class LanceDatasetStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_lance = sys.modules.get("lance")

    def tearDown(self) -> None:
        if self.previous_lance is None:
            sys.modules.pop("lance", None)
        else:
            sys.modules["lance"] = self.previous_lance

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
            self.assertEqual(record.message, "LeRobot v3 metadata snapshot indexed.")
            self.assertIsNotNone(summary)
            self.assertEqual(summary.episode_count, 1)
            self.assertEqual(summary.frame_count, 30)
            self.assertEqual(summary.camera_names, ["cam_high"])
            self.assertEqual(episodes[0].episode_index, 7)
            self.assertEqual(episodes[0].task_index, 4)

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


if __name__ == "__main__":
    unittest.main()
