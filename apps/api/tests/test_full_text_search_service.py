from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import FullTextSearchRequest
from apps.api.services.full_text_search_service import full_text_search


class FullTextSearchServiceTest(unittest.TestCase):
    def test_full_text_search_matches_episode_and_annotation_text(self) -> None:
        now = datetime.now(timezone.utc)
        episodes = [
            EpisodeListItem(
                dataset_id="sample",
                episode_index=1,
                task_index=3,
                length=100,
                caption="successful cloth edge grasp",
                review_status="accepted",
            ),
            EpisodeListItem(
                dataset_id="sample",
                episode_index=2,
                task_index=4,
                length=100,
                caption="empty workspace",
                review_status="pending",
            ),
        ]
        annotations = [
            AnnotationRecord(
                annotation_id="ann-1",
                dataset_id="sample",
                episode_index=2,
                start_frame=5,
                end_frame=5,
                label_type="failure_reason",
                label_value="cloth slipped from gripper",
                source=AnnotationSource.vlm,
                confidence=0.8,
                review_status=ReviewStatus.pending,
                created_by="test",
                created_at=now,
                updated_at=now,
            )
        ]

        results = full_text_search(
            FullTextSearchRequest(dataset_id="sample", text="cloth gripper", limit=10),
            episodes=episodes,
            annotations=annotations,
        )

        self.assertEqual(results[0].episode_index, 2)
        self.assertEqual(results[0].frame_index, 5)
        self.assertEqual(results[0].match_type, "full_text_annotation")
        self.assertEqual(results[1].episode_index, 1)
        self.assertIn("cloth", results[0].label or "")

    def test_full_text_search_returns_empty_for_blank_query(self) -> None:
        results = full_text_search(
            FullTextSearchRequest(dataset_id="sample", text="   ", limit=10),
            episodes=[],
            annotations=[],
        )

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
