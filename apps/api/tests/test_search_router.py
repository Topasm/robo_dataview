from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from apps.api.routers import search
from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import FilterPresetCreate
from apps.api.services.filter_preset_service import FilterPresetStore


class SearchRouterTest(unittest.TestCase):
    def test_filter_preset_endpoints_create_list_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilterPresetStore(storage_root=Path(tmpdir))
            with patch.object(search, "filter_preset_store", store):
                created = search.create_filter_preset(
                    FilterPresetCreate(
                        dataset_id="dataset-a",
                        name="Accepted",
                        query='review_status == "accepted"',
                    )
                )
                loaded = search.list_filter_presets(dataset_id="dataset-a")
                deleted = search.delete_filter_preset(created.preset_id)

            self.assertEqual([preset.preset_id for preset in loaded], [created.preset_id])
            self.assertEqual(deleted, {"status": "deleted"})

    def test_delete_missing_filter_preset_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilterPresetStore(storage_root=Path(tmpdir))
            with patch.object(search, "filter_preset_store", store):
                with self.assertRaises(HTTPException) as context:
                    search.delete_filter_preset("missing")

            self.assertEqual(context.exception.status_code, 404)

    def test_semantic_search_filters_candidates_before_ranking(self) -> None:
        now = datetime.now(timezone.utc)
        episodes = [
            EpisodeListItem(
                dataset_id="dataset-a",
                episode_index=1,
                review_status="accepted",
                caption="cloth grasp",
            ),
            EpisodeListItem(
                dataset_id="dataset-a",
                episode_index=2,
                review_status="rejected",
                caption="empty table",
            ),
        ]
        annotations = [
            AnnotationRecord(
                annotation_id="ann-1",
                dataset_id="dataset-a",
                episode_index=1,
                start_frame=0,
                end_frame=0,
                label_type="phase",
                label_value="grasp",
                source=AnnotationSource.human,
                confidence=1,
                review_status=ReviewStatus.accepted,
                created_by="tester",
                created_at=now,
                updated_at=now,
            ),
            AnnotationRecord(
                annotation_id="ann-2",
                dataset_id="dataset-a",
                episode_index=2,
                start_frame=0,
                end_frame=0,
                label_type="phase",
                label_value="slip",
                source=AnnotationSource.human,
                confidence=1,
                review_status=ReviewStatus.accepted,
                created_by="tester",
                created_at=now,
                updated_at=now,
            ),
        ]
        fake_store = _FakeSearchStore(episodes=episodes, filtered_episode_indices=[1])
        fake_annotations = _FakeAnnotationStore(annotations=annotations)
        fake_index = _FakeEmbeddingIndex()
        payload = search.SemanticSearchRequest(
            dataset_id="dataset-a",
            text="cloth",
            filter_query='review_status == "accepted"',
        )

        with (
            patch.object(search, "store", fake_store),
            patch.object(search, "annotation_store", fake_annotations),
            patch.object(search, "embedding_index", fake_index),
        ):
            results = search.semantic_search(payload)

        self.assertEqual(results[0].episode_index, 1)
        self.assertEqual(fake_store.filter_query, 'review_status == "accepted"')
        self.assertEqual([episode.episode_index for episode in fake_index.seen_episodes], [1])
        self.assertEqual([annotation.episode_index for annotation in fake_index.seen_annotations], [1])
        self.assertFalse(fake_index.persist_records)


class _FakeSearchStore:
    def __init__(self, episodes: list[EpisodeListItem], filtered_episode_indices: list[int]) -> None:
        self.episodes = episodes
        self.filtered_episode_indices = filtered_episode_indices
        self.filter_query: str | None = None

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[EpisodeListItem]:
        del dataset_id, limit, offset
        return self.episodes

    def filter_search(self, payload: search.FilterSearchRequest) -> list[search.SearchResult]:
        self.filter_query = payload.query
        return [
            search.SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode_index,
                match_type="episode_filter",
            )
            for episode_index in self.filtered_episode_indices
        ]


class _FakeAnnotationStore:
    def __init__(self, annotations: list[AnnotationRecord]) -> None:
        self.annotations = annotations

    def list(self, dataset_id: str, episode_index: int | None) -> list[AnnotationRecord]:
        del dataset_id, episode_index
        return self.annotations


class _FakeEmbeddingIndex:
    def __init__(self) -> None:
        self.seen_episodes: list[EpisodeListItem] = []
        self.seen_annotations: list[AnnotationRecord] = []
        self.persist_records: bool | None = None

    def search(
        self,
        payload: search.SemanticSearchRequest,
        *,
        episodes: list[EpisodeListItem],
        annotations: list[AnnotationRecord],
        persist_records: bool,
    ) -> list[search.SearchResult]:
        self.seen_episodes = episodes
        self.seen_annotations = annotations
        self.persist_records = persist_records
        return [
            search.SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=1.0,
                match_type="semantic_text_embedding",
                label=episode.caption,
            )
            for episode in episodes
        ]


if __name__ == "__main__":
    unittest.main()
