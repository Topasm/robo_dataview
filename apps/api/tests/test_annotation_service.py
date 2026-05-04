from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from apps.api.schemas.annotations import AnnotationCreate, AnnotationUpdate
from apps.api.schemas.common import ReviewStatus
from apps.api.services.annotation_service import AnnotationStore


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

            third_store.delete(created.annotation_id)
            fourth_store = AnnotationStore(storage_root=storage_root, mirror_lance=False)
            self.assertEqual(fourth_store.list("sample-xvla-soft-fold", episode_index=0), [])

    def test_storage_paths_include_jsonl_and_lance_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AnnotationStore(storage_root=Path(tmpdir), mirror_lance=False)
            paths = store.storage_paths("hf://datasets/lance-format/lerobot-xvla-soft-fold/data")

            self.assertTrue(paths["jsonl"].endswith("/annotations.jsonl"))
            self.assertTrue(paths["lance"].endswith("/annotations.lance"))
            self.assertTrue(paths["history"].endswith("/history.jsonl"))

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


if __name__ == "__main__":
    unittest.main()
