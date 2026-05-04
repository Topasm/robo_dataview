from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from apps.api.schemas.search import FilterPresetCreate
from apps.api.services.filter_preset_service import FilterPresetStore


class FilterPresetServiceTest(unittest.TestCase):
    def test_filter_presets_persist_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first = FilterPresetStore(storage_root=storage_root)
            created = first.create(
                FilterPresetCreate(
                    dataset_id="dataset-a",
                    name="Accepted train",
                    query='review_status == "accepted" AND split == "train"',
                )
            )

            second = FilterPresetStore(storage_root=storage_root)
            loaded = second.list("dataset-a")

            self.assertEqual([preset.preset_id for preset in loaded], [created.preset_id])
            self.assertEqual(loaded[0].query, 'review_status == "accepted" AND split == "train"')

            self.assertTrue(second.delete(created.preset_id))
            third = FilterPresetStore(storage_root=storage_root)
            self.assertEqual(third.list("dataset-a"), [])


if __name__ == "__main__":
    unittest.main()
