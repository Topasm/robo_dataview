from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.hf_dataset_export import write_hf_dataset_export
from apps.api.services.lerobot_io import write_lerobot_v3_snapshot


RUN_OFFICIAL_EXPORT_TESTS = os.environ.get("RUN_OFFICIAL_EXPORT_TESTS") == "1"


@unittest.skipUnless(
    RUN_OFFICIAL_EXPORT_TESTS,
    "set RUN_OFFICIAL_EXPORT_TESTS=1 to run optional dependency export checks",
)
class OfficialExportDependencyTest(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec("datasets") is None, "datasets is not installed")
    def test_hf_dataset_export_round_trips_with_real_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = write_hf_dataset_export(
                Path(tmpdir),
                dataset_id="official-dependency-test",
                episodes=[
                    EpisodeDetail(
                        dataset_id="official-dependency-test",
                        episode_index=0,
                        task_index=1,
                        length=2,
                        fps=20.0,
                        camera_names=[],
                        language_instruction="Move the object.",
                    )
                ],
                annotations_by_episode={},
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0, 0.05],
                        "states": [[0.0, 1.0], [1.0, 2.0]],
                        "actions": [[0.5], [0.75]],
                    }
                },
                version_description="official dependency test",
            )

            self.assertTrue(artifact["validation"]["metadata_ok"])
            self.assertTrue(artifact["validation"]["loadable"])
            self.assertEqual(artifact["validation"]["load"]["num_rows"], 2)

    @unittest.skipIf(importlib.util.find_spec("datasets") is None, "datasets is not installed")
    @unittest.skipIf(importlib.util.find_spec("lerobot") is None, "lerobot is not installed")
    @unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
    @unittest.skipIf(importlib.util.find_spec("pyarrow") is None, "pyarrow is not installed")
    def test_lerobot_snapshot_loads_with_official_loader_without_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = write_lerobot_v3_snapshot(
                Path(tmpdir),
                dataset_id="official-dependency-test",
                episodes=[
                    EpisodeDetail(
                        dataset_id="official-dependency-test",
                        episode_index=0,
                        task_index=1,
                        length=2,
                        fps=20.0,
                        camera_names=[],
                        language_instruction="Move the object.",
                    )
                ],
                annotations_by_episode={},
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0, 0.05],
                        "states": [[0.0, 1.0], [1.0, 2.0]],
                        "actions": [[0.5], [0.75]],
                    }
                },
                version_description="official dependency test",
            )

            validation = artifact["validation"]

            self.assertTrue(validation["metadata_ok"])
            self.assertTrue(validation["official_loader"]["available"])
            self.assertTrue(validation["official_loader"]["ok"])
            self.assertTrue(validation["lerobot_loadable"])
            self.assertEqual(validation["official_loader"]["length"], 2)

    @unittest.skipIf(importlib.util.find_spec("cv2") is None, "opencv is not installed")
    @unittest.skipIf(importlib.util.find_spec("datasets") is None, "datasets is not installed")
    @unittest.skipIf(importlib.util.find_spec("lerobot") is None, "lerobot is not installed")
    @unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
    @unittest.skipIf(importlib.util.find_spec("pyarrow") is None, "pyarrow is not installed")
    def test_lerobot_snapshot_loads_with_official_loader_with_video(self) -> None:
        video_blob = _make_tiny_mp4(width=16, height=12, fps=20.0, frame_count=2)
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = write_lerobot_v3_snapshot(
                Path(tmpdir),
                dataset_id="official-dependency-test",
                episodes=[
                    EpisodeDetail(
                        dataset_id="official-dependency-test",
                        episode_index=0,
                        task_index=1,
                        length=2,
                        fps=20.0,
                        camera_names=["cam_high"],
                        language_instruction="Move the object.",
                    )
                ],
                annotations_by_episode={},
                timeseries_by_episode={
                    0: {
                        "timestamps": [0.0, 0.05],
                        "states": [[0.0, 1.0], [1.0, 2.0]],
                        "actions": [[0.5], [0.75]],
                    }
                },
                video_blobs_by_episode={0: {"cam_high": video_blob}},
                version_description="official dependency video test",
            )

            validation = artifact["validation"]
            video_status = validation["video_readability"]["videos/cam_high/chunk-000/file-000.mp4"]

            self.assertTrue(validation["metadata_ok"])
            self.assertTrue(video_status["readable"])
            self.assertEqual(video_status["frame_count"], 2)
            self.assertTrue(validation["official_loader"]["available"])
            self.assertTrue(validation["official_loader"]["ok"])
            self.assertTrue(validation["lerobot_loadable"])
            self.assertEqual(validation["official_loader"]["length"], 2)

def _make_tiny_mp4(*, width: int, height: int, fps: float, frame_count: int) -> bytes:
    import cv2
    import numpy as np

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "tiny.mp4"
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise unittest.SkipTest("OpenCV mp4v VideoWriter is unavailable")
        try:
            for index in range(frame_count):
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                frame[:, :, 0] = min(255, index * 80)
                frame[:, :, 1] = 64
                frame[:, :, 2] = 128
                writer.write(frame)
        finally:
            writer.release()
        if not path.exists() or path.stat().st_size == 0:
            raise unittest.SkipTest("OpenCV did not write a valid MP4 file")
        return path.read_bytes()


if __name__ == "__main__":
    unittest.main()
