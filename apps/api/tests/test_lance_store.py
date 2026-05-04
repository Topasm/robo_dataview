from __future__ import annotations

import sys
import types
import unittest

from apps.api.schemas.datasets import DatasetOpenRequest
from apps.api.services.lance_store import LanceDatasetStore


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


if __name__ == "__main__":
    unittest.main()
