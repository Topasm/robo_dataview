from __future__ import annotations

import unittest

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.common import ReviewStatus
from apps.api.services.annotation_service import AnnotationStore
from apps.api.services import lance_store
from apps.api.services.lance_store import _count_dirty_annotations


class EpisodeDirtyCountTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_store = lance_store.annotation_store if hasattr(
            lance_store, "annotation_store"
        ) else None
        self.store = AnnotationStore(persist=False)
        # Inject our isolated store into the lance_store module so the
        # dirty-count helper exercises it instead of the global singleton.
        import apps.api.services.annotation_service as annotation_service

        self._original_global = annotation_service.annotation_store
        annotation_service.annotation_store = self.store

    def tearDown(self) -> None:
        import apps.api.services.annotation_service as annotation_service

        annotation_service.annotation_store = self._original_global

    def _make(self, *, episode_index: int = 0, status: ReviewStatus = ReviewStatus.accepted):
        return self.store.create(
            AnnotationCreate(
                dataset_id="dataset-a",
                episode_index=episode_index,
                start_frame=0,
                end_frame=1,
                label_type="skill",
                label_value="approach",
                review_status=status,
            )
        )

    def test_dirty_count_excludes_applied_and_rejected(self) -> None:
        unapplied_accepted = self._make(status=ReviewStatus.accepted)
        unapplied_edited = self._make(status=ReviewStatus.edited)
        rejected = self._make(status=ReviewStatus.rejected)
        already_applied = self._make(status=ReviewStatus.accepted)
        self.store.mark_applied([already_applied.annotation_id], export_id="export-old")

        count = _count_dirty_annotations("dataset-a", 0)
        self.assertEqual(count, 2)
        self.assertNotIn(rejected.annotation_id, {})  # smoke ref so the var is used

    def test_dirty_count_after_apply_drops_to_zero_then_returns_with_new_edits(self) -> None:
        first = self._make(status=ReviewStatus.accepted)
        second = self._make(status=ReviewStatus.accepted)
        self.assertEqual(_count_dirty_annotations("dataset-a", 0), 2)

        self.store.mark_applied(
            [first.annotation_id, second.annotation_id],
            export_id="export-fresh",
        )
        self.assertEqual(_count_dirty_annotations("dataset-a", 0), 0)

        self._make(status=ReviewStatus.edited)
        self.assertEqual(_count_dirty_annotations("dataset-a", 0), 1)

    def test_dirty_count_isolated_per_episode(self) -> None:
        self._make(episode_index=0, status=ReviewStatus.accepted)
        self._make(episode_index=1, status=ReviewStatus.accepted)
        self._make(episode_index=1, status=ReviewStatus.accepted)

        self.assertEqual(_count_dirty_annotations("dataset-a", 0), 1)
        self.assertEqual(_count_dirty_annotations("dataset-a", 1), 2)
        self.assertEqual(_count_dirty_annotations("dataset-a", 99), 0)


if __name__ == "__main__":
    unittest.main()
