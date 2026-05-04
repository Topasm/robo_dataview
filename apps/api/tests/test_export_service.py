from __future__ import annotations

import json
import unittest
from pathlib import Path

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.common import ExportFormat, JobStatus, ReviewStatus
from apps.api.schemas.exports import ExportCreateRequest
from apps.api.services.annotation_service import annotation_store
from apps.api.services import export_service
from apps.api.services.export_service import ExportStore
from apps.api.services.version_service import VersionStore


class ExportServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_export_root = export_service.EXPORT_ROOT
        self.export_root = Path("/tmp/robot-data-studio-test-exports")
        self.version_root = Path("/tmp/robot-data-studio-test-versions")
        export_service.EXPORT_ROOT = self.export_root

    def tearDown(self) -> None:
        export_service.EXPORT_ROOT = self.previous_export_root
        if self.export_root.exists():
            for path in sorted(self.export_root.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            self.export_root.rmdir()
        if self.version_root.exists():
            for path in sorted(self.version_root.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            self.version_root.rmdir()

    def test_create_writes_manifest_with_accepted_annotations_only(self) -> None:
        accepted = annotation_store.create(
            AnnotationCreate(
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                start_frame=0,
                end_frame=10,
                label_type="phase",
                label_value="accepted_phase",
                review_status=ReviewStatus.accepted,
            )
        )
        rejected = annotation_store.create(
            AnnotationCreate(
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                start_frame=11,
                end_frame=20,
                label_type="phase",
                label_value="rejected_phase",
                review_status=ReviewStatus.rejected,
            )
        )

        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)
        record = exports.create(
            ExportCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
                format=ExportFormat.lerobot,
                version_description="test export",
            )
        )
        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        annotation_values = [
            annotation["label_value"]
            for episode in manifest["episodes"]
            for annotation in episode["annotations"]
        ]
        lerobot_artifact = manifest["artifacts"]["lerobot_v3"]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(manifest["num_episodes"], 1)
        self.assertIsNotNone(record.artifacts)
        self.assertEqual(lerobot_artifact["materialization_status"], "metadata_only")
        self.assertTrue(lerobot_artifact["validation"]["metadata_ok"])
        self.assertTrue(Path(lerobot_artifact["files"]["info"]).exists())
        self.assertTrue(Path(lerobot_artifact["files"]["episodes_jsonl"]).exists())
        self.assertTrue(Path(lerobot_artifact["files"]["annotations"]).exists())
        self.assertIn("accepted_phase", annotation_values)
        self.assertNotIn("rejected_phase", annotation_values)
        version_records = versions.list("sample-xvla-soft-fold")
        self.assertEqual([version.version_id for version in version_records], [record.export_id])
        self.assertEqual(version_records[0].num_episodes, 1)
        self.assertEqual(version_records[0].num_frames, 180)

        annotation_store.delete(accepted.annotation_id)
        annotation_store.delete(rejected.annotation_id)

    def test_export_record_can_be_loaded_from_existing_manifest(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        first_store = ExportStore(versions=versions)
        created = first_store.create(
            ExportCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0, 2],
                format=ExportFormat.lerobot,
                version_description="restart-safe export",
            )
        )

        second_store = ExportStore(versions=versions)
        loaded = second_store.get(created.export_id)

        self.assertEqual(loaded.export_id, created.export_id)
        self.assertEqual(loaded.status, JobStatus.succeeded)
        self.assertEqual(loaded.episode_indices, [0, 2])
        self.assertEqual(loaded.output_uri, created.output_uri)
        self.assertEqual(loaded.artifacts, created.artifacts)


if __name__ == "__main__":
    unittest.main()
