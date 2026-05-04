from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from apps.api.schemas.episodes import EpisodeDetail
from workers.keyframe_extractor import KeyframeArtifact
from workers.vlm_autolabel import AutoLabelConfig
from workers.vlm_provider import get_vlm_provider


class VlmProviderTest(unittest.TestCase):
    def test_heuristic_provider_returns_raw_response_and_proposals(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_VLM_PROVIDER": ""}, clear=False):
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
        self.assertEqual(result.raw_response["keyframe_image_count"], 0)
        self.assertGreaterEqual(len(result.proposals), 12)

    def test_provider_includes_extracted_keyframe_image_artifacts(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_VLM_PROVIDER": ""}, clear=False):
            provider = get_vlm_provider("heuristic-vlm-fallback")
        episode = EpisodeDetail(
            dataset_id="dataset-a",
            episode_index=2,
            task_index=3,
            length=24,
            fps=20.0,
            camera_names=["cam_high"],
        )

        def fake_extract(**kwargs):
            return [
                KeyframeArtifact(
                    camera=kwargs["camera"],
                    frame_index=0,
                    uri="/tmp/keyframe.jpg",
                    width=32,
                    height=24,
                )
            ]

        with patch("workers.vlm_provider.extract_keyframes_from_blob", side_effect=fake_extract):
            result = provider.propose(
                dataset_id="dataset-a",
                episode=episode,
                config=AutoLabelConfig(
                    model="heuristic-vlm-fallback",
                    prompt_template="episode_autolabel_v1",
                    prompt_version="v1",
                ),
                video_blobs={"cam_high": b"fake mp4"},
            )

        self.assertEqual(result.raw_response["keyframe_image_count"], 1)
        self.assertEqual(result.raw_response["keyframe_images"][0]["camera"], "cam_high")
        self.assertEqual(result.raw_response["keyframe_images"][0]["uri"], "/tmp/keyframe.jpg")

    def test_openai_compatible_provider_posts_images_and_parses_annotations(self) -> None:
        episode = EpisodeDetail(
            dataset_id="dataset-a",
            episode_index=2,
            task_index=3,
            length=24,
            fps=20.0,
            camera_names=["cam_high"],
        )
        captured: dict[str, object] = {}

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image:
            image.write(b"fake-jpeg")
            image.flush()

            def fake_extract(**kwargs):
                return [
                    KeyframeArtifact(
                        camera=kwargs["camera"],
                        frame_index=0,
                        uri=image.name,
                        width=32,
                        height=24,
                    )
                ]

            def fake_urlopen(request, timeout):
                captured["url"] = request.full_url
                captured["body"] = json.loads(request.data.decode("utf-8"))
                captured["authorization"] = request.get_header("Authorization")
                captured["timeout"] = timeout
                return FakeHttpResponse(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "episode_caption": {
                                                "text": "Robot grasps the cloth edge.",
                                                "confidence": 0.91,
                                            },
                                            "success_label": {
                                                "value": "success",
                                                "confidence": 0.88,
                                            },
                                            "object_list": ["cloth", "gripper"],
                                            "phases": [
                                                {
                                                    "label": "approach",
                                                    "start_frame": 0,
                                                    "end_frame": 8,
                                                    "confidence": 0.7,
                                                }
                                            ],
                                            "important_frames": [
                                                {
                                                    "frame_index": 5,
                                                    "label": "edge contact",
                                                    "confidence": 0.67,
                                                }
                                            ],
                                        }
                                    )
                                }
                            }
                        ]
                    }
                )

            with (
                patch.dict(
                    os.environ,
                    {
                        "ROBOT_DATA_STUDIO_VLM_API_KEY": "test-key",
                        "ROBOT_DATA_STUDIO_VLM_BASE_URL": "https://vlm.example.test/v1",
                    },
                    clear=False,
                ),
                patch("workers.vlm_provider.extract_keyframes_from_blob", side_effect=fake_extract),
                patch("workers.vlm_provider.urlopen", side_effect=fake_urlopen),
            ):
                provider = get_vlm_provider("openai-compatible:test-vlm")
                result = provider.propose(
                    dataset_id="dataset-a",
                    episode=episode,
                    config=AutoLabelConfig(
                        model="openai-compatible:test-vlm",
                        prompt_template="episode_autolabel_v1",
                        prompt_version="v1",
                        prompt_body="Return JSON labels.",
                    ),
                    video_blobs={"cam_high": b"fake mp4"},
                )

        self.assertEqual(result.provider, "openai-compatible")
        self.assertEqual(captured["url"], "https://vlm.example.test/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer test-key")
        self.assertEqual(captured["body"]["model"], "test-vlm")
        messages = captured["body"]["messages"]
        user_content = messages[1]["content"]
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertEqual(result.raw_response["proposal_count"], 5)
        self.assertEqual([proposal.label_type for proposal in result.proposals][:2], [
            "episode_caption",
            "success_label",
        ])
        self.assertEqual(result.proposals[0].label_value, "Robot grasps the cloth edge.")
        self.assertEqual(result.proposals[-1].start_frame, 5)
        redacted_url = result.raw_response["request"]["messages"][1]["content"][1]["image_url"]["url"]
        self.assertEqual(redacted_url, "[image-data-url]")


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
