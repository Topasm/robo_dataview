from __future__ import annotations

import sys
import unittest
from pathlib import Path

from apps.api.schemas.rerun import RerunSessionCreate
from apps.api.services import rerun_service
from apps.api.services.rerun_service import RerunSessionStore


class FakeRerunModule:
    def __init__(self) -> None:
        self.logged: list[tuple[str, object]] = []
        self.saved_path: Path | None = None

    def init(self, *args: object, **kwargs: object) -> None:
        return None

    def save(self, path: Path) -> None:
        self.saved_path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake rrd")

    def set_time_sequence(self, *args: object, **kwargs: object) -> None:
        return None

    def set_time(self, *args: object, **kwargs: object) -> None:
        return None

    def Scalar(self, value: float) -> float:
        return value

    def log(self, entity_path: str, value: object) -> None:
        self.logged.append((entity_path, value))


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
