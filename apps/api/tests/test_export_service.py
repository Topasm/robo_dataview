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
from apps.api.services.hf_dataset_export import validate_hf_dataset_export
from apps.api.services.version_service import VersionStore


class ExportServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_export_root = export_service.EXPORT_ROOT
        self.export_root = Path("/tmp/robot-data-studio-test-exports")
        self.version_root = Path("/tmp/robot-data-studio-test-versions")
        export_service.EXPORT_ROOT = self.export_root
        self._delete_test_annotations()

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

    def _delete_test_annotations(self) -> None:
        test_values = {
            "accepted_phase",
            "rejected_phase",
            "accepted_exact_frame",
            "rejected_exact_frame",
            "jsonl_phase",
        }
        for annotation in annotation_store.list("sample-xvla-soft-fold", episode_index=0):
            if annotation.label_value in test_values:
                annotation_store.delete(annotation.annotation_id)

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

    def test_export_without_explicit_indices_paginates_all_split_pages(self) -> None:
        episodes = [
            EpisodeDetail(
                dataset_id="split-dataset",
                episode_index=index,
                task_index=1,
                length=10,
                split="train",
                fps=20.0,
                camera_names=[],
            )
            for index in range(1000)
        ]
        episodes.append(
            EpisodeDetail(
                dataset_id="split-dataset",
                episode_index=1000,
                task_index=1,
                length=11,
                split="val",
                fps=20.0,
                camera_names=[],
            )
        )
        fake_store = _FakeSplitStore(episodes)
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

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(record.episode_indices, [1000])
        self.assertGreaterEqual(fake_store.list_calls, 2)

    def test_hf_dataset_export_fails_when_dependency_is_missing(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.dict(sys.modules, {"datasets": None}):
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
        self.assertIn("optional `datasets` dependency", record.message or "")

    def test_hf_dataset_export_writes_saved_dataset_artifact(self) -> None:
        fake_datasets = _fake_datasets_module()
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.dict(sys.modules, {"datasets": fake_datasets}):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    format=ExportFormat.hf_dataset,
                    version_description="hf dataset export",
                )
            )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        artifact = manifest["artifacts"]["hf_dataset"]
        frames = [
            json.loads(line)
            for line in Path(artifact["files"]["frames_jsonl"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(artifact["materialized"]["episode_rows"], 1)
        self.assertEqual(artifact["materialized"]["frame_rows"], 180)
        self.assertEqual(artifact["validation"]["metadata_ok"], True)
        self.assertEqual(artifact["validation"]["load"]["num_rows"], 180)
        self.assertTrue(Path(artifact["files"]["dataset"]).exists())
        self.assertEqual(frames[0]["episode_index"], 0)
        self.assertEqual(frames[0]["frame_index"], 0)
        self.assertIn("observation_state", frames[0])
        self.assertEqual(versions.list("sample-xvla-soft-fold")[0].export_format, "hf_dataset")

    def test_hf_dataset_validation_rejects_corrupt_metadata_contract(self) -> None:
        fake_datasets = _fake_datasets_module()
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.dict(sys.modules, {"datasets": fake_datasets}):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    format=ExportFormat.hf_dataset,
                    version_description="hf dataset export",
                )
            )

            manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
            artifact = manifest["artifacts"]["hf_dataset"]
            metadata_path = Path(artifact["files"]["metadata"])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["format"] = "wrong-format"
            metadata["frame_rows"] = 1
            metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

            validation = validate_hf_dataset_export(Path(artifact["root"]), expected_frame_rows=180)

        self.assertFalse(validation["metadata_ok"])
        self.assertIn("metadata format does not match HF Dataset export format", validation["errors"])
        self.assertIn("metadata frame_rows does not match frames.jsonl row count", validation["errors"])
        self.assertIn("metadata frame_rows does not match expected frame count", validation["errors"])

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
        self.assertEqual(artifact["materialized"]["media_rows"], 0)
        self.assertEqual(artifact["materialized"]["train_episode_rows"], 1)
        self.assertNotIn("video_rows", artifact["materialized"])
        self.assertEqual(artifact["materialized"]["annotation_current_rows"], 1)
        self.assertEqual(artifact["materialized"]["annotation_event_rows"], 0)
        self.assertNotIn("annotation_rows", artifact["materialized"])
        self.assertTrue(artifact["validation"]["metadata_ok"])
        self.assertEqual(artifact["validation"]["table_readability"]["episodes"]["row_count"], 1)
        self.assertEqual(artifact["validation"]["table_readability"]["frames"]["row_count"], 180)
        self.assertEqual(artifact["validation"]["table_readability"]["media"]["row_count"], 0)
        self.assertEqual(
            artifact["validation"]["table_readability"]["train_episodes"]["row_count"],
            1,
        )
        self.assertEqual(
            artifact["validation"]["table_readability"]["annotations_current"]["row_count"],
            1,
        )
        self.assertEqual(
            artifact["validation"]["table_readability"]["annotation_events"]["row_count"],
            0,
        )
        self.assertFalse(artifact["validation"]["present"]["videos"])
        self.assertFalse(artifact["validation"]["present"]["annotations"])
        self.assertTrue(Path(artifact["files"]["episodes"]).exists())
        self.assertTrue(Path(artifact["files"]["frames"]).exists())
        self.assertTrue(Path(artifact["files"]["media"]).exists())
        self.assertTrue(Path(artifact["files"]["train_episodes"]).exists())
        self.assertTrue(Path(artifact["files"]["annotations_current"]).exists())
        self.assertTrue(Path(artifact["files"]["annotation_events"]).exists())
        self.assertNotIn("videos", artifact["files"])
        self.assertNotIn("annotations", artifact["files"])
        self.assertTrue(Path(artifact["files"]["manifest"]).exists())
        self.assertTrue(artifact["validation"]["present"]["manifest"])
        self.assertEqual(len(written_paths), 6)
        exported_manifest = json.loads(
            Path(artifact["files"]["manifest"]).read_text(encoding="utf-8")
        )
        metadata = json.loads(Path(artifact["files"]["metadata"]).read_text(encoding="utf-8"))
        self.assertEqual(exported_manifest, metadata)
        self.assertEqual(metadata["primary_training_table"], "train_episodes.lance")
        self.assertEqual(metadata["training_columns"]["state"], "observation_state")
        self.assertEqual(metadata["training_columns"]["action"], "actions")
        self.assertEqual(metadata["blob_storage"]["episodes"], "metadata_only")
        self.assertEqual(metadata["blob_storage"]["media"], "metadata_only")
        self.assertGreater(metadata["state_dim"], 0)
        self.assertGreater(metadata["action_dim"], 0)
        self.assertEqual(metadata["frame_table"]["index_columns"], ["episode_index", "frame_index"])
        self.assertEqual(metadata["frame_table"]["state_column"], "observation_state")
        self.assertEqual(metadata["frame_table"]["action_column"], "action")
        self.assertTrue(metadata["frame_table"]["state_dim_consistent"])
        self.assertTrue(metadata["frame_table"]["action_dim_consistent"])
        written_tables = getattr(written_paths, "tables", {})
        episode_rows = written_tables[str(Path(artifact["files"]["episodes"]))]["rows"]
        train_episode_rows = written_tables[str(Path(artifact["files"]["train_episodes"]))]["rows"]
        self.assertEqual(len(episode_rows), 1)
        self.assertEqual(len(train_episode_rows), 1)
        self.assertNotIn("timestamps", episode_rows[0])
        self.assertNotIn("observation_state", episode_rows[0])
        self.assertNotIn("actions", episode_rows[0])
        self.assertIn("timestamps", train_episode_rows[0])
        self.assertIn("observation_state", train_episode_rows[0])
        self.assertIn("actions", train_episode_rows[0])
        self.assertEqual(
            manifest["episodes"][0]["annotations"][0]["label_value"],
            "accepted_exact_frame",
        )
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
        self.assertEqual(artifact["materialized"]["media_rows"], 1)
        self.assertNotIn("video_rows", artifact["materialized"])
        self.assertEqual(artifact["validation"]["media_count"], 1)
        self.assertEqual(artifact["validation"]["video_count"], 0)
        self.assertTrue(Path(artifact["files"]["media"]).exists())
        self.assertNotIn("videos", artifact["files"])
        self.assertTrue(any(path.endswith("media.lance") for path in written_paths))
        self.assertTrue(any(path.endswith("train_episodes.lance") for path in written_paths))
        self.assertFalse(any(path.endswith("videos.lance") for path in written_paths))
        metadata = json.loads(Path(artifact["files"]["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["camera_keys"], ["cam_high"])
        self.assertEqual(metadata["blob_storage"]["media"], "metadata_only")
        written_tables = getattr(written_paths, "tables", {})
        media_rows = written_tables[str(Path(artifact["files"]["media"]))]["rows"]
        train_episode_rows = written_tables[str(Path(artifact["files"]["train_episodes"]))]["rows"]
        self.assertEqual(media_rows[0]["byte_size"], len(b"video-bytes"))
        self.assertIsNone(media_rows[0]["video_blob"])
        self.assertEqual(train_episode_rows[0]["cam_high_video_blob"], b"video-bytes")

    def test_lance_export_materializes_accepted_skill_clips(self) -> None:
        skill = annotation_store.create(
            AnnotationCreate(
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                start_frame=3,
                end_frame=7,
                label_type="skill",
                label_value="approach",
                review_status=ReviewStatus.accepted,
                metadata={"skillId": 0, "qualityScore": 1.0, "successLabel": True},
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
                    materialize_skill_clips=True,
                )
            )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        artifact = manifest["artifacts"]["lance_subset"]
        metadata = json.loads(Path(artifact["files"]["manifest"]).read_text(encoding="utf-8"))
        written_tables = getattr(written_paths, "tables", {})
        skill_rows = written_tables[str(Path(artifact["files"]["skill_segments"]))]["rows"]
        train_clip_rows = written_tables[str(Path(artifact["files"]["train_skill_clips"]))]["rows"]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(metadata["primary_training_table"], "train_skill_clips.lance")
        self.assertEqual(metadata["total_skill_segments"], 1)
        self.assertEqual(metadata["total_train_skill_clips"], 1)
        self.assertEqual(metadata["clip_export"]["train_skill_clips"], 1)
        self.assertEqual(artifact["validation"]["train_skill_clip_count"], 1)
        self.assertEqual(skill_rows[0]["clip_id"], skill.annotation_id)
        self.assertEqual(train_clip_rows[0]["clip_id"], skill.annotation_id)
        self.assertEqual(train_clip_rows[0]["source_episode_index"], 0)
        self.assertEqual(train_clip_rows[0]["episode_index"], 0)
        self.assertEqual(train_clip_rows[0]["length"], 5)
        self.assertEqual(train_clip_rows[0]["video_frame_offset"], 3)

        annotation_store.delete(skill.annotation_id)

    def test_lance_export_fails_when_validation_fails(self) -> None:
        fake_pyarrow = _fake_pyarrow_module()
        fake_lance, _written_paths = _fake_lance_module(row_count_overrides={"frames": 2})
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
                    version_description="bad lance subset",
                )
            )

        self.assertEqual(record.status, JobStatus.failed)
        self.assertIsNone(record.output_uri)
        self.assertIn("Lance subset export validation failed", record.message or "")
        self.assertIn("frames.lance row count 2 does not match expected 180", record.message or "")
        self.assertIsNotNone(record.artifacts)
        assert record.artifacts is not None
        self.assertFalse(record.artifacts["lance_subset"]["validation"]["metadata_ok"])
        self.assertEqual(versions.list("sample-xvla-soft-fold"), [])

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

    def test_export_can_publish_artifacts_to_fsspec_destination(self) -> None:
        fake_fs = _FakePublishFs()
        fake_fsspec = _fake_fsspec_module(fake_fs)
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.dict(sys.modules, fake_fsspec):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    format=ExportFormat.jsonl,
                    version_description="published jsonl export",
                    publish_uri="s3://bucket/robot-data/export-1",
                )
            )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))
        publish = manifest["artifacts"]["publish"]
        remote_manifest = json.loads(
            fake_fs.files["bucket/robot-data/export-1/manifest.json"].decode("utf-8")
        )

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(publish["destination_uri"], "s3://bucket/robot-data/export-1")
        self.assertEqual(publish["manifest_uri"], "s3://bucket/robot-data/export-1/manifest.json")
        self.assertGreaterEqual(publish["file_count"], 3)
        self.assertIn("bucket/robot-data/export-1/jsonl_export/episodes.jsonl", fake_fs.files)
        self.assertIn("bucket/robot-data/export-1/jsonl_export/captions.jsonl", fake_fs.files)
        self.assertEqual(
            remote_manifest["artifacts"]["publish"]["manifest_uri"],
            "s3://bucket/robot-data/export-1/manifest.json",
        )

    def test_export_fails_clearly_when_publish_dependency_is_missing(self) -> None:
        versions = VersionStore(storage_root=self.version_root, mirror_lance=False)
        exports = ExportStore(versions=versions)

        with patch.dict(sys.modules, {"fsspec": None, "fsspec.core": None}):
            record = exports.create(
                ExportCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    format=ExportFormat.jsonl,
                    version_description="published jsonl export",
                    publish_uri="s3://bucket/robot-data/export-1",
                )
            )

        manifest = json.loads(Path(record.output_uri or "").read_text(encoding="utf-8"))

        self.assertEqual(record.status, JobStatus.failed)
        self.assertIn("Publishing to remote object storage requires optional `fsspec`", record.message or "")
        self.assertFalse(manifest["artifacts"]["publish"]["metadata_ok"])
        self.assertEqual(versions.list("sample-xvla-soft-fold"), [])

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
    module.float64 = lambda: "float64"
    module.float32 = lambda: "float32"
    module.bool_ = lambda: "bool"
    module.binary = lambda: "binary"
    module.large_binary = lambda: "large_binary"
    module.list_ = lambda dtype: f"list<{dtype}>"
    module.timestamp = lambda unit, tz=None: f"timestamp<{unit},{tz}>"
    return module


class _FakeLanceDataset:
    def __init__(self, row_count: int) -> None:
        self._row_count = row_count

    def count_rows(self) -> int:
        return self._row_count


class _WrittenPaths(list[str]):
    def __init__(self) -> None:
        super().__init__()
        self.tables: dict[str, dict] = {}


def _fake_lance_module(
    row_count_overrides: dict[str, int] | None = None,
) -> tuple[ModuleType, list[str]]:
    module = ModuleType("lance")
    written_paths = _WrittenPaths()
    row_counts: dict[str, int] = {}
    row_count_overrides = row_count_overrides or {}

    def write_dataset(table: object, path: str, mode: str = "overwrite") -> None:
        del mode
        path_obj = Path(path)
        path_obj.mkdir(parents=True, exist_ok=True)
        (path_obj / "_SUCCESS").write_text("ok", encoding="utf-8")
        written_paths.append(path)
        written_paths.tables[path] = table
        key = path_obj.name.removesuffix(".lance")
        row_counts[str(path_obj)] = int(row_count_overrides.get(key, len(table["rows"])))

    def dataset(path: str) -> _FakeLanceDataset:
        if path not in row_counts:
            raise FileNotFoundError(path)
        return _FakeLanceDataset(row_counts[path])

    module.dataset = dataset
    module.write_dataset = write_dataset
    return module, written_paths


def _fake_datasets_module() -> ModuleType:
    module = ModuleType("datasets")

    class Dataset:
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def __len__(self) -> int:
            return len(self.rows)

        @classmethod
        def from_list(cls, rows: list[dict]) -> "Dataset":
            return cls(rows)

        def save_to_disk(self, path: str) -> None:
            root = Path(path)
            root.mkdir(parents=True, exist_ok=True)
            (root / "dataset_info.json").write_text(
                json.dumps({"num_rows": len(self.rows)}, sort_keys=True),
                encoding="utf-8",
            )
            (root / "state.json").write_text(
                json.dumps({"data_files": [{"filename": "data.jsonl"}]}, sort_keys=True),
                encoding="utf-8",
            )
            (root / "data.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in self.rows),
                encoding="utf-8",
            )

    def load_from_disk(path: str) -> Dataset:
        data_path = Path(path) / "data.jsonl"
        rows = [
            json.loads(line)
            for line in data_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return Dataset(rows)

    module.Dataset = Dataset
    module.load_from_disk = load_from_disk
    return module


class _FakePublishHandle:
    def __init__(self, fs: "_FakePublishFs", path: str) -> None:
        self.fs = fs
        self.path = path
        self.buffer = bytearray()

    def __enter__(self) -> "_FakePublishHandle":
        return self

    def __exit__(self, *args: object) -> None:
        self.fs.files[self.path] = bytes(self.buffer)

    def write(self, value: bytes) -> int:
        self.buffer.extend(value)
        return len(value)


class _FakePublishFs:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.directories: list[str] = []

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        del exist_ok
        self.directories.append(path)

    def open(self, path: str, mode: str) -> _FakePublishHandle:
        self.assert_write_mode(mode)
        return _FakePublishHandle(self, path)

    @staticmethod
    def assert_write_mode(mode: str) -> None:
        if mode != "wb":
            raise AssertionError(f"unexpected mode: {mode}")


def _fake_fsspec_module(fs: _FakePublishFs) -> dict[str, ModuleType]:
    fsspec_module = ModuleType("fsspec")
    core_module = ModuleType("fsspec.core")
    core_module.url_to_fs = lambda uri: (fs, uri.removeprefix("s3://"))
    return {
        "fsspec": fsspec_module,
        "fsspec.core": core_module,
    }


class _FakeSplitStore:
    def __init__(self, episodes: list[EpisodeDetail] | None = None) -> None:
        self.episodes = episodes or [
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
        self.list_calls = 0

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[EpisodeDetail]:
        self.list_calls += 1
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
