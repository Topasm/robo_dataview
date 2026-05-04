from __future__ import annotations

import unittest

from apps.api.schemas.episodes import EpisodeDetail
from workers.vlm_autolabel import AutoLabelConfig
from workers.vlm_provider import get_vlm_provider


class VlmProviderTest(unittest.TestCase):
    def test_heuristic_provider_returns_raw_response_and_proposals(self) -> None:
        provider = get_vlm_provider("heuristic-vlm-fallback")
        episode = EpisodeDetail(
            dataset_id="dataset-a",
            episode_index=2,
            task_index=3,
            length=24,
            fps=20.0,
            camera_names=["cam_high"],
        )
        result = provider.propose(
            dataset_id="dataset-a",
            episode=episode,
            config=AutoLabelConfig(
                model="heuristic-vlm-fallback",
                prompt_template="episode_autolabel_v1",
                prompt_version="v1",
            ),
        )

        self.assertEqual(result.provider, "heuristic-fallback")
        self.assertEqual(result.raw_response["provider"], "heuristic-fallback")
        self.assertEqual(result.raw_response["prompt_version"], "v1")
        self.assertGreaterEqual(len(result.raw_response["keyframes"]), 8)
        self.assertGreaterEqual(len(result.proposals), 12)


if __name__ == "__main__":
    unittest.main()
