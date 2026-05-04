from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.lance_store import VideoSource
from workers.keyframe_extractor import KeyframeArtifact
from workers.visual_embedding_worker import (
    VisualEmbeddingConfig,
    build_visual_embedding_records,
)


class VisualEmbeddingWorkerTest(unittest.TestCase):
    def test_build_visual_embedding_records_uses_video_source_keyframes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            publish_root = root / "published"
            video_path = root / "episode.mp4"
            video_path.write_bytes(b"fake-video")
            image_path = root / "cam_high_frame_000000.jpg"

            def fake_extract(*, path, camera, frame_indices, output_dir):
                self.assertEqual(path, video_path)
                self.assertEqual(camera, "cam_high")
                self.assertEqual(frame_indices, [0, 2])
                output_dir.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(b"fake-jpeg")
                return [
                    KeyframeArtifact(
                        camera=camera,
                        frame_index=0,
                        uri=str(image_path),
                        width=32,
                        height=24,
                    )
                ]

            with (
                patch.dict(
                    os.environ,
                    {"ROBOT_DATA_STUDIO_KEYFRAME_CACHE_PUBLISH_URI": str(publish_root)},
                    clear=False,
                ),
                patch(
                    "workers.visual_embedding_worker.extract_keyframes_from_path",
                    side_effect=fake_extract,
                ),
            ):
                result = build_visual_embedding_records(
                    dataset_store=FakeVisualStore(video_path),
                    dataset_id="dataset-a",
                    episode_indices=[3],
                    config=VisualEmbeddingConfig(
                        model="fake-vision",
                        camera_names=("cam_high",),
                        min_keyframes=2,
                        max_keyframes=2,
                    ),
                    provider=FakeVisualProvider(),
                    cache_root=root / "cache",
                )

            self.assertEqual(result.provider, "fake-vision-provider")
            self.assertEqual(result.artifact_count, 1)
            self.assertEqual(result.skipped, [])
            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.episode_index, 3)
            self.assertEqual(record.frame_index, 0)
            self.assertEqual(record.modality, "image")
            self.assertEqual(record.camera, "cam_high")
            self.assertEqual(record.source_uri, str(publish_root / "keyframes/cam_high_frame_000000.jpg"))
            self.assertEqual(record.source_model, "fake-vision-provider")
            self.assertIsNotNone(record.content_hash)
            self.assertEqual(Path(record.source_uri).read_bytes(), b"fake-jpeg")
            self.assertAlmostEqual(sum(value * value for value in record.embedding), 1.0)


class FakeVisualStore:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path

    def list_episodes(self, dataset_id: str, limit: int, offset: int):
        del dataset_id, limit, offset
        return [self.get_episode("dataset-a", 3)]

    def get_episode(self, dataset_id: str, episode_index: int):
        del dataset_id
        if episode_index != 3:
            return None
        return EpisodeDetail(
            dataset_id="dataset-a",
            episode_index=3,
            task_index=1,
            length=3,
            fps=20,
            camera_names=["cam_high"],
            duration_seconds=0.15,
        )

    def get_video_source(self, dataset_id: str, episode_index: int, camera: str):
        del dataset_id
        if episode_index == 3 and camera == "cam_high":
            return VideoSource(size=self.video_path.stat().st_size, path=self.video_path)
        return None


class FakeVisualProvider:
    source_model = "fake-vision-provider"

    def embed_images(self, image_paths: list[Path]) -> list[list[float]]:
        return [[3.0, 4.0] for _ in image_paths]


if __name__ == "__main__":
    unittest.main()
