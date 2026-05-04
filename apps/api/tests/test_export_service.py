from __future__ import annotations

import json
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from pathlib import Path

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.common import ExportFormat, JobStatus, ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.exports import ExportCreateRequest
from apps.api.schemas.frames import FrameRecord
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

    def test_export_without_explicit_indices_can_filter_by_split(self) -> None:
        fake_store = _FakeSplitStore()
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.object(export_service, "store", fake_store):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="split-dataset",
                    splits=["val"],
                    format=ExportFormat.jsonl,
                    version_description="val split export",
                )
            )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(record.episode_indices, [1])
        self.assertEqual(manifest["episode_indices"], [1])
        self.assertEqual(manifest["splits"], ["val"])
        self.assertEqual(manifest["episodes"][0]["split"], "val")

    def test_hf_dataset_export_fails_until_implemented(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        record = exports.create(
            ExportCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
                format=ExportFormat.hf_dataset,
                version_description="hf dataset export",
            )
        )

        self.assertEqual(record.status, JobStatus.failed)
        self.assertIsNone(record.output_uri)
        self.assertIn("Hugging Face Dataset export is not implemented", record.message or "")

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

    def test_lerobot_export_fails_when_validation_fails(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.object(export_service, "store", _FakeInvalidVideoStore()):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="invalid-video-dataset",
                    episode_indices=[0],
                    format=ExportFormat.lerobot,
                    version_description="invalid video export",
                )
            )

        self.assertEqual(record.status, JobStatus.failed)
        self.assertIsNone(record.output_uri)
        self.assertIn("LeRobot export validation failed", record.message or "")
        self.assertIn("invalid MP4 files", record.message or "")
        self.assertIsNotNone(record.artifacts)
        assert record.artifacts is not None
        self.assertFalse(record.artifacts["lerobot_v3"]["validation"]["metadata_ok"])
        self.assertEqual(versions.list("invalid-video-dataset"), [])

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
        self.assertEqual(artifact["materialized"]["video_rows"], 0)
        self.assertEqual(artifact["materialized"]["annotation_rows"], 1)
        self.assertTrue(artifact["validation"]["metadata_ok"])
        self.assertTrue(Path(artifact["files"]["episodes"]).exists())
        self.assertTrue(Path(artifact["files"]["frames"]).exists())
        self.assertTrue(Path(artifact["files"]["videos"]).exists())
        self.assertTrue(Path(artifact["files"]["annotations"]).exists())
        self.assertEqual(len(written_paths), 4)
        self.assertEqual(manifest["episodes"][0]["annotations"][0]["label_value"], "accepted_exact_frame")
        version_records = versions.list("sample-xvla-soft-fold")
        self.assertEqual(version_records[0].export_format, "lance")

        annotation_store.delete(accepted.annotation_id)
        annotation_store.delete(rejected.annotation_id)

    def test_lance_export_writes_video_table_when_blobs_are_available(self) -> None:
        fake_pyarrow = _fake_pyarrow_module()
        fake_lance, written_paths = _fake_lance_module()
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.object(export_service, "store", _FakeLanceVideoStore()):
            with patch.dict(
                sys.modules,
                {"pyarrow": fake_pyarrow, "lance": fake_lance},
            ):
                record = exports.create(
                    ExportCreateRequest(
                        dataset_id="lance-video-dataset",
                        episode_indices=[7],
                        format=ExportFormat.lance,
                        version_description="lance video subset",
                    )
                )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        artifact = manifest["artifacts"]["lance_subset"]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(artifact["materialized"]["video_rows"], 1)
        self.assertEqual(artifact["validation"]["video_count"], 1)
        self.assertTrue(Path(artifact["files"]["videos"]).exists())
        self.assertTrue(any(path.endswith("videos.lance") for path in written_paths))

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
    module.binary = lambda: "binary"
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


class _FakeSplitStore:
    def __init__(self) -> None:
        self.episodes = [
            EpisodeDetail(
                dataset_id="split-dataset",
                episode_index=0,
                task_index=1,
                length=10,
                split="train",
                fps=20.0,
                camera_names=[],
            ),
            EpisodeDetail(
                dataset_id="split-dataset",
                episode_index=1,
                task_index=1,
                length=11,
                split="val",
                fps=20.0,
                camera_names=[],
            ),
            EpisodeDetail(
                dataset_id="split-dataset",
                episode_index=2,
                task_index=1,
                length=12,
                split="test",
                fps=20.0,
                camera_names=[],
            ),
        ]

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[EpisodeDetail]:
        if dataset_id != "split-dataset":
            return []
        return self.episodes[offset : offset + limit]

    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        if dataset_id != "split-dataset":
            return None
        return next(
            (episode for episode in self.episodes if episode.episode_index == episode_index),
            None,
        )


class _FakeInvalidVideoStore:
    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        if dataset_id != "invalid-video-dataset" or episode_index != 0:
            return None
        return EpisodeDetail(
            dataset_id=dataset_id,
            episode_index=0,
            task_index=1,
            length=1,
            fps=20.0,
            camera_names=["cam_high"],
        )

    def get_episode_timeseries(self, dataset_id: str, episode_index: int) -> dict | None:
        if dataset_id != "invalid-video-dataset" or episode_index != 0:
            return None
        return {
            "timestamps": [0.0],
            "states": [[0.0, 0.0]],
            "actions": [[1.0, 1.0]],
        }

    def get_video_blob(self, dataset_id: str, episode_index: int, camera: str) -> bytes | None:
        if dataset_id == "invalid-video-dataset" and episode_index == 0 and camera == "cam_high":
            return b"not an mp4"
        return None


class _FakeLanceVideoStore:
    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        if dataset_id != "lance-video-dataset" or episode_index != 7:
            return None
        return EpisodeDetail(
            dataset_id=dataset_id,
            episode_index=7,
            task_index=1,
            length=1,
            fps=20.0,
            camera_names=["cam high"],
        )

    def list_frames(
        self,
        dataset_id: str,
        episode_index: int,
        *,
        start_frame: int,
        end_frame: int | None,
        limit: int,
    ) -> list[FrameRecord]:
        del start_frame, end_frame, limit
        if dataset_id != "lance-video-dataset" or episode_index != 7:
            return []
        return [
            FrameRecord(
                dataset_id=dataset_id,
                episode_index=episode_index,
                frame_index=0,
                timestamp=0.0,
                task_index=1,
                observation_state=[0.0, 0.0],
                action=[1.0, 1.0],
                state_norm=0.0,
                action_norm=1.4,
                is_bad_frame=False,
            )
        ]

    def get_video_blob(self, dataset_id: str, episode_index: int, camera: str) -> bytes | None:
        if dataset_id == "lance-video-dataset" and episode_index == 7 and camera == "cam high":
            return b"video-bytes"
        return None


if __name__ == "__main__":
    unittest.main()
