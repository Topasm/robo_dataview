from __future__ import annotations

import unittest

from packages.robot_schema import ANNOTATIONS_COLUMNS, annotations_column_names


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
                "created_at",
                "updated_at",
            ],
        )
        non_nullable = {column.name for column in ANNOTATIONS_COLUMNS if not column.nullable}
        self.assertIn("annotation_id", non_nullable)
        self.assertIn("review_status", non_nullable)


if __name__ == "__main__":
    unittest.main()
