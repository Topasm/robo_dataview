from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.hf_dataset_export import write_hf_dataset_export


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


if __name__ == "__main__":
    unittest.main()
