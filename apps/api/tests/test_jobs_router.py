from __future__ import annotations

import unittest

from apps.api.routers.jobs import list_vlm_prompts


class JobsRouterTest(unittest.TestCase):
    def test_list_vlm_prompts_exposes_registered_prompt_versions(self) -> None:
        prompts = list_vlm_prompts()

        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].prompt_id, "episode_autolabel_v1")
        self.assertEqual(prompts[0].version, "v1")
        self.assertIn("phase", prompts[0].expected_outputs)


if __name__ == "__main__":
    unittest.main()
