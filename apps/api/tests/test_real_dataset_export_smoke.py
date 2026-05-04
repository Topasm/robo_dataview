from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from apps.api.schemas.datasets import DatasetOpenRequest
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.lance_store import LanceDatasetStore
from apps.api.services.lerobot_io import write_lerobot_v3_snapshot


RUN_REAL_DATASET_EXPORT_SMOKE = os.environ.get("RUN_REAL_DATASET_EXPORT_SMOKE") == "1"
DEFAULT_REAL_DATASET_URI = "hf://datasets/lance-format/lerobot-xvla-soft-fold/data"


@unittest.skipUnless(
    RUN_REAL_DATASET_EXPORT_SMOKE,
    "set RUN_REAL_DATASET_EXPORT_SMOKE=1 to run real dataset export smoke checks",
)
class RealDatasetExportSmokeTest(unittest.TestCase):
    def test_real_lance_dataset_subset_exports_and_loads_with_official_lerobot(self) -> None:
        dataset_uri = os.environ.get("REAL_DATASET_URI", DEFAULT_REAL_DATASET_URI)
        dataset_name = os.environ.get("REAL_DATASET_NAME", "real-export-smoke")
        episode_limit = _env_int("REAL_DATASET_EPISODE_LIMIT", default=1, minimum=1, maximum=8)
        export_videos = _env_bool("REAL_DATASET_EXPORT_VIDEOS", default=False)
        if export_videos and dataset_uri.startswith("hf://") and not _has_hf_token():
            self.skipTest(
                "HF_TOKEN is required for video materialization from hf:// Lance datasets "
                "to avoid Hugging Face API rate limits."
            )

        dataset_store = LanceDatasetStore()
        record = dataset_store.open_dataset(DatasetOpenRequest(uri=dataset_uri, name=dataset_name))
        self.assertEqual(record.status, "indexed", record.message)

        summary = dataset_store.get_summary(record.dataset_id)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertGreater(summary.episode_count, 0)

        page = dataset_store.list_episode_page(record.dataset_id, limit=episode_limit, offset=0)
        self.assertGreater(len(page.items), 0)

        episodes: list[EpisodeDetail] = []
        timeseries_by_episode: dict[int, dict[str, object]] = {}
        video_blobs_by_episode: dict[int, dict[str, bytes]] = {}
        for item in page.items:
            episode = dataset_store.get_episode(record.dataset_id, item.episode_index)
            self.assertIsNotNone(episode)
            assert episode is not None
            timeseries = dataset_store.get_episode_timeseries(record.dataset_id, item.episode_index)
            self.assertIsNotNone(timeseries)
            assert timeseries is not None
            self.assertGreater(_timeseries_frame_count(timeseries), 0)

            episodes.append(episode)
            timeseries_by_episode[episode.episode_index] = timeseries
            if export_videos:
                video_blobs = {
                    camera: blob
                    for camera in episode.camera_names
                    if (blob := _get_video_blob_or_skip(
                        self,
                        dataset_store,
                        dataset_id=record.dataset_id,
                        episode_index=episode.episode_index,
                        camera=camera,
                    ))
                    is not None
                }
                self.assertGreater(
                    len(video_blobs),
                    0,
                    f"no video blobs found for episode {episode.episode_index}",
                )
                video_blobs_by_episode[episode.episode_index] = video_blobs

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = write_lerobot_v3_snapshot(
                Path(tmpdir),
                dataset_id=record.dataset_id,
                episodes=episodes,
                annotations_by_episode={},
                version_description=f"real dataset export smoke from {dataset_uri}",
                timeseries_by_episode=timeseries_by_episode,
                video_blobs_by_episode=video_blobs_by_episode if export_videos else None,
            )

        validation = artifact["validation"]
        self.assertTrue(validation["metadata_ok"], validation)
        self.assertGreater(artifact["materialized"]["frame_rows"], 0)
        self.assertIsNotNone(artifact["files"]["data"], artifact)
        self.assertTrue(validation["official_loader"]["available"], validation["official_loader"])
        self.assertTrue(validation["official_loader"]["ok"], validation["official_loader"])
        self.assertEqual(
            validation["official_loader"]["length"],
            artifact["materialized"]["frame_rows"],
        )


def _timeseries_frame_count(timeseries: dict[str, object]) -> int:
    return max(
        len(_sequence(timeseries.get("timestamps"))),
        len(_sequence(timeseries.get("states"))),
        len(_sequence(timeseries.get("actions"))),
    )


def _sequence(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)  # type: ignore[arg-type]
    except TypeError:
        return []


def _env_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _has_hf_token() -> bool:
    return any(
        os.environ.get(name)
        for name in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN")
    )


def _get_video_blob_or_skip(
    test_case: unittest.TestCase,
    dataset_store: LanceDatasetStore,
    *,
    dataset_id: str,
    episode_index: int,
    camera: str,
) -> bytes | None:
    try:
        return dataset_store.get_video_blob(dataset_id, episode_index, camera)
    except OSError as exc:
        message = str(exc)
        if "rate limit" in message.lower() or "status: 429" in message:
            test_case.skipTest(
                "Hugging Face rate-limited video materialization; set HF_TOKEN and rerun."
            )
        raise


if __name__ == "__main__":
    unittest.main()
