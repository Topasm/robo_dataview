from __future__ import annotations

import json
import sys
import tempfile
from types import ModuleType
from pathlib import Path
import unittest
from unittest.mock import patch

from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.lerobot_io import (
    read_lerobot_snapshot_summary,
    validate_lerobot_v3_snapshot,
    write_lerobot_v3_snapshot,
)


FAKE_MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


class LeRobotIoTest(unittest.TestCase):
    def test_write_and_read_lerobot_v3_metadata_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            episodes = [
                EpisodeDetail(
                    dataset_id="sample-xvla-soft-fold",
                    episode_index=0,
                    task_index=3,
                    length=12,
                    fps=20.0,
                    camera_names=["cam_high", "cam_left_wrist"],
                    language_instruction="Fold the cloth.",
                ),
                EpisodeDetail(
                    dataset_id="sample-xvla-soft-fold",
                    episode_index=2,
                    task_index=3,
                    length=8,
                    fps=20.0,
                    camera_names=["cam_high"],
                    language_instruction="Fold the cloth.",
                ),
            ]

            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=episodes,
                annotations_by_episode={},
                version_description="unit test",
            )
            summary = read_lerobot_snapshot_summary(Path(artifact["root"]))

            self.assertEqual(artifact["materialization_status"], "metadata_only")
            self.assertTrue(artifact["validation"]["metadata_ok"])
            self.assertEqual(summary["format"], "lerobot_v3_metadata_snapshot")
            self.assertEqual(summary["total_episodes"], 2)
            self.assertEqual(summary["episode_indices"], [0, 1])
            self.assertTrue(Path(artifact["files"]["stats"]).exists())
            self.assertTrue(Path(artifact["files"]["tasks_jsonl"]).exists())
            self.assertTrue(Path(artifact["files"]["episodes_jsonl"]).exists())
            self.assertTrue(Path(artifact["files"]["data_index"]).exists())
            self.assertTrue(Path(artifact["files"]["validation"]).exists())

            validation = validate_lerobot_v3_snapshot(Path(artifact["root"]))

            self.assertTrue(validation["metadata_ok"])
            self.assertFalse(validation["lerobot_loadable"])
            self.assertIn("official_loader", validation)
            self.assertEqual(validation["episode_count"], 2)
            self.assertEqual(validation["frame_count"], 20)

    def test_write_lerobot_v3_snapshot_materializes_frames_and_videos(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            episodes = [
                EpisodeDetail(
                    dataset_id="sample-xvla-soft-fold",
                    episode_index=0,
                    task_index=3,
                    length=3,
                    fps=20.0,
                    camera_names=["cam high"],
                    language_instruction="Fold the cloth.",
                ),
            ]

            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=episodes,
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0, 0.05, 0.1],
                        "states": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
                        "actions": [[0.0, 1.0], [0.0, 2.0], [3.0, 4.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam high": FAKE_MP4_BYTES}},
            )
            root = Path(artifact["root"])
            validation = validate_lerobot_v3_snapshot(root)

            self.assertIn(artifact["materialization_status"], {"data_jsonl_mp4", "parquet_mp4"})
            self.assertEqual(artifact["materialized"]["frame_rows"], 3)
            self.assertEqual(artifact["materialized"]["video_files"], 1)
            self.assertEqual(validation["materialized_frame_count"], 3)
            self.assertEqual(validation["materialized_video_count"], 1)
            self.assertTrue(Path(artifact["files"]["data_jsonl"]).exists())
            self.assertTrue(Path(artifact["files"]["video_index"]).exists())
            self.assertTrue((root / "videos/cam_high/chunk-000/file-000.mp4").exists())
            info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
            self.assertEqual(info["features"]["observation.state"]["shape"], [2])
            self.assertEqual(info["features"]["action"]["shape"], [2])
            self.assertEqual(info["features"]["timestamp"]["shape"], [1])
            self.assertEqual(info["features"]["index"]["shape"], [1])
            self.assertEqual(info["features"]["cam_high"]["dtype"], "video")
            self.assertEqual(info["total_frames"], 3)
            stats = json.loads((root / "meta/stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["observation.state"]["min"], [0.0, 0.0])
            self.assertEqual(stats["observation.state"]["max"], [1.0, 1.0])
            self.assertEqual(stats["observation.state"]["count"], [3, 3])
            self.assertEqual(stats["action"]["max"], [3.0, 4.0])
            data_rows = [
                json.loads(line)
                for line in (root / "data/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual([row["index"] for row in data_rows], [0, 1, 2])
            self.assertEqual({row["episode_index"] for row in data_rows}, {0})
            self.assertEqual({row["source_episode_index"] for row in data_rows}, {0})
            self.assertEqual({row["task_index"] for row in data_rows}, {0})
            self.assertEqual({row["source_task_index"] for row in data_rows}, {3})
            self.assertEqual(
                data_rows[0]["cam_high"],
                {
                    "path": "videos/cam_high/chunk-000/file-000.mp4",
                    "timestamp": 0.0,
                },
            )
            self.assertEqual(data_rows[2]["cam_high"]["timestamp"], 0.1)
            episode_rows = [
                json.loads(line)
                for line in (root / "meta/episodes/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(episode_rows[0]["episode_index"], 0)
            self.assertEqual(episode_rows[0]["source_episode_index"], 0)
            self.assertEqual(episode_rows[0]["meta/episodes/chunk_index"], 0)
            self.assertEqual(episode_rows[0]["meta/episodes/file_index"], 0)
            self.assertEqual(episode_rows[0]["tasks"], ["Fold the cloth."])
            self.assertEqual(episode_rows[0]["task_index"], 0)
            self.assertEqual(episode_rows[0]["source_task_index"], 3)
            self.assertEqual(episode_rows[0]["dataset_from_index"], 0)
            self.assertEqual(episode_rows[0]["dataset_to_index"], 3)
            self.assertEqual(episode_rows[0]["data/chunk_index"], 0)
            self.assertEqual(episode_rows[0]["data/file_index"], 0)
            self.assertEqual(episode_rows[0]["videos/cam_high/chunk_index"], 0)
            self.assertEqual(episode_rows[0]["videos/cam_high/file_index"], 0)
            self.assertEqual(episode_rows[0]["videos/cam_high/from_timestamp"], 0.0)
            self.assertEqual(episode_rows[0]["videos/cam_high/to_timestamp"], 0.15)

    def test_lerobot_snapshot_offsets_follow_materialized_frame_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=5,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=[],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    5: {
                        "timestamps": [0.0, 0.05],
                        "states": [[0.0], [1.0]],
                        "actions": [[2.0], [3.0]],
                    }
                },
            )
            root = Path(artifact["root"])

            info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
            episode_rows = [
                json.loads(line)
                for line in (root / "meta/episodes/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            data_index_rows = [
                json.loads(line)
                for line in (root / "data/chunk-000/file-000.index.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            data_rows = [
                json.loads(line)
                for line in (root / "data/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            validation = validate_lerobot_v3_snapshot(root)

            self.assertEqual(info["total_frames"], 2)
            self.assertEqual(episode_rows[0]["length"], 2)
            self.assertEqual(episode_rows[0]["dataset_to_index"], 2)
            self.assertEqual(data_index_rows[0]["data_end_idx"], 2)
            self.assertEqual(len(data_rows), 2)
            self.assertTrue(validation["metadata_ok"])

    def test_lerobot_data_parquet_excludes_video_reference_columns(self) -> None:
        written_tables: dict[str, list[dict]] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            with patch.dict(
                sys.modules,
                {
                    **_fake_pyarrow_write_modules(written_tables),
                    "pandas": None,
                },
            ):
                artifact = write_lerobot_v3_snapshot(
                    export_dir,
                    dataset_id="sample-xvla-soft-fold",
                    episodes=[
                        EpisodeDetail(
                            dataset_id="sample-xvla-soft-fold",
                            episode_index=0,
                            task_index=3,
                            length=1,
                            fps=20.0,
                            camera_names=["cam high"],
                        )
                    ],
                    annotations_by_episode={},
                    version_description="unit test",
                    timeseries_by_episode={
                        0: {
                            "timestamps": [0.0],
                            "states": [[0.0]],
                            "actions": [[1.0]],
                        }
                    },
                    video_blobs_by_episode={0: {"cam high": FAKE_MP4_BYTES}},
                )

            root = Path(artifact["root"])
            data_parquet_path = (root / "data/chunk-000/file-000.parquet").as_posix()
            data_jsonl_rows = [
                json.loads(line)
                for line in (root / "data/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

            self.assertTrue(Path(artifact["files"]["data"]).exists())
            self.assertIn("cam_high", data_jsonl_rows[0])
            self.assertNotIn("cam_high", written_tables[data_parquet_path][0])

    def test_lerobot_data_parquet_uses_hf_dataset_features_when_available(self) -> None:
        written_datasets: dict[str, dict] = {}
        written_tables: dict[str, list[dict]] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            with patch.dict(
                sys.modules,
                {
                    **_fake_pyarrow_write_modules(written_tables),
                    "datasets": _fake_hf_datasets_write_module(written_datasets),
                    "pandas": None,
                },
            ):
                artifact = write_lerobot_v3_snapshot(
                    export_dir,
                    dataset_id="sample-xvla-soft-fold",
                    episodes=[
                        EpisodeDetail(
                            dataset_id="sample-xvla-soft-fold",
                            episode_index=0,
                            task_index=3,
                            length=1,
                            fps=20.0,
                            camera_names=["cam high"],
                        )
                    ],
                    annotations_by_episode={},
                    version_description="unit test",
                    timeseries_by_episode={
                        0: {
                            "timestamps": [0.0],
                            "states": [[0.0, 1.0]],
                            "actions": [[2.0]],
                        }
                    },
                    video_blobs_by_episode={0: {"cam high": FAKE_MP4_BYTES}},
                )

            data_parquet_path = Path(artifact["files"]["data"] or "").as_posix()
            dataset_payload = written_datasets[data_parquet_path]

            self.assertEqual(dataset_payload["split"], "train")
            self.assertIn("observation.state", dataset_payload["features"])
            self.assertIn("action", dataset_payload["features"])
            self.assertNotIn("cam_high", dataset_payload["features"])
            self.assertNotIn("cam_high", dataset_payload["columns"])
            self.assertEqual(dataset_payload["columns"]["episode_index"], [0])

    def test_validate_lerobot_snapshot_rejects_total_frame_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=2,
                        fps=20.0,
                        camera_names=[],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0, 0.05],
                        "states": [[0.0], [1.0]],
                        "actions": [[2.0], [3.0]],
                    }
                },
            )
            root = Path(artifact["root"])
            info_path = root / "meta/info.json"
            info = json.loads(info_path.read_text(encoding="utf-8"))
            info["total_frames"] = 1
            info_path.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8")

            validation = validate_lerobot_v3_snapshot(root)

            self.assertFalse(validation["metadata_ok"])
            self.assertIn(
                "total_frames does not match episode metadata frame count",
                validation["errors"],
            )
            self.assertIn(
                "total_frames does not match materialized frame row count",
                validation["errors"],
            )

    def test_validate_lerobot_snapshot_rejects_invalid_mp4_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=["cam_high"],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0],
                        "states": [[0.0, 0.0]],
                        "actions": [[1.0, 1.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": b"not an mp4"}},
            )

            validation = validate_lerobot_v3_snapshot(Path(artifact["root"]))

            self.assertFalse(validation["metadata_ok"])
            self.assertFalse(validation["local_lerobot_loadable_heuristic"])
            self.assertTrue(
                any("invalid MP4 files" in error for error in validation["errors"])
            )

    def test_validate_lerobot_snapshot_records_official_loader_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=[],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
            )
            with patch.dict(sys.modules, _fake_lerobot_modules(_FakeLeRobotDataset)):
                validation = validate_lerobot_v3_snapshot(Path(artifact["root"]))

            self.assertTrue(validation["official_loader"]["available"])
            self.assertTrue(validation["official_loader"]["ok"])
            self.assertTrue(validation["lerobot_loadable"])
            self.assertEqual(validation["loadability_basis"], "official_loader")
            self.assertEqual(validation["official_loader"]["length"], 7)
            self.assertEqual(validation["official_loader"]["repo_id"], "local/sample-xvla-soft-fold")

    def test_validate_lerobot_snapshot_records_official_loader_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=[],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
            )
            with patch.dict(sys.modules, _fake_lerobot_modules(_FailingLeRobotDataset)):
                validation = validate_lerobot_v3_snapshot(Path(artifact["root"]))

            self.assertTrue(validation["official_loader"]["available"])
            self.assertFalse(validation["official_loader"]["ok"])
            self.assertFalse(validation["lerobot_loadable"])
            self.assertEqual(validation["loadability_basis"], "official_loader")
            self.assertIn("RuntimeError: cannot load", validation["official_loader"]["error"])

    def test_validate_lerobot_snapshot_accepts_complete_local_shard_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=["cam_high"],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0],
                        "states": [[0.0, 0.0]],
                        "actions": [[1.0, 1.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": FAKE_MP4_BYTES}},
            )
            root = Path(artifact["root"])
            (root / "meta/tasks.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )
            (root / "meta/episodes/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )
            (root / "data/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )

            with patch.dict(
                sys.modules,
                {
                    **_fake_pyarrow_modules(),
                    "lerobot": None,
                    "lerobot.datasets": None,
                    "lerobot.datasets.lerobot_dataset": None,
                },
            ):
                validation = validate_lerobot_v3_snapshot(root)

            self.assertTrue(validation["present"]["data_parquet"])
            self.assertTrue(validation["parquet_readability"]["tasks_parquet"]["readable"])
            self.assertTrue(validation["parquet_readability"]["episodes_parquet"]["readable"])
            self.assertTrue(validation["parquet_readability"]["data_parquet"]["readable"])
            self.assertTrue(validation["metadata_ok"])
            self.assertTrue(validation["local_lerobot_loadable_heuristic"])
            self.assertFalse(validation["lerobot_loadable"])
            self.assertEqual(validation["loadability_basis"], "local_heuristic_unverified")

    def test_validate_lerobot_snapshot_rejects_unreadable_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=["cam_high"],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0],
                        "states": [[0.0, 0.0]],
                        "actions": [[1.0, 1.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": FAKE_MP4_BYTES}},
            )
            root = Path(artifact["root"])
            (root / "meta/tasks.parquet").write_text("placeholder", encoding="utf-8")
            (root / "meta/episodes/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )
            (root / "data/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )

            with patch.dict(sys.modules, _fake_pyarrow_modules(error=ValueError("bad magic"))):
                validation = validate_lerobot_v3_snapshot(root)

            self.assertFalse(validation["metadata_ok"])
            self.assertFalse(validation["local_lerobot_loadable_heuristic"])
            self.assertFalse(validation["parquet_readability"]["data_parquet"]["readable"])
            self.assertTrue(
                any("not readable as Parquet" in error for error in validation["errors"])
            )

    def test_validate_lerobot_snapshot_rejects_wrong_parquet_row_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=["cam_high"],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0],
                        "states": [[0.0, 0.0]],
                        "actions": [[1.0, 1.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": FAKE_MP4_BYTES}},
            )
            root = Path(artifact["root"])
            (root / "meta/tasks.parquet").write_text("placeholder", encoding="utf-8")
            (root / "meta/episodes/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )
            (root / "data/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )

            with patch.dict(
                sys.modules,
                _fake_pyarrow_modules(row_count_overrides={"data_parquet": 2}),
            ):
                validation = validate_lerobot_v3_snapshot(root)

            self.assertFalse(validation["metadata_ok"])
            self.assertFalse(validation["local_lerobot_loadable_heuristic"])
            self.assertTrue(
                any("row count 2 does not match expected 1" in error for error in validation["errors"])
            )

    def test_validate_lerobot_snapshot_requires_video_shard_metadata_for_local_loadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=["cam_high"],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0],
                        "states": [[0.0, 0.0]],
                        "actions": [[1.0, 1.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": FAKE_MP4_BYTES}},
            )
            root = Path(artifact["root"])
            episodes_parquet_path = root / "meta/episodes/chunk-000/file-000.parquet"
            if episodes_parquet_path.exists():
                episodes_parquet_path.unlink()
            episodes_path = root / "meta/episodes/chunk-000/file-000.jsonl"
            rows = [
                json.loads(line)
                for line in episodes_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            rows[0].pop("videos/cam_high/chunk_index")
            episodes_path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            (root / "data/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )

            validation = validate_lerobot_v3_snapshot(root)

            self.assertTrue(validation["present"]["data_parquet"])
            self.assertTrue(validation["metadata_ok"])
            self.assertFalse(validation["local_lerobot_loadable_heuristic"])

    def test_validate_lerobot_snapshot_requires_frame_video_references_for_local_loadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)
            artifact = write_lerobot_v3_snapshot(
                export_dir,
                dataset_id="sample-xvla-soft-fold",
                episodes=[
                    EpisodeDetail(
                        dataset_id="sample-xvla-soft-fold",
                        episode_index=0,
                        task_index=3,
                        length=1,
                        fps=20.0,
                        camera_names=["cam_high"],
                    )
                ],
                annotations_by_episode={},
                version_description="unit test",
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0],
                        "states": [[0.0, 0.0]],
                        "actions": [[1.0, 1.0]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": FAKE_MP4_BYTES}},
            )
            root = Path(artifact["root"])
            rows = [
                json.loads(line)
                for line in (root / "data/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            rows[0].pop("cam_high")
            (root / "data/chunk-000/file-000.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            (root / "meta/tasks.parquet").write_text("placeholder", encoding="utf-8")
            (root / "meta/episodes/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )
            (root / "data/chunk-000/file-000.parquet").write_text(
                "placeholder",
                encoding="utf-8",
            )

            validation = validate_lerobot_v3_snapshot(root)

            self.assertFalse(validation["metadata_ok"])
            self.assertFalse(validation["local_lerobot_loadable_heuristic"])
            self.assertIn(
                "frame rows must include valid video feature references",
                validation["errors"],
            )


class _FakeLeRobotDataset:
    def __init__(self, repo_id: str, root: Path) -> None:
        self.repo_id = repo_id
        self.root = root

    def __len__(self) -> int:
        return 7


class _FailingLeRobotDataset:
    def __init__(self, repo_id: str, root: Path) -> None:
        del repo_id, root
        raise RuntimeError("cannot load")


def _fake_lerobot_modules(dataset_class: type) -> dict[str, ModuleType]:
    lerobot_module = ModuleType("lerobot")
    datasets_module = ModuleType("lerobot.datasets")
    datasets_module.LeRobotDataset = dataset_class
    return {
        "lerobot": lerobot_module,
        "lerobot.datasets": datasets_module,
    }


class _FakeParquetTable:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.num_rows = len(rows)

    def to_pylist(self) -> list[dict]:
        return self._rows


def _fake_pyarrow_modules(
    error: Exception | None = None,
    row_count_overrides: dict[str, int] | None = None,
) -> dict[str, ModuleType]:
    pyarrow_module = ModuleType("pyarrow")
    parquet_module = ModuleType("pyarrow.parquet")
    row_count_overrides = row_count_overrides or {}

    def read_table(path: Path) -> _FakeParquetTable:
        if error is not None:
            raise error
        key = _fake_parquet_key(Path(path))
        if key in row_count_overrides:
            return _FakeParquetTable(
                [{"index": index} for index in range(int(row_count_overrides[key]))]
            )
        return _FakeParquetTable(_jsonl_rows_for_fake_parquet(Path(path)))

    parquet_module.read_table = read_table  # type: ignore[attr-defined]
    pyarrow_module.parquet = parquet_module  # type: ignore[attr-defined]
    return {
        "pyarrow": pyarrow_module,
        "pyarrow.parquet": parquet_module,
    }


def _fake_pyarrow_write_modules(written_tables: dict[str, list[dict]]) -> dict[str, ModuleType]:
    pyarrow_module = ModuleType("pyarrow")
    parquet_module = ModuleType("pyarrow.parquet")

    class Table:
        @staticmethod
        def from_pylist(rows: list[dict]) -> _FakeParquetTable:
            return _FakeParquetTable(rows)

    def write_table(table: _FakeParquetTable, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fake parquet", encoding="utf-8")
        written_tables[path.as_posix()] = table.to_pylist()

    def read_table(path: Path) -> _FakeParquetTable:
        rows = written_tables.get(path.as_posix(), _jsonl_rows_for_fake_parquet(Path(path)))
        return _FakeParquetTable(rows)

    pyarrow_module.Table = Table  # type: ignore[attr-defined]
    pyarrow_module.parquet = parquet_module  # type: ignore[attr-defined]
    parquet_module.write_table = write_table  # type: ignore[attr-defined]
    parquet_module.read_table = read_table  # type: ignore[attr-defined]
    return {
        "pyarrow": pyarrow_module,
        "pyarrow.parquet": parquet_module,
    }


def _fake_hf_datasets_write_module(written_datasets: dict[str, dict]) -> ModuleType:
    module = ModuleType("datasets")

    class Dataset:
        def __init__(self, columns: dict[str, list], features: dict, split: str | None) -> None:
            self.columns = columns
            self.features = features
            self.split = split

        @classmethod
        def from_dict(
            cls,
            columns: dict[str, list],
            *,
            features: dict,
            split: str | None = None,
        ) -> "Dataset":
            return cls(columns, features, split)

        def to_parquet(self, path: str) -> None:
            path_obj = Path(path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text("fake hf dataset parquet", encoding="utf-8")
            written_datasets[path_obj.as_posix()] = {
                "columns": self.columns,
                "features": self.features,
                "split": self.split,
            }

    module.Dataset = Dataset
    module.Features = lambda features: features  # type: ignore[attr-defined]
    module.Value = lambda dtype: {"kind": "Value", "dtype": dtype}  # type: ignore[attr-defined]
    module.Sequence = lambda *, length, feature: {  # type: ignore[attr-defined]
        "kind": "Sequence",
        "length": length,
        "feature": feature,
    }
    module.Image = lambda: {"kind": "Image"}  # type: ignore[attr-defined]
    module.Array2D = lambda *, shape, dtype: {  # type: ignore[attr-defined]
        "kind": "Array2D",
        "shape": shape,
        "dtype": dtype,
    }
    module.Array3D = lambda *, shape, dtype: {  # type: ignore[attr-defined]
        "kind": "Array3D",
        "shape": shape,
        "dtype": dtype,
    }
    module.Array4D = lambda *, shape, dtype: {  # type: ignore[attr-defined]
        "kind": "Array4D",
        "shape": shape,
        "dtype": dtype,
    }
    module.Array5D = lambda *, shape, dtype: {  # type: ignore[attr-defined]
        "kind": "Array5D",
        "shape": shape,
        "dtype": dtype,
    }
    return module


def _fake_parquet_key(path: Path) -> str:
    if path.name == "tasks.parquet":
        return "tasks_parquet"
    if path.name == "file-000.parquet" and path.parent.name == "chunk-000":
        if path.parent.parent.name == "episodes":
            return "episodes_parquet"
        if path.parent.parent.name == "data":
            return "data_parquet"
    return path.name


def _jsonl_rows_for_fake_parquet(path: Path) -> list[dict]:
    if path.name == "tasks.parquet":
        jsonl_path = path.with_name("tasks.jsonl")
    else:
        jsonl_path = path.with_suffix(".jsonl")
    if not jsonl_path.exists():
        return [{"index": 0}]
    return [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    unittest.main()
