from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import lance
import pyarrow as pa

from apps.api.schemas.common import ExportFormat, JobStatus
from apps.api.schemas.datasets import DatasetOpenRequest
from apps.api.schemas.exports import ExportRecord
from apps.api.services import export_service
from apps.api.services.lance_store import LanceDatasetStore


def _build_published_bundle(root: Path, *, dataset_id: str = "smoke-bg2-v1") -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    episodes_schema = pa.schema(
        [
            pa.field("episode_index", pa.int64(), nullable=False),
            pa.field("source_episode_index", pa.int64(), nullable=False),
            pa.field("source_session", pa.string(), nullable=False),
            pa.field("task_index", pa.int64()),
            pa.field("fps", pa.float64()),
            pa.field("fps_target", pa.float64()),
            pa.field("length", pa.int64()),
            pa.field("timestamps", pa.list_(pa.float64())),
            pa.field("language_instruction", pa.string()),
            pa.field(
                "camera_segments",
                pa.list_(
                    pa.struct(
                        [
                            pa.field("camera_key", pa.string()),
                            pa.field("camera_column", pa.string()),
                            pa.field("media_id", pa.string()),
                        ]
                    )
                ),
            ),
        ]
    )
    rows = [
        {
            "episode_index": i,
            "source_episode_index": i,
            "source_session": "session_20260101_120000_grasp",
            "task_index": 0,
            "fps": 30.0,
            "fps_target": 30.0,
            "length": 5,
            "timestamps": [j / 30.0 for j in range(5)],
            "language_instruction": "grasp the bolt",
            "camera_segments": [
                {
                    "camera_key": "observation.images.cam_head",
                    "camera_column": "observation_images_cam_head",
                    "media_id": f"episode_{i:08d}_observation_images_cam_head",
                }
            ],
        }
        for i in range(3)
    ]
    lance.write_dataset(
        pa.Table.from_pylist(rows, schema=episodes_schema),
        str(data_dir / "episodes.lance"),
        mode="overwrite",
    )
    videos_schema = pa.schema(
        [
            pa.field("media_id", pa.string(), nullable=False),
            pa.field("episode_index", pa.int64(), nullable=False),
            pa.field("source_episode_index", pa.int64(), nullable=False),
            pa.field("source_session", pa.string(), nullable=False),
            pa.field("camera_id", pa.string(), nullable=False),
            pa.field("camera_name", pa.string(), nullable=False),
            lance.blob_field("video_blob"),
        ]
    )
    video_rows = [
        {
            "media_id": f"episode_{i:08d}_observation_images_cam_head",
            "episode_index": i,
            "source_episode_index": i,
            "source_session": "session_20260101_120000_grasp",
            "camera_id": "observation_images_cam_head",
            "camera_name": "observation.images.cam_head",
            "video_blob": f"video-{i}".encode("utf-8"),
        }
        for i in range(3)
    ]
    video_arrays = []
    for field in videos_schema:
        values = [row.get(field.name) for row in video_rows]
        if field.name == "video_blob":
            video_arrays.append(lance.blob_array(values))
        else:
            video_arrays.append(pa.array(values, type=field.type))
    lance.write_dataset(
        pa.Table.from_arrays(video_arrays, schema=videos_schema),
        str(data_dir / "videos.lance"),
        mode="overwrite",
        data_storage_version="2.2",
    )

    manifest = {
        "format": "rllab_published_lance_dataset_v2",
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "primary_training_table": "data/episodes.lance",
        "tables": {
            "episodes": {"path": "data/episodes.lance", "exists": True},
            "videos": {"path": "data/videos.lance", "exists": True},
        },
        "modalities": {
            "video.cam_head": {
                "kind": "video",
                "camera_key": "observation.images.cam_head",
                "camera_column": "observation_images_cam_head",
                "segment_column": "camera_segments",
            }
        },
        "source_session_count": 2,
        "total_episodes": 3,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _build_published_v2_bundle(root: Path, *, dataset_id: str = "smoke-bg2-v2") -> None:
    data_dir = root / "data"
    meta_dir = root / "meta"
    data_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    state_names = ["arm_l_joint1", "gripper_l_joint1"]
    action_names = ["arm_l_joint1", "gripper_l_joint1"]
    episodes_schema = pa.schema(
        [
            pa.field("episode_index", pa.int64(), nullable=False),
            pa.field("task_index", pa.int64()),
            pa.field("fps", pa.float64()),
            pa.field("length", pa.int64()),
            pa.field("timestamps", pa.list_(pa.float64())),
            pa.field("observation_state", pa.list_(pa.list_(pa.float32()))),
            pa.field("actions", pa.list_(pa.list_(pa.float32()))),
            pa.field("language_instruction", pa.string()),
        ]
    )
    lance.write_dataset(
        pa.Table.from_pylist(
            [
                {
                    "episode_index": 0,
                    "task_index": 0,
                    "fps": 30.0,
                    "length": 2,
                    "timestamps": [0.0, 1 / 30.0],
                    "observation_state": [[0.0, 0.1], [0.2, 0.3]],
                    "actions": [[1.0, 1.1], [1.2, 1.3]],
                    "language_instruction": "pick",
                }
            ],
            schema=episodes_schema,
        ),
        str(data_dir / "episodes.lance"),
        mode="overwrite",
    )
    (meta_dir / "info.json").write_text(
        json.dumps(
            {
                "features": {
                    "observation.state": {"shape": [2], "names": state_names},
                    "action": {"shape": [2], "names": action_names},
                }
            }
        )
    )
    manifest = {
        "format": "rllab_published_lance_dataset_v2",
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "primary_training_table": "data/episodes.lance",
        "tables": {"episodes": "data/episodes.lance"},
        "modalities": {
            "state.body": {
                "kind": "state",
                "column": "observation_state",
                "names_ref": "meta/info.json#/features/observation.state/names",
                "shape": [2],
            }
        },
        "actions": {
            "action.body": {
                "kind": "action",
                "column": "actions",
                "names_ref": "meta/info.json#/features/action/names",
                "shape": [2],
                "semantics": {
                    "command_type": "joint_position",
                    "absolute_or_delta": "absolute",
                    "units": "mixed",
                    "control_frame": "robot_base",
                    "applies_to_interval": "[t_i, t_{i+1})",
                    "normalized": False,
                },
            }
        },
        "training_targets": ["action.body"],
        "counts": {"episodes": 1, "frames": 2, "videos": 0},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))


class PublishedLayoutTest(unittest.TestCase):
    def test_open_published_bundle_uses_manifest_dataset_id(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            bundle_root = Path(workdir) / "bundle-with-different-folder-name"
            _build_published_bundle(bundle_root, dataset_id="smoke-bg2-v1")

            store = LanceDatasetStore()
            record = store.open_dataset(
                DatasetOpenRequest(uri=str(bundle_root))
            )
            self.assertEqual(record.dataset_id, "smoke-bg2-v1")

            summary = store.get_summary("smoke-bg2-v1")
            self.assertIsNotNone(summary)
            assert summary is not None  # for type-checker
            self.assertEqual(summary.storage_layout, "published_hf")
            self.assertEqual(summary.primary_training_table, "data/episodes.lance")
            self.assertEqual(summary.annotation_storage, "local_overlay")
            self.assertEqual(summary.source_session_count, 2)
            self.assertEqual(summary.dataset_id_source, "manifest")
            self.assertEqual(summary.episode_count, 3)
            self.assertEqual(summary.camera_names, ["cam_head"])
            self.assertEqual(store.get_video_blob("smoke-bg2-v1", 0, "cam_head"), b"video-0")

    def test_open_published_v2_bundle_uses_registry_joint_names(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            bundle_root = Path(workdir) / "bundle-v2"
            _build_published_v2_bundle(bundle_root, dataset_id="smoke-bg2-v2")

            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri=str(bundle_root)))
            self.assertEqual(record.dataset_id, "smoke-bg2-v2")

            summary = store.get_summary("smoke-bg2-v2")
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.storage_layout, "published_hf")
            self.assertEqual(summary.primary_training_table, "data/episodes.lance")
            self.assertEqual(summary.dataset_id_source, "manifest")

            timeseries = store.get_episode_norm_series("smoke-bg2-v2", 0)
            self.assertIsNotNone(timeseries)
            assert timeseries is not None
            self.assertEqual(timeseries.state_names, ["arm_l_joint1", "gripper_l_joint1"])
            self.assertEqual(timeseries.action_names, ["arm_l_joint1", "gripper_l_joint1"])

    def test_flat_session_keeps_uri_dataset_id(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            session_root = Path(workdir) / "session_20260101_120000_grasp"
            session_root.mkdir(parents=True, exist_ok=True)

            schema = pa.schema(
                [
                    pa.field("episode_index", pa.int64(), nullable=False),
                    pa.field("task_index", pa.int64()),
                    pa.field("fps", pa.float64()),
                    pa.field("length", pa.int64()),
                    pa.field("timestamps", pa.list_(pa.float64())),
                ]
            )
            lance.write_dataset(
                pa.Table.from_pylist(
                    [
                        {
                            "episode_index": 0,
                            "task_index": 0,
                            "fps": 30.0,
                            "length": 1,
                            "timestamps": [0.0],
                        }
                    ],
                    schema=schema,
                ),
                str(session_root / "episodes.lance"),
                mode="overwrite",
            )

            store = LanceDatasetStore()
            record = store.open_dataset(DatasetOpenRequest(uri=str(session_root)))
            self.assertEqual(record.dataset_id, "session_20260101_120000_grasp")

            summary = store.get_summary(record.dataset_id)
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.storage_layout, "flat_session")
            self.assertEqual(summary.dataset_id_source, "uri")
            self.assertIsNone(summary.primary_training_table)


class HubRepoNamingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {
            key: os.environ.get(key)
            for key in (
                "RLLAB_HF_REPO_ID",
                "RLLAB_HF_NAMESPACE",
                "RLLAB_HF_CURATED_REPO_PER_EXPORT",
            )
        }
        for key in self._saved_env:
            os.environ.pop(key, None)
        self.record = ExportRecord(
            export_id="abc123def456",
            dataset_id="bg2-grasp-v1",
            episode_indices=[0],
            format=ExportFormat.lance,
            status=JobStatus.succeeded,
        )

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_uses_dataset_id_repo(self) -> None:
        os.environ["RLLAB_HF_NAMESPACE"] = "rllab-postech"
        repo_id = export_service.ExportStore._hub_repo_id(self.record)
        self.assertEqual(repo_id, "rllab-postech/bg2-grasp-v1")

    def test_legacy_curated_suffix_opt_in(self) -> None:
        os.environ["RLLAB_HF_NAMESPACE"] = "rllab-postech"
        os.environ["RLLAB_HF_CURATED_REPO_PER_EXPORT"] = "1"
        repo_id = export_service.ExportStore._hub_repo_id(self.record)
        self.assertEqual(repo_id, "rllab-postech/bg2-grasp-v1-curated-abc123de")

    def test_explicit_repo_id_wins(self) -> None:
        os.environ["RLLAB_HF_REPO_ID"] = "myorg/something-explicit"
        repo_id = export_service.ExportStore._hub_repo_id(self.record)
        self.assertEqual(repo_id, "myorg/something-explicit")

    def test_no_namespace_returns_none(self) -> None:
        repo_id = export_service.ExportStore._hub_repo_id(self.record)
        self.assertIsNone(repo_id)


if __name__ == "__main__":
    unittest.main()
