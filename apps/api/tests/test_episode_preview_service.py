from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from apps.api.services.episode_preview_service import EpisodePreviewService
from apps.api.services.lance_store import VideoSource


class FakePreviewStore:
    def __init__(self, source: VideoSource | None) -> None:
        self.source = source

    def get_video_source(self, dataset_id: str, episode_index: int, camera: str) -> VideoSource | None:
        if dataset_id != "dataset-a" or episode_index != 3 or camera != "cam_high":
            return None
        return self.source


class FakeCapture:
    opened_paths: list[str] = []
    seek_frames: list[int] = []

    def __init__(self, path: str) -> None:
        self.path = path
        self.opened_paths.append(path)

    def isOpened(self) -> bool:
        return True

    def set(self, prop: int, value: int) -> None:
        if prop == 1:
            self.seek_frames.append(value)

    def read(self) -> tuple[bool, object]:
        return True, types.SimpleNamespace(shape=(24, 32, 3))

    def release(self) -> None:
        pass


class EpisodePreviewServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_cv2 = sys.modules.get("cv2")
        FakeCapture.opened_paths = []
        FakeCapture.seek_frames = []
        sys.modules["cv2"] = types.SimpleNamespace(
            CAP_PROP_POS_FRAMES=1,
            IMWRITE_JPEG_QUALITY=2,
            VideoCapture=FakeCapture,
            imwrite=_fake_imwrite,
        )

    def tearDown(self) -> None:
        if self.previous_cv2 is None:
            sys.modules.pop("cv2", None)
        else:
            sys.modules["cv2"] = self.previous_cv2

    def test_preview_cache_decodes_file_source_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_root = Path(tmpdir) / "cache"
            video_path = Path(tmpdir) / "episode.mp4"
            video_path.write_bytes(b"fake-video")
            service = EpisodePreviewService(cache_root=cache_root)

            with patch(
                "apps.api.services.episode_preview_service.store",
                FakePreviewStore(VideoSource(size=video_path.stat().st_size, path=video_path)),
            ):
                first = service.get_or_create_preview(
                    dataset_id="dataset-a",
                    episode_index=3,
                    camera="cam_high",
                    frame_index=4,
                )
                second = service.get_or_create_preview(
                    dataset_id="dataset-a",
                    episode_index=3,
                    camera="cam_high",
                    frame_index=4,
                )

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(first.path, second.path)
            self.assertEqual(first.path.read_bytes(), b"fake-jpeg")
            self.assertEqual(first.content_type, "image/jpeg")
            self.assertEqual(first.frame_index, 4)
            self.assertEqual(FakeCapture.opened_paths, [str(video_path)])
            self.assertEqual(FakeCapture.seek_frames, [4])

    def test_preview_cache_can_publish_generated_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cache_root = root / "cache"
            publish_root = root / "published"
            video_path = root / "episode.mp4"
            video_path.write_bytes(b"fake-video")
            service = EpisodePreviewService(cache_root=cache_root)

            with (
                patch.dict(
                    os.environ,
                    {"ROBOT_DATA_STUDIO_PREVIEW_CACHE_PUBLISH_URI": str(publish_root)},
                    clear=False,
                ),
                patch(
                    "apps.api.services.episode_preview_service.store",
                    FakePreviewStore(VideoSource(size=video_path.stat().st_size, path=video_path)),
                ),
            ):
                preview = service.get_or_create_preview(
                    dataset_id="dataset-a",
                    episode_index=3,
                    camera="cam_high",
                    frame_index=4,
                )

            self.assertIsNotNone(preview)
            self.assertEqual(preview.published_uri, str(publish_root / "previews" / preview.path.name))
            self.assertEqual(preview.publish_size_bytes, len(b"fake-jpeg"))
            self.assertIsNone(preview.publish_error)
            self.assertEqual(Path(preview.published_uri or "").read_bytes(), b"fake-jpeg")

    def test_preview_cache_returns_none_when_video_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = EpisodePreviewService(cache_root=Path(tmpdir) / "cache")
            with patch("apps.api.services.episode_preview_service.store", FakePreviewStore(None)):
                preview = service.get_or_create_preview(
                    dataset_id="dataset-a",
                    episode_index=3,
                    camera="cam_high",
                )

        self.assertIsNone(preview)


def _fake_imwrite(path: str, _frame: object, _params: list[int]) -> bool:
    Path(path).write_bytes(b"fake-jpeg")
    return True


if __name__ == "__main__":
    unittest.main()
