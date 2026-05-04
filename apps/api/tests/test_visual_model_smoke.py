from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import SemanticSearchRequest
from apps.api.services.embedding_service import (
    EmbeddingIndex,
    EmbeddingRecord,
    TransformersTextEmbeddingProvider,
    create_embedding_id,
)
from workers.visual_embedding_worker import TransformersVisionEmbeddingProvider


RUN_VISUAL_MODEL_SMOKE = os.environ.get("RUN_VISUAL_MODEL_SMOKE") == "1"
DEFAULT_VISUAL_MODEL_SMOKE_MODEL = "openai/clip-vit-base-patch32"


@unittest.skipUnless(
    RUN_VISUAL_MODEL_SMOKE,
    "set RUN_VISUAL_MODEL_SMOKE=1 to run real CLIP/SigLIP visual model smoke checks",
)
class VisualModelSmokeTest(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec("PIL") is None, "pillow is not installed")
    @unittest.skipIf(importlib.util.find_spec("torch") is None, "torch is not installed")
    @unittest.skipIf(importlib.util.find_spec("transformers") is None, "transformers is not installed")
    def test_transformers_visual_embeddings_are_searchable_with_matching_text_encoder(self) -> None:
        from PIL import Image

        model_name = os.environ.get(
            "VISUAL_MODEL_SMOKE_MODEL",
            DEFAULT_VISUAL_MODEL_SMOKE_MODEL,
        )
        dataset_id = "visual-model-smoke"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = root / "red-square.jpg"
            Image.new("RGB", (64, 64), (220, 24, 24)).save(image_path)

            visual_provider = TransformersVisionEmbeddingProvider(model_name)
            [image_embedding] = visual_provider.embed_images([image_path])
            text_provider = TransformersTextEmbeddingProvider(model_name)

            record = EmbeddingRecord(
                embedding_id=create_embedding_id(
                    dataset_id,
                    scope=f"visual:{visual_provider.source_model}:cam_high:0:smoke",
                    text="cam_high frame 0 visual keyframe",
                ),
                episode_index=0,
                frame_index=0,
                clip_start_frame=0,
                clip_end_frame=0,
                modality="image",
                embedding=image_embedding,
                text="cam_high frame 0 visual keyframe",
                source_model=visual_provider.source_model,
                created_at=datetime.now(timezone.utc),
                camera="cam_high",
                source_uri=str(image_path),
                content_hash="visual-model-smoke",
            )
            index = EmbeddingIndex(
                storage_root=root / "embeddings",
                embedding_provider=text_provider,
                mirror_lance=False,
                mirror_lancedb=False,
            )
            index.upsert_records(dataset_id, [record])

            results = index.search(
                SemanticSearchRequest(
                    dataset_id=dataset_id,
                    text="red square",
                    modalities=["image"],
                    limit=1,
                ),
                episodes=[EpisodeListItem(dataset_id=dataset_id, episode_index=0, caption="red square")],
                annotations=[],
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].episode_index, 0)
        self.assertEqual(results[0].frame_index, 0)
        self.assertEqual(results[0].match_type, "semantic_visual_embedding")
        self.assertEqual(results[0].source_model, visual_provider.source_model)
        self.assertIsNotNone(results[0].score)
        assert results[0].score is not None
        self.assertGreater(results[0].score, 0)


if __name__ == "__main__":
    unittest.main()
