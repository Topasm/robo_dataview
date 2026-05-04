from __future__ import annotations

import json
import os
import tempfile
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import SemanticSearchRequest
from apps.api.services.embedding_service import (
    DeterministicTextEmbeddingProvider,
    EmbeddingRecord,
    EmbeddingIndex,
    OpenAICompatibleEmbeddingProvider,
    embed_text,
    get_text_embedding_provider,
)


class EmbeddingServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_lancedb = sys.modules.get("lancedb")

    def tearDown(self) -> None:
        if self.previous_lancedb is None:
            sys.modules.pop("lancedb", None)
        else:
            sys.modules["lancedb"] = self.previous_lancedb

    def test_embed_text_is_normalized_and_deterministic(self) -> None:
        first = embed_text("cloth edge grasp")
        second = embed_text("cloth edge grasp")

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)

    def test_semantic_search_ranks_matching_episode_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            index = EmbeddingIndex(
                storage_root=Path(tmpdir),
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
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
            first_index = EmbeddingIndex(
                storage_root=storage_root,
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
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

            second_index = EmbeddingIndex(
                storage_root=storage_root,
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
            second_records = second_index.records("sample")
            paths = second_index.storage_paths("sample")

            self.assertEqual(
                [record.embedding_id for record in second_records],
                [first_records[0].embedding_id],
            )
            self.assertTrue(Path(paths["jsonl"]).exists())
            self.assertTrue(paths["lance"].endswith("/embeddings.lance"))
            self.assertTrue(paths["lancedb"].endswith("/lancedb"))

    def test_embedding_index_upserts_visual_records_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            record = EmbeddingRecord(
                embedding_id="visual-1",
                episode_index=7,
                frame_index=12,
                clip_start_frame=12,
                clip_end_frame=12,
                modality="image",
                embedding=[1.0, 0.0],
                text="cam_high frame 12 visual keyframe",
                source_model="fake-vision",
                created_at=datetime.now(timezone.utc),
                camera="cam_high",
                source_uri="/tmp/keyframe.jpg",
                content_hash="abc123",
            )
            first_index = EmbeddingIndex(
                storage_root=storage_root,
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
            first_index.upsert_records("sample", [record])

            second_index = EmbeddingIndex(
                storage_root=storage_root,
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
            loaded = second_index.records("sample")

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].modality, "image")
        self.assertEqual(loaded[0].camera, "cam_high")
        self.assertEqual(loaded[0].source_uri, "/tmp/keyframe.jpg")
        self.assertEqual(loaded[0].content_hash, "abc123")

    def test_text_reindex_preserves_visual_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            index = EmbeddingIndex(
                storage_root=Path(tmpdir),
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
            visual_record = EmbeddingRecord(
                embedding_id="visual-1",
                episode_index=1,
                frame_index=4,
                clip_start_frame=4,
                clip_end_frame=4,
                modality="image",
                embedding=[1.0, 0.0],
                text="cam_high frame 4 visual keyframe",
                source_model="fake-vision",
                created_at=datetime.now(timezone.utc),
                camera="cam_high",
                source_uri="/tmp/keyframe.jpg",
                content_hash="abc123",
            )
            index.upsert_records("sample", [visual_record])

            index.index_dataset(
                "sample",
                episodes=[
                    EpisodeListItem(
                        dataset_id="sample",
                        episode_index=1,
                        task_index=3,
                        length=100,
                        caption="cloth grasp",
                    )
                ],
                annotations=[],
            )
            records = index.records("sample")

        self.assertIn("visual-1", {record.embedding_id for record in records})
        self.assertIn("image", {record.modality for record in records})
        self.assertIn("text", {record.modality for record in records})

    def test_embedding_index_can_search_without_persisting_filtered_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            index = EmbeddingIndex(
                storage_root=storage_root,
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=False,
            )
            episodes = [
                EpisodeListItem(
                    dataset_id="sample",
                    episode_index=1,
                    task_index=3,
                    length=100,
                    caption="successful cloth edge grasp",
                )
            ]

            results = index.search(
                SemanticSearchRequest(dataset_id="sample", text="cloth", limit=1),
                episodes=episodes,
                annotations=[],
                persist_records=False,
            )

            self.assertEqual(results[0].episode_index, 1)
            self.assertEqual(index.records("sample"), [])
            self.assertEqual(list(storage_root.rglob("embeddings.jsonl")), [])

    def test_embedding_index_uses_lancedb_when_available(self) -> None:
        fake_db = FakeLanceDb()
        sys.modules["lancedb"] = types.SimpleNamespace(connect=lambda path: fake_db)
        with tempfile.TemporaryDirectory() as tmpdir:
            index = EmbeddingIndex(
                storage_root=Path(tmpdir),
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=True,
            )
            episodes = [
                EpisodeListItem(
                    dataset_id="sample",
                    episode_index=1,
                    task_index=3,
                    length=100,
                    caption="successful cloth edge grasp",
                )
            ]

            results = index.search(
                SemanticSearchRequest(dataset_id="sample", text="cloth grasp", limit=2),
                episodes=episodes,
                annotations=[],
            )

        self.assertEqual(fake_db.created_table_name, "embeddings")
        self.assertEqual(fake_db.opened_table_name, "embeddings")
        self.assertEqual(results[0].match_type, "lancedb_vector")
        self.assertEqual(results[0].episode_index, 1)

    def test_lancedb_search_filters_to_text_rows(self) -> None:
        fake_db = FakeLanceDb()
        sys.modules["lancedb"] = types.SimpleNamespace(connect=lambda path: fake_db)
        with tempfile.TemporaryDirectory() as tmpdir:
            index = EmbeddingIndex(
                storage_root=Path(tmpdir),
                embedding_provider=DeterministicTextEmbeddingProvider(),
                mirror_lance=False,
                mirror_lancedb=True,
            )
            index.upsert_records(
                "sample",
                [
                    EmbeddingRecord(
                        embedding_id="visual-1",
                        episode_index=99,
                        frame_index=0,
                        clip_start_frame=0,
                        clip_end_frame=0,
                        modality="image",
                        embedding=[1.0, 0.0],
                        text="cam_high frame 0 visual keyframe",
                        source_model="fake-vision",
                        created_at=datetime.now(timezone.utc),
                        camera="cam_high",
                        source_uri="/tmp/keyframe.jpg",
                        content_hash="abc123",
                    )
                ],
            )

            results = index.search(
                SemanticSearchRequest(dataset_id="sample", text="cloth grasp", limit=2),
                episodes=[
                    EpisodeListItem(
                        dataset_id="sample",
                        episode_index=1,
                        task_index=3,
                        length=100,
                        caption="successful cloth edge grasp",
                    )
                ],
                annotations=[],
            )

        self.assertEqual([result.episode_index for result in results], [1])
        self.assertEqual(results[0].match_type, "lancedb_vector")

    def test_embedding_index_uses_configured_embedding_provider(self) -> None:
        provider = FakeTextEmbeddingProvider()
        with tempfile.TemporaryDirectory() as tmpdir:
            index = EmbeddingIndex(
                storage_root=Path(tmpdir),
                embedding_provider=provider,
                mirror_lance=False,
                mirror_lancedb=False,
            )
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
            records = index.records("sample")

        self.assertEqual(results[0].episode_index, 1)
        self.assertEqual(records[0].source_model, "fake-text-embedding")
        self.assertIn("cloth grasp", provider.seen_texts)

    def test_openai_compatible_embedding_provider_posts_to_embeddings_endpoint(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeHttpResponse(
                {
                    "data": [
                        {"index": 0, "embedding": [3.0, 4.0]},
                        {"index": 1, "embedding": [0.0, 2.0]},
                    ]
                }
            )

        provider = OpenAICompatibleEmbeddingProvider(
            api_key="test-key",
            base_url="https://embedding.example.test/v1",
            model="embed-test",
            timeout_seconds=3,
        )
        with patch("apps.api.services.embedding_service.urlopen", side_effect=fake_urlopen):
            embeddings = provider.embed_many(["cloth", "empty"])

        self.assertEqual(captured["url"], "https://embedding.example.test/v1/embeddings")
        self.assertEqual(captured["authorization"], "Bearer test-key")
        self.assertEqual(captured["body"], {"model": "embed-test", "input": ["cloth", "empty"]})
        self.assertEqual(captured["timeout"], 3)
        self.assertAlmostEqual(embeddings[0][0], 0.6)
        self.assertEqual(provider.source_model, "openai-compatible:embed-test")

    def test_embedding_provider_env_selects_openai_compatible(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ROBOT_DATA_STUDIO_EMBEDDING_PROVIDER": "openai-compatible",
                "ROBOT_DATA_STUDIO_EMBEDDING_BASE_URL": "https://embedding.example.test/v1",
                "ROBOT_DATA_STUDIO_EMBEDDING_MODEL": "embed-test",
            },
            clear=False,
        ):
            provider = get_text_embedding_provider()

        self.assertIsInstance(provider, OpenAICompatibleEmbeddingProvider)


class FakeLanceDb:
    def __init__(self) -> None:
        self.created_table_name: str | None = None
        self.opened_table_name: str | None = None
        self.rows: list[dict[str, object]] = []

    def create_table(self, name: str, data: list[dict[str, object]], mode: str) -> None:
        self.created_table_name = name
        self.rows = [{**row, "_distance": 0.0} for row in data]

    def open_table(self, name: str) -> "FakeLanceTable":
        self.opened_table_name = name
        return FakeLanceTable(self.rows)


class FakeLanceTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def search(self, query_embedding: list[float], vector_column_name: str | None = None) -> "FakeLanceQuery":
        return FakeLanceQuery(self.rows)


class FakeLanceQuery:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.limit_value = len(rows)

    def limit(self, value: int) -> "FakeLanceQuery":
        self.limit_value = value
        return self

    def to_list(self) -> list[dict[str, object]]:
        return self.rows[: self.limit_value]


class FakeTextEmbeddingProvider:
    source_model = "fake-text-embedding"

    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.seen_texts.extend(texts)
        return [[1.0, 0.0] if "cloth" in text else [0.0, 1.0] for text in texts]


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
