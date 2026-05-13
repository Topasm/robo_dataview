from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from apps.api.schemas.annotations import AnnotationCreate, AnnotationUpdate
from apps.api.schemas.common import ReviewStatus
from apps.api.services.annotation_service import AnnotationConflictError, AnnotationStore


class AnnotationServiceTest(unittest.TestCase):
    def test_annotation_store_persists_jsonl_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            created = first_store.create(
                AnnotationCreate(
                    dataset_id="sample-xvla-soft-fold",
                    episode_index=0,
                    start_frame=4,
                    end_frame=12,
                    label_type="phase",
                    label_value="cloth_edge_grasp",
                    review_status=ReviewStatus.accepted,
                )
            )

            second_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            loaded = second_store.list("sample-xvla-soft-fold", episode_index=0)
            self.assertEqual([record.annotation_id for record in loaded], [created.annotation_id])
            self.assertEqual(loaded[0].label_value, "cloth_edge_grasp")
            self.assertEqual(loaded[0].review_status, ReviewStatus.accepted)

            second_store.update(
                created.annotation_id,
                AnnotationUpdate(label_value="cloth_release", review_status=ReviewStatus.edited),
            )
            third_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            updated = third_store.list("sample-xvla-soft-fold", episode_index=0)[0]
            self.assertEqual(updated.label_value, "cloth_release")
            self.assertEqual(updated.review_status, ReviewStatus.edited)
            self.assertEqual(updated.revision, 2)

            third_store.delete(created.annotation_id)
            fourth_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            self.assertEqual(fourth_store.list("sample-xvla-soft-fold", episode_index=0), [])
            persisted = fourth_store._records[created.annotation_id]
            self.assertIsNotNone(persisted.deleted_at)
            self.assertEqual(persisted.revision, 3)

    def test_storage_paths_include_jsonl_and_lance_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AnnotationStore(storage_root=Path(tmpdir), mirror_lance=False)
            paths = store.storage_paths("hf://datasets/lance-format/lerobot-xvla-soft-fold/data")

            self.assertTrue(paths["jsonl"].endswith("/annotations.jsonl"))
            self.assertTrue(paths["lance"].endswith("/annotations.lance"))
            self.assertTrue(paths["legacy_lance"].endswith("/annotations.lance"))
            self.assertTrue(paths["current_lance"].endswith("/annotations_current.lance"))
            self.assertTrue(paths["events_lance"].endswith("/annotation_events.lance"))
            self.assertTrue(paths["history"].endswith("/history.jsonl"))

    def test_legacy_lance_mirror_can_be_disabled_by_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                "os.environ",
                {"ROBOT_DATA_STUDIO_WRITE_LEGACY_ANNOTATIONS_LANCE": "0"},
            ):
                store = AnnotationStore(storage_root=Path(tmpdir), mirror_lance=False)

            self.assertFalse(store.write_legacy_lance_mirror)

    def test_persisted_jsonl_uses_schema_column_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AnnotationStore(storage_root=Path(tmpdir), mirror_lance=False)
            record = store.create(
                AnnotationCreate(
                    dataset_id="sample-xvla-soft-fold",
                    episode_index=1,
                    start_frame=0,
                    end_frame=5,
                    label_type="important_frame",
                    label_value="gripper_contact",
                )
            )
            jsonl_path = Path(store.storage_paths("sample-xvla-soft-fold")["jsonl"])
            row = json.loads(jsonl_path.read_text(encoding="utf-8").strip())

            self.assertEqual(row["annotation_id"], record.annotation_id)
            self.assertEqual(row["dataset_id"], "sample-xvla-soft-fold")
            self.assertEqual(row["source"], "human")
            self.assertEqual(row["review_status"], "pending")

    def test_current_lance_mirror_receives_active_records_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AnnotationStore(storage_root=Path(tmpdir), mirror_lance=False)
            first = store.create(
                AnnotationCreate(
                    dataset_id="dataset-a",
                    episode_index=0,
                    start_frame=0,
                    end_frame=3,
                    label_type="phase",
                    label_value="approach",
                )
            )
            second = store.create(
                AnnotationCreate(
                    dataset_id="dataset-a",
                    episode_index=0,
                    start_frame=4,
                    end_frame=8,
                    label_type="phase",
                    label_value="grasp",
                )
            )
            with patch.object(store, "_mirror_current_lance") as current_mirror:
                store.delete(first.annotation_id)

            mirrored_records = current_mirror.call_args.args[1]
            self.assertEqual([record.annotation_id for record in mirrored_records], [second.annotation_id])
            jsonl_path = Path(store.storage_paths("dataset-a")["jsonl"])
            rows = [
                json.loads(line)
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            deleted_rows = [row for row in rows if row["annotation_id"] == first.annotation_id]
            self.assertIsNotNone(deleted_rows[0]["deleted_at"])

    def test_annotation_store_records_history_jsonl_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            created = first_store.create(
                AnnotationCreate(
                    dataset_id="sample-xvla-soft-fold",
                    episode_index=4,
                    start_frame=10,
                    end_frame=20,
                    label_type="phase",
                    label_value="approach",
                    created_by="alice",
                )
            )
            updated = first_store.update(
                created.annotation_id,
                AnnotationUpdate(
                    label_value="grasp",
                    review_status=ReviewStatus.edited,
                    updated_by="bob",
                ),
            )
            self.assertIsNotNone(updated)
            deleted = first_store.delete(created.annotation_id)

            second_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            events = second_store.list_history(
                "sample-xvla-soft-fold",
                annotation_id=created.annotation_id,
            )
            history_path = Path(second_store.storage_paths("sample-xvla-soft-fold")["history"])
            rows = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertTrue(deleted)
            self.assertEqual([event.action for event in events], ["create", "update", "delete"])
            self.assertEqual([event.actor for event in events], ["alice", "bob", "local"])
            self.assertIsNone(events[0].before)
            self.assertEqual(events[0].after["label_value"], "approach")
            self.assertEqual(events[1].before["label_value"], "approach")
            self.assertEqual(events[1].after["label_value"], "grasp")
            self.assertEqual(events[2].before["label_value"], "grasp")
            self.assertIsNone(events[2].after)
            self.assertEqual([row["action"] for row in rows], ["create", "update", "delete"])

    def test_update_rejects_stale_expected_revision(self) -> None:
        store = AnnotationStore(persist=False)
        created = store.create(
            AnnotationCreate(
                dataset_id="dataset-a",
                episode_index=0,
                start_frame=0,
                end_frame=1,
                label_type="phase",
                label_value="start",
            )
        )

        updated = store.update(
            created.annotation_id,
            AnnotationUpdate(label_value="middle", expected_revision=1),
        )
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.revision, 2)
        with self.assertRaises(AnnotationConflictError):
            store.update(
                created.annotation_id,
                AnnotationUpdate(label_value="late", expected_revision=1),
            )

    def test_mark_applied_stamps_export_id_idempotently(self) -> None:
        store = AnnotationStore(persist=False)
        first = store.create(
            AnnotationCreate(
                dataset_id="dataset-a",
                episode_index=0,
                start_frame=0,
                end_frame=4,
                label_type="skill",
                label_value="approach",
                review_status=ReviewStatus.accepted,
            )
        )
        second = store.create(
            AnnotationCreate(
                dataset_id="dataset-a",
                episode_index=0,
                start_frame=4,
                end_frame=10,
                label_type="skill",
                label_value="grasp",
                review_status=ReviewStatus.accepted,
            )
        )

        updated = store.mark_applied(
            [first.annotation_id, second.annotation_id],
            export_id="export-001",
        )
        self.assertEqual(len(updated), 2)
        self.assertEqual({record.applied_export_id for record in updated}, {"export-001"})
        self.assertEqual({record.revision for record in updated}, {2})

        # Idempotent — second call with same export id is a no-op (no extra
        # revision bump, no extra history event).
        replay = store.mark_applied(
            [first.annotation_id, second.annotation_id],
            export_id="export-001",
        )
        self.assertEqual(replay, [])
        events = store.list_history("dataset-a", annotation_id=first.annotation_id)
        self.assertEqual([event.action for event in events], ["create", "apply"])

        # Re-marking with a different export id bumps revision again.
        rebumped = store.mark_applied([first.annotation_id], export_id="export-002")
        self.assertEqual(len(rebumped), 1)
        self.assertEqual(rebumped[0].applied_export_id, "export-002")
        self.assertEqual(rebumped[0].revision, 3)

        # Soft-deleted annotations are skipped silently.
        store.delete(second.annotation_id)
        skipped = store.mark_applied([second.annotation_id], export_id="export-003")
        self.assertEqual(skipped, [])

    def test_compact_dataset_prunes_tombstones_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            active = store.create(
                AnnotationCreate(
                    dataset_id="dataset-a",
                    episode_index=0,
                    start_frame=0,
                    end_frame=4,
                    label_type="skill",
                    label_value="approach",
                    review_status=ReviewStatus.accepted,
                )
            )
            deleted = store.create(
                AnnotationCreate(
                    dataset_id="dataset-a",
                    episode_index=0,
                    start_frame=5,
                    end_frame=9,
                    label_type="skill",
                    label_value="grasp_part",
                    review_status=ReviewStatus.accepted,
                )
            )
            store.delete(deleted.annotation_id)

            summary = store.compact_dataset("dataset-a")

            self.assertEqual(summary["active_records"], 1)
            self.assertEqual(summary["deleted_records_pruned"], 1)
            self.assertEqual(summary["history_events_after"], 0)
            reloaded = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            self.assertIsNotNone(reloaded.get(active.annotation_id))
            self.assertIsNone(reloaded.get(deleted.annotation_id))
            self.assertEqual(reloaded.list_history("dataset-a"), [])
            jsonl_path = Path(reloaded.storage_paths("dataset-a")["jsonl"])
            rows = [
                json.loads(line)
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([row["annotation_id"] for row in rows], [active.annotation_id])
            self.assertFalse(Path(reloaded.storage_paths("dataset-a")["history"]).exists())

    def test_compact_dataset_can_prune_applied_episode_deletions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            deletion = store.create(
                AnnotationCreate(
                    dataset_id="dataset-a",
                    episode_index=3,
                    start_frame=0,
                    end_frame=0,
                    label_type="episode_disposition",
                    label_value="deleted",
                    review_status=ReviewStatus.accepted,
                )
            )
            store.mark_applied([deletion.annotation_id], export_id="export-001")

            summary = store.compact_dataset(
                "dataset-a",
                drop_applied_episode_deletions=True,
            )

            self.assertEqual(summary["active_records"], 0)
            self.assertEqual(summary["applied_episode_deletions_pruned"], 1)
            self.assertEqual(store.applied_deleted_episode_indices("dataset-a"), set())

    def test_applied_export_id_persists_across_jsonl_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            created = first_store.create(
                AnnotationCreate(
                    dataset_id="dataset-a",
                    episode_index=0,
                    start_frame=0,
                    end_frame=4,
                    label_type="skill",
                    label_value="approach",
                    review_status=ReviewStatus.accepted,
                )
            )
            first_store.mark_applied([created.annotation_id], export_id="export-roundtrip")

            second_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            reloaded = second_store.get(created.annotation_id)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.applied_export_id, "export-roundtrip")

    def test_legacy_jsonl_without_applied_export_id_loads_as_null(self) -> None:
        # Pre-Phase-2 JSONL rows do not carry the new column; pydantic's default
        # must surface them as None so existing datasets keep loading.
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            dataset_dir = storage_root / "dataset-a-deadbeef0001"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            legacy_row = {
                "annotation_id": "legacy-row",
                "dataset_id": "dataset-a",
                "episode_index": 0,
                "start_frame": 0,
                "end_frame": 4,
                "label_type": "skill",
                "label_value": "approach",
                "source": "human",
                "confidence": 1.0,
                "review_status": "accepted",
                "metadata": {},
                "created_by": "local",
                "updated_by": "local",
                "assigned_to": None,
                "revision": 1,
                "deleted_at": None,
                "lock_owner": None,
                "lock_expires_at": None,
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
            (dataset_dir / "annotations.jsonl").write_text(
                json.dumps(legacy_row) + "\n", encoding="utf-8"
            )
            store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            loaded = store.get("legacy-row")
            self.assertIsNotNone(loaded)
            self.assertIsNone(loaded.applied_export_id)

    def test_review_and_assignment_actions_are_specific(self) -> None:
        store = AnnotationStore(persist=False)
        created = store.create(
            AnnotationCreate(
                dataset_id="dataset-a",
                episode_index=0,
                start_frame=0,
                end_frame=1,
                label_type="phase",
                label_value="start",
            )
        )

        store.update(
            created.annotation_id,
            AnnotationUpdate(review_status=ReviewStatus.accepted),
        )
        store.update(
            created.annotation_id,
            AnnotationUpdate(assigned_to="alice"),
            action="assign",
        )
        events = store.list_history("dataset-a", annotation_id=created.annotation_id)

        self.assertEqual([event.action for event in events], ["create", "accept", "assign"])

    def test_applied_deleted_episode_disposition_cannot_be_cleared(self) -> None:
        store = AnnotationStore(persist=False)
        created = store.upsert_episode_disposition(
            dataset_id="dataset-a",
            episode_index=2,
            disposition="deleted",
            reason=None,
            actor="local",
        )
        self.assertIsNotNone(created)
        records = store.list("dataset-a", episode_index=2)
        store.mark_applied([records[0].annotation_id], export_id="export-001")

        cleared = store.upsert_episode_disposition(
            dataset_id="dataset-a",
            episode_index=2,
            disposition=None,
            reason=None,
            actor="local",
        )

        self.assertEqual(cleared["disposition"], "deleted")
        self.assertEqual(cleared["applied_export_id"], "export-001")
        self.assertEqual(store.applied_deleted_episode_indices("dataset-a"), {2})


if __name__ == "__main__":
    unittest.main()
