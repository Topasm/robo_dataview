from __future__ import annotations

import unittest

from packages.robot_schema import (
    ANNOTATIONS_COLUMNS,
    annotations_column_names,
    embeddings_column_names,
    episode_labels_column_names,
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
                "assigned_to",
                "created_at",
                "updated_at",
            ],
        )
        non_nullable = {column.name for column in ANNOTATIONS_COLUMNS if not column.nullable}
        self.assertIn("annotation_id", non_nullable)
        self.assertIn("review_status", non_nullable)

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


if __name__ == "__main__":
    unittest.main()
