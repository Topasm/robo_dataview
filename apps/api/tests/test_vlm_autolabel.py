from __future__ import annotations

import unittest

from apps.api.schemas.episodes import EpisodeDetail
from workers.vlm_autolabel import AutoLabelConfig, build_vlm_annotation_proposals, select_keyframes


class VlmAutoLabelTest(unittest.TestCase):
    def test_select_keyframes_spreads_across_episode(self) -> None:
        indices = select_keyframes(180)

        self.assertEqual(len(indices), 16)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 179)
        self.assertEqual(indices, sorted(set(indices)))

    def test_select_keyframes_keeps_all_short_episode_frames(self) -> None:
        self.assertEqual(select_keyframes(5), [0, 1, 2, 3, 4])

    def test_vlm_proposals_include_prompt_keyframes(self) -> None:
        episode = EpisodeDetail(
            dataset_id="dataset-a",
            episode_index=4,
            task_index=3,
            length=60,
            fps=20.0,
            camera_names=["cam_high"],
            caption="Fold the cloth",
            success_label=True,
        )
        proposals = build_vlm_annotation_proposals(
            "dataset-a",
            episode,
            AutoLabelConfig(
                model="test-vlm",
                prompt_template="episode_autolabel_v1",
                min_keyframes=8,
                max_keyframes=8,
            ),
        )
        keyframes = [proposal for proposal in proposals if proposal.label_type == "important_frame"]

        self.assertEqual(len(keyframes), 8)
        self.assertEqual(keyframes[0].start_frame, 0)
        self.assertEqual(keyframes[-1].start_frame, 59)
        self.assertTrue(all(proposal.label_value.startswith("keyframe_") for proposal in keyframes))


if __name__ == "__main__":
    unittest.main()
