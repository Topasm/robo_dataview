from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import SemanticSearchRequest
from apps.api.services.embedding_service import EmbeddingIndex, embed_text


class EmbeddingServiceTest(unittest.TestCase):
    def test_embed_text_is_normalized_and_deterministic(self) -> None:
        first = embed_text("cloth edge grasp")
        second = embed_text("cloth edge grasp")

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)

    def test_semantic_search_ranks_matching_episode_text(self) -> None:
        index = EmbeddingIndex()
        episodes = [
            EpisodeListItem(
                dataset_id="sample",
                episode_index=1,
                task_index=3,
                length=100,
                caption="successful cloth edge grasp",
            ),
            EpisodeListItem(
                dataset_id="sample",
                episode_index=2,
                task_index=4,
                length=100,
                caption="empty workspace",
            ),
        ]

        results = index.search(
            SemanticSearchRequest(dataset_id="sample", text="cloth grasp", limit=2),
            episodes=episodes,
            annotations=[],
        )

        self.assertEqual(results[0].episode_index, 1)
        self.assertEqual(results[0].match_type, "semantic_text_embedding")

    def test_embedding_index_persists_records_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first_index = EmbeddingIndex(storage_root=storage_root, mirror_lance=False)
            episodes = [
                EpisodeListItem(
                    dataset_id="sample",
                    episode_index=1,
                    task_index=3,
                    length=100,
                    caption="successful cloth edge grasp",
                )
            ]
            first_records = first_index.index_dataset("sample", episodes=episodes, annotations=[])

            second_index = EmbeddingIndex(storage_root=storage_root, mirror_lance=False)
            second_records = second_index.records("sample")
            paths = second_index.storage_paths("sample")

            self.assertEqual([record.embedding_id for record in second_records], [first_records[0].embedding_id])
            self.assertTrue(Path(paths["jsonl"]).exists())
            self.assertTrue(paths["lance"].endswith("/embeddings.lance"))


if __name__ == "__main__":
    unittest.main()
