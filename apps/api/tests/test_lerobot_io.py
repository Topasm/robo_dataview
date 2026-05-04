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
            self.assertEqual(summary["episode_indices"], [0, 2])
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
                video_blobs_by_episode={0: {"cam high": b"fake mp4"}},
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
            stats = json.loads((root / "meta/stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["features"]["observation.state"]["min"], [0.0, 0.0])
            self.assertEqual(stats["features"]["observation.state"]["max"], [1.0, 1.0])
            self.assertEqual(stats["features"]["action"]["max"], [3.0, 4.0])
            episode_rows = [
                json.loads(line)
                for line in (root / "meta/episodes/chunk-000/file-000.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(episode_rows[0]["data/chunk_index"], 0)
            self.assertEqual(episode_rows[0]["data/file_index"], 0)
            self.assertEqual(episode_rows[0]["videos/cam_high/chunk_index"], 0)
            self.assertEqual(episode_rows[0]["videos/cam_high/file_index"], 0)

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
            self.assertIn("RuntimeError: cannot load", validation["official_loader"]["error"])


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


if __name__ == "__main__":
    unittest.main()
