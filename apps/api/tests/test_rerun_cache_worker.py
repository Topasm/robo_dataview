from __future__ import annotations

from pathlib import Path
import tempfile
import types
import unittest

from apps.api.schemas.rerun import RerunSessionRecord
from workers.rerun_cache_worker import generate_rerun_recording


class FakeRerunModule:
    def __init__(self) -> None:
        self.logged: list[tuple[str, object]] = []
        self.static_logged: list[tuple[str, object]] = []

    def init(self, *args: object, **kwargs: object) -> None:
        return None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake rrd")

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


class FakeDatasetStore:
    def get_episode_timeseries(self, dataset_id: str, episode_index: int) -> dict[str, object] | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        return {
            "timestamps": [0.0, 0.1],
            "states": [[3.0, 4.0], [0.0, 0.0]],
            "actions": [[0.0, 1.0], [0.0, 2.0]],
        }

    def get_episode(self, dataset_id: str, episode_index: int) -> object | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        return types.SimpleNamespace(fps=10.0, camera_names=["cam high"])

    def get_video_blob(self, dataset_id: str, episode_index: int, camera: str) -> bytes | None:
        if dataset_id == "dataset-a" and episode_index == 3 and camera == "cam high":
            return b"fake mp4"
        return None


class RerunCacheWorkerTest(unittest.TestCase):
    def test_generate_rerun_recording_logs_scalars_and_camera_assets(self) -> None:
        fake_rerun = FakeRerunModule()
        record = _record()
        with tempfile.TemporaryDirectory() as tmpdir:
            rrd_path = Path(tmpdir) / "episode.rrd"
            updated = generate_rerun_recording(
                record,
                rrd_path,
                dataset_store=FakeDatasetStore(),
                import_module_fn=lambda _name: fake_rerun,
            )

        self.assertEqual(updated.status, "ready")
        self.assertFalse(updated.cache_hit)
        self.assertEqual(updated.camera_count, 1)
        self.assertIn(("state/norm", 5.0), fake_rerun.logged)
        self.assertIn(
            ("cameras/cam_high/video_asset", ("asset_video", b"fake mp4", "video/mp4")),
            fake_rerun.static_logged,
        )

    def test_generate_rerun_recording_reports_cache_hit(self) -> None:
        record = _record()
        with tempfile.TemporaryDirectory() as tmpdir:
            rrd_path = Path(tmpdir) / "episode.rrd"
            rrd_path.write_bytes(b"cached")
            updated = generate_rerun_recording(
                record,
                rrd_path,
                dataset_store=FakeDatasetStore(),
                import_module_fn=lambda _name: FakeRerunModule(),
            )

        self.assertEqual(updated.status, "ready")
        self.assertTrue(updated.cache_hit)
        self.assertEqual(updated.message, "Loaded cached Rerun recording.")

    def test_generate_rerun_recording_reports_missing_episode(self) -> None:
        updated = generate_rerun_recording(
            _record(dataset_id="missing"),
            Path("/tmp/missing.rrd"),
            dataset_store=FakeDatasetStore(),
            import_module_fn=lambda _name: FakeRerunModule(),
        )

        self.assertEqual(updated.status, "episode_not_found")


def _record(dataset_id: str = "dataset-a") -> RerunSessionRecord:
    return RerunSessionRecord(
        session_id="session-a",
        dataset_id=dataset_id,
        episode_index=3,
        mode="rrd_cache",
        status="pending",
        cache_key="cache-a",
        rrd_path="/tmp/episode.rrd",
    )


if __name__ == "__main__":
    unittest.main()
