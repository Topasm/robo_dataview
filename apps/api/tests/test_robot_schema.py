from __future__ import annotations

import unittest

from packages.robot_schema import (
    ANNOTATIONS_COLUMNS,
    annotations_column_names,
    annotation_events_column_names,
    annotations_current_column_names,
    cameras_column_names,
    embeddings_column_names,
    episode_labels_column_names,
    build_raw_episodes_pyarrow_schema,
    episodes_column_names,
    frames_column_names,
    media_column_names,
    raw_episodes_column_names,
    raw_frames_column_names,
    raw_videos_column_names,
    splits_column_names,
    tasks_column_names,
    versions_column_names,
)


class RobotSchemaTest(unittest.TestCase):
    def test_annotations_schema_contains_required_columns_in_order(self) -> None:
        self.assertEqual(
            annotations_column_names(),
            [
                "annotation_id",
                "dataset_id",
                "episode_index",
                "start_frame",
                "end_frame",
                "label_type",
                "label_value",
                "source",
                "confidence",
                "review_status",
                "created_by",
                "updated_by",
                "assigned_to",
                "revision",
                "deleted_at",
                "lock_owner",
                "lock_expires_at",
                "created_at",
                "updated_at",
            ],
        )
        non_nullable = {column.name for column in ANNOTATIONS_COLUMNS if not column.nullable}
        self.assertIn("annotation_id", non_nullable)
        self.assertIn("review_status", non_nullable)
        self.assertEqual(annotations_current_column_names(), annotations_column_names())

    def test_annotation_events_schema_contains_audit_columns(self) -> None:
        columns = annotation_events_column_names()

        self.assertIn("event_id", columns)
        self.assertIn("annotation_id", columns)
        self.assertIn("before_json", columns)
        self.assertIn("after_json", columns)

    def test_embeddings_schema_contains_required_columns_in_order(self) -> None:
        self.assertEqual(
            embeddings_column_names(),
            [
                "embedding_id",
                "episode_index",
                "frame_index",
                "clip_start_frame",
                "clip_end_frame",
                "modality",
                "embedding",
                "text",
                "source_model",
                "created_at",
                "camera",
                "source_uri",
                "content_hash",
            ],
        )

    def test_episode_labels_schema_contains_required_columns_in_order(self) -> None:
        self.assertEqual(
            episode_labels_column_names(),
            [
                "dataset_id",
                "episode_index",
                "caption",
                "success_label",
                "failure_reason",
                "quality_score",
                "split",
                "review_status",
                "language_instruction",
                "has_human_label",
                "updated_at",
            ],
        )

    def test_versions_schema_contains_required_columns_in_order(self) -> None:
        self.assertEqual(
            versions_column_names(),
            [
                "version_id",
                "parent_version_id",
                "dataset_id",
                "description",
                "filter_query",
                "num_episodes",
                "num_frames",
                "export_format",
                "export_uri",
                "created_at",
                "created_by",
            ],
        )

    def test_raw_episode_schema_normalizes_camera_feature_columns(self) -> None:
        columns = raw_episodes_column_names(["observation.images.cam_head"])

        self.assertIn("episode_index", columns)
        self.assertIn("observation_images_cam_head_video_blob", columns)
        self.assertIn("observation_images_cam_head_from_timestamp", columns)
        self.assertIn("observation_images_cam_head_to_timestamp", columns)
        self.assertEqual(columns, episodes_column_names(["observation.images.cam_head"]))

    def test_raw_frame_and_video_contracts_expose_core_columns(self) -> None:
        self.assertIn("frame_index", raw_frames_column_names())
        self.assertIn("global_frame_index", raw_frames_column_names())
        self.assertIn("observation_state", raw_frames_column_names())
        self.assertEqual(raw_frames_column_names(), frames_column_names())
        self.assertIn("camera_name", raw_videos_column_names())
        self.assertIn("video_blob", raw_videos_column_names())
        self.assertEqual(raw_videos_column_names(), media_column_names())

    def test_auxiliary_lance_contracts_expose_core_columns(self) -> None:
        self.assertIn("camera_id", cameras_column_names())
        self.assertIn("task_id", tasks_column_names())
        self.assertIn("split", splits_column_names())

    def test_raw_episode_schema_marks_video_blobs_as_lance_blobs(self) -> None:
        schema = build_raw_episodes_pyarrow_schema(["observation.images.cam_head"])
        field = schema.field("observation_images_cam_head_video_blob")

        self.assertEqual(field.metadata[b"lance-encoding:blob"], b"true")


if __name__ == "__main__":
    unittest.main()
