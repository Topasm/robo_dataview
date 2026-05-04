from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.api.schemas.rerun import RerunSessionCreate
from apps.api.services import rerun_service
from apps.api.services.rerun_service import RerunSessionStore


class FakeRerunModule:
    def __init__(self) -> None:
        self.logged: list[tuple[str, object]] = []
        self.static_logged: list[tuple[str, object]] = []
        self.saved_paths: list[Path] = []
        self.saved_path: Path | None = None

    def init(self, *args: object, **kwargs: object) -> None:
        return None

    def save(self, path: Path) -> None:
        self.saved_path = path
        self.saved_paths.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake rrd")

    def set_time_sequence(self, *args: object, **kwargs: object) -> None:
        return None

    def set_time(self, *args: object, **kwargs: object) -> None:
        return None

    def Scalar(self, value: float) -> float:
        return value

    def AssetVideo(self, *, contents: bytes, media_type: str) -> tuple[str, bytes, str]:
        return ("asset_video", contents, media_type)

    def VideoFrameReference(self, *, seconds: float, video_reference: str) -> tuple[str, float, str]:
        return ("video_frame_reference", seconds, video_reference)

    def log(self, entity_path: str, value: object, **kwargs: object) -> None:
        if kwargs.get("static"):
            self.static_logged.append((entity_path, value))
            return
        self.logged.append((entity_path, value))


class FakeRerunStore:
    def get_episode_timeseries(self, dataset_id: str, episode_index: int) -> dict[str, object] | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        return {
            "timestamps": [0.0, 0.1, 0.2],
            "states": [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
            "actions": [[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]],
        }

    def get_episode(self, dataset_id: str, episode_index: int) -> object | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        return types.SimpleNamespace(fps=10.0, camera_names=["cam high"])

    def get_video_blob(self, dataset_id: str, episode_index: int, camera: str) -> bytes | None:
        if dataset_id == "dataset-a" and episode_index == 3 and camera == "cam high":
            return b"fake mp4"
        return None


class RerunSessionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_rerun = sys.modules.get("rerun")
        self.previous_import_module = rerun_service.import_module
        self.previous_cache_dir = rerun_service.RERUN_CACHE_DIR
        self.cache_dir = Path("/tmp/robot-data-studio-test-rerun")
        rerun_service.RERUN_CACHE_DIR = self.cache_dir

    def tearDown(self) -> None:
        if self.previous_rerun is None:
            sys.modules.pop("rerun", None)
        else:
            sys.modules["rerun"] = self.previous_rerun
        rerun_service.import_module = self.previous_import_module
        rerun_service.RERUN_CACHE_DIR = self.previous_cache_dir
        for path in self.cache_dir.glob("*.rrd"):
            path.unlink()
        if self.cache_dir.exists():
            self.cache_dir.rmdir()

    def test_create_generates_rrd_when_rerun_is_available(self) -> None:
        fake_rerun = FakeRerunModule()
        sys.modules["rerun"] = fake_rerun

        sessions = RerunSessionStore()
        record = sessions.create(
            RerunSessionCreate(dataset_id="sample-xvla-soft-fold", episode_index=0)
        )

        self.assertEqual(record.status, "ready")
        self.assertIsNotNone(record.rrd_path)
        self.assertTrue(Path(record.rrd_path).exists())
        self.assertEqual(sessions.path_for_recording(record.session_id), Path(record.rrd_path))
        self.assertIn(("state/norm", 0.0), fake_rerun.logged)
        self.assertTrue(record.rrd_url.endswith(f"{record.session_id}.rrd"))

    def test_create_logs_camera_video_assets_and_frame_references(self) -> None:
        fake_rerun = FakeRerunModule()
        sys.modules["rerun"] = fake_rerun

        with patch.object(rerun_service, "store", FakeRerunStore()):
            sessions = RerunSessionStore()
            record = sessions.create(RerunSessionCreate(dataset_id="dataset-a", episode_index=3))

        self.assertEqual(record.status, "ready")
        self.assertEqual(record.camera_count, 1)
        self.assertIn(
            ("cameras/cam_high/video_asset", ("asset_video", b"fake mp4", "video/mp4")),
            fake_rerun.static_logged,
        )
        frame_logs = [
            value
            for entity_path, value in fake_rerun.logged
            if entity_path == "cameras/cam_high/frame"
        ]
        self.assertEqual(len(frame_logs), 3)
        self.assertEqual(frame_logs[0], ("video_frame_reference", 0.0, "cameras/cam_high/video_asset"))

    def test_create_reuses_cache_for_same_episode_and_mode(self) -> None:
        fake_rerun = FakeRerunModule()
        sys.modules["rerun"] = fake_rerun

        with patch.object(rerun_service, "store", FakeRerunStore()):
            sessions = RerunSessionStore()
            first = sessions.create(RerunSessionCreate(dataset_id="dataset-a", episode_index=3))
            second = sessions.create(RerunSessionCreate(dataset_id="dataset-a", episode_index=3))

        self.assertEqual(first.status, "ready")
        self.assertEqual(second.status, "ready")
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertEqual(first.rrd_path, second.rrd_path)
        self.assertEqual(len(fake_rerun.saved_paths), 1)

    def test_create_reports_missing_dependency(self) -> None:
        def raise_import_error(name: str) -> object:
            if name == "rerun":
                raise ImportError("missing rerun")
            return self.previous_import_module(name)

        rerun_service.import_module = raise_import_error
        sessions = RerunSessionStore()
        record = sessions.create(
            RerunSessionCreate(dataset_id="sample-xvla-soft-fold", episode_index=0)
        )
        self.assertEqual(record.status, "dependency_missing")
        self.assertEqual(record.message, "Python package 'rerun-sdk>=0.31.4,<0.32' is not installed.")


if __name__ == "__main__":
    unittest.main()
