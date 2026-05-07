from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.episodes import EpisodeDispositionUpdate
from apps.api.services.annotation_service import (
    EPISODE_DISPOSITION_LABEL_TYPE,
    AnnotationStore,
)


class EpisodeDispositionSchemaTest(unittest.TestCase):
    def test_validator_accepts_known_values(self) -> None:
        for value in ("kept", "deleted", "flagged", None):
            payload = EpisodeDispositionUpdate(disposition=value)
            self.assertEqual(payload.disposition, value)

    def test_validator_rejects_unknown_values(self) -> None:
        with self.assertRaises(ValueError):
            EpisodeDispositionUpdate(disposition="archived")


class EpisodeDispositionStoreTest(unittest.TestCase):
    def _store(self) -> AnnotationStore:
        return AnnotationStore(persist=False, mirror_lance=False)

    def test_upsert_create_then_update_then_clear(self) -> None:
        store = self._store()
        dataset_id = "dataset-disposition"

        # No existing record, clearing is a no-op.
        self.assertIsNone(
            store.upsert_episode_disposition(
                dataset_id=dataset_id,
                episode_index=0,
                disposition=None,
                reason=None,
            )
        )

        # Create a "deleted" disposition.
        created = store.upsert_episode_disposition(
            dataset_id=dataset_id,
            episode_index=0,
            disposition="deleted",
            reason="frame drift",
            actor="alice",
        )
        self.assertIsNotNone(created)
        assert created is not None
        self.assertEqual(created["disposition"], "deleted")
        self.assertEqual(created["reason"], "frame drift")
        self.assertIsInstance(created["disposition_updated_at"], datetime)

        records = [
            record
            for record in store._records.values()
            if record.label_type == EPISODE_DISPOSITION_LABEL_TYPE
            and record.deleted_at is None
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].label_value, "deleted")
        self.assertEqual(records[0].source, AnnotationSource.human)
        self.assertEqual(records[0].review_status, ReviewStatus.accepted)
        self.assertEqual(records[0].metadata.get("reason"), "frame drift")

        # Update — should reuse the same annotation row (still 1 active).
        updated = store.upsert_episode_disposition(
            dataset_id=dataset_id,
            episode_index=0,
            disposition="kept",
            reason=None,
            actor="bob",
        )
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["disposition"], "kept")
        self.assertIsNone(updated["reason"])

        active = [
            record
            for record in store._records.values()
            if record.label_type == EPISODE_DISPOSITION_LABEL_TYPE
            and record.deleted_at is None
        ]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].label_value, "kept")
        self.assertEqual(active[0].metadata, {})

        # Clear — soft delete, no active row remains.
        cleared = store.upsert_episode_disposition(
            dataset_id=dataset_id,
            episode_index=0,
            disposition=None,
            reason=None,
            actor="bob",
        )
        self.assertIsNone(cleared)
        active = [
            record
            for record in store._records.values()
            if record.label_type == EPISODE_DISPOSITION_LABEL_TYPE
            and record.deleted_at is None
        ]
        self.assertEqual(active, [])
        self.assertEqual(store.list_episode_dispositions(dataset_id), {})

    def test_list_episode_dispositions_returns_latest_per_episode(self) -> None:
        store = self._store()
        dataset_id = "dataset-multi"
        # Episode 1 — single disposition.
        store.upsert_episode_disposition(
            dataset_id=dataset_id,
            episode_index=1,
            disposition="flagged",
            reason="needs review",
        )
        # Episode 2 — write two records via raw create() to simulate migration
        # duplicates; only the newest should survive in list_episode_dispositions.
        older = store.create(
            AnnotationCreate(
                dataset_id=dataset_id,
                episode_index=2,
                start_frame=0,
                end_frame=0,
                label_type=EPISODE_DISPOSITION_LABEL_TYPE,
                label_value="kept",
                source=AnnotationSource.human,
                review_status=ReviewStatus.accepted,
                metadata={"reason": "old"},
            )
        )
        # Force the older record's updated_at into the past so the next create
        # is unambiguously newer regardless of clock granularity.
        older.updated_at = older.updated_at - timedelta(minutes=1)
        store._records[older.annotation_id] = older
        store.create(
            AnnotationCreate(
                dataset_id=dataset_id,
                episode_index=2,
                start_frame=0,
                end_frame=0,
                label_type=EPISODE_DISPOSITION_LABEL_TYPE,
                label_value="deleted",
                source=AnnotationSource.human,
                review_status=ReviewStatus.accepted,
                metadata={"reason": "newer"},
            )
        )

        # Different dataset should be ignored.
        store.upsert_episode_disposition(
            dataset_id="other-dataset",
            episode_index=1,
            disposition="kept",
            reason=None,
        )

        dispositions = store.list_episode_dispositions(dataset_id)
        self.assertEqual(set(dispositions.keys()), {1, 2})
        self.assertEqual(dispositions[1]["disposition"], "flagged")
        self.assertEqual(dispositions[1]["reason"], "needs review")
        self.assertEqual(dispositions[2]["disposition"], "deleted")
        self.assertEqual(dispositions[2]["reason"], "newer")
        self.assertIsInstance(dispositions[1]["disposition_updated_at"], datetime)
        # Latest selection: episode 2 should reflect the newer row.
        self.assertGreater(
            dispositions[2]["disposition_updated_at"],
            datetime.now(timezone.utc) - timedelta(minutes=5),
        )


if __name__ == "__main__":
    unittest.main()
