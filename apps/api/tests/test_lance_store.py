from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
import unittest

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
            video_blob = store.get_video_blob(record.dataset_id, 3, "cam_high")

        self.assertEqual(video_blob, b"file-video")

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


if __name__ == "__main__":
    unittest.main()
