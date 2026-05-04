from __future__ import annotations

import json
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
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
        self.assertIn(lerobot_artifact["materialization_status"], {"data_jsonl", "parquet"})
        self.assertEqual(lerobot_artifact["materialized"]["frame_rows"], 180)
        self.assertTrue(lerobot_artifact["validation"]["metadata_ok"])
        self.assertTrue(Path(lerobot_artifact["files"]["info"]).exists())
        self.assertTrue(Path(lerobot_artifact["files"]["data_jsonl"]).exists())
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

    def test_lance_export_fails_when_dependencies_are_missing(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.dict(sys.modules, {"pyarrow": None, "lance": None}):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    format=ExportFormat.lance,
                    version_description="missing deps",
                )
            )

        self.assertEqual(record.status, JobStatus.failed)
        self.assertIsNone(record.output_uri)
        self.assertIn("optional pyarrow and lance", record.message or "")

    def test_lance_export_writes_subset_artifact(self) -> None:
        accepted = annotation_store.create(
            AnnotationCreate(
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                start_frame=1,
                end_frame=1,
                label_type="important_frame",
                label_value="accepted_exact_frame",
                review_status=ReviewStatus.accepted,
            )
        )
        rejected = annotation_store.create(
            AnnotationCreate(
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                start_frame=2,
                end_frame=2,
                label_type="occlusion",
                label_value="rejected_exact_frame",
                review_status=ReviewStatus.rejected,
            )
        )
        fake_pyarrow = _fake_pyarrow_module()
        fake_lance, written_paths = _fake_lance_module()

        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)
        with patch.dict(
            sys.modules,
            {"pyarrow": fake_pyarrow, "lance": fake_lance},
        ):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    format=ExportFormat.lance,
                    version_description="lance subset",
                )
            )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        artifact = manifest["artifacts"]["lance_subset"]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(artifact["materialized"]["episode_rows"], 1)
        self.assertEqual(artifact["materialized"]["frame_rows"], 180)
        self.assertEqual(artifact["materialized"]["annotation_rows"], 1)
        self.assertTrue(artifact["validation"]["metadata_ok"])
        self.assertTrue(Path(artifact["files"]["episodes"]).exists())
        self.assertTrue(Path(artifact["files"]["frames"]).exists())
        self.assertTrue(Path(artifact["files"]["annotations"]).exists())
        self.assertEqual(len(written_paths), 3)
        self.assertEqual(manifest["episodes"][0]["annotations"][0]["label_value"], "accepted_exact_frame")
        version_records = versions.list("sample-xvla-soft-fold")
        self.assertEqual(version_records[0].export_format, "lance")

        annotation_store.delete(accepted.annotation_id)
        annotation_store.delete(rejected.annotation_id)

    def test_jsonl_export_writes_caption_and_annotation_files(self) -> None:
        accepted = annotation_store.create(
            AnnotationCreate(
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                start_frame=0,
                end_frame=10,
                label_type="phase",
                label_value="jsonl_phase",
                review_status=ReviewStatus.accepted,
            )
        )
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        record = exports.create(
            ExportCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
                format=ExportFormat.jsonl,
                version_description="jsonl export",
            )
        )
        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        artifact = manifest["artifacts"]["jsonl"]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(artifact["materialized"]["episode_rows"], 1)
        self.assertEqual(artifact["materialized"]["caption_rows"], 1)
        self.assertEqual(artifact["materialized"]["annotation_rows"], 1)
        self.assertTrue(Path(artifact["files"]["episodes"]).exists())
        self.assertTrue(Path(artifact["files"]["captions"]).exists())
        self.assertTrue(Path(artifact["files"]["annotations"]).exists())
        self.assertEqual(versions.list("sample-xvla-soft-fold")[0].export_format, "jsonl")

        annotation_store.delete(accepted.annotation_id)

    def test_vla_export_writes_timeseries_examples(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        record = exports.create(
            ExportCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
                format=ExportFormat.vla,
                version_description="vla export",
            )
        )
        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        artifact = manifest["artifacts"]["vla_jsonl"]
        examples = [
            json.loads(line)
            for line in Path(artifact["files"]["examples"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(artifact["materialized"]["example_rows"], 1)
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["episode_index"], 0)
        self.assertEqual(len(examples[0]["action"]), 180)
        self.assertEqual(versions.list("sample-xvla-soft-fold")[0].export_format, "vla")


class _FakeTable:
    @staticmethod
    def from_pylist(rows: list[dict], schema: object | None = None) -> dict:
        return {"rows": rows, "schema": schema}


def _fake_pyarrow_module() -> ModuleType:
    module = ModuleType("pyarrow")
    module.Table = _FakeTable
    module.schema = lambda fields, metadata=None: {"fields": fields, "metadata": metadata}
    module.field = lambda name, dtype, nullable=True: {
        "name": name,
        "dtype": dtype,
        "nullable": nullable,
    }
    module.string = lambda: "string"
    module.int64 = lambda: "int64"
    module.float32 = lambda: "float32"
    module.bool_ = lambda: "bool"
    module.list_ = lambda dtype: f"list<{dtype}>"
    module.timestamp = lambda unit, tz=None: f"timestamp<{unit},{tz}>"
    return module


def _fake_lance_module() -> tuple[ModuleType, list[str]]:
    module = ModuleType("lance")
    written_paths: list[str] = []

    def write_dataset(table: object, path: str, mode: str = "overwrite") -> None:
        del table, mode
        path_obj = Path(path)
        path_obj.mkdir(parents=True, exist_ok=True)
        (path_obj / "_SUCCESS").write_text("ok", encoding="utf-8")
        written_paths.append(path)

    module.write_dataset = write_dataset
    return module, written_paths


if __name__ == "__main__":
    unittest.main()
