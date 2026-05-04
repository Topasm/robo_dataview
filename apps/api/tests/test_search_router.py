from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from apps.api.routers import search
from apps.api.schemas.search import FilterPresetCreate
from apps.api.services.filter_preset_service import FilterPresetStore


class SearchRouterTest(unittest.TestCase):
    def test_filter_preset_endpoints_create_list_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilterPresetStore(storage_root=Path(tmpdir))
            with patch.object(search, "filter_preset_store", store):
                created = search.create_filter_preset(
                    FilterPresetCreate(
                        dataset_id="dataset-a",
                        name="Accepted",
                        query='review_status == "accepted"',
                    )
                )
                loaded = search.list_filter_presets(dataset_id="dataset-a")
                deleted = search.delete_filter_preset(created.preset_id)

            self.assertEqual([preset.preset_id for preset in loaded], [created.preset_id])
            self.assertEqual(deleted, {"status": "deleted"})

    def test_delete_missing_filter_preset_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilterPresetStore(storage_root=Path(tmpdir))
            with patch.object(search, "filter_preset_store", store):
                with self.assertRaises(HTTPException) as context:
                    search.delete_filter_preset("missing")

            self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
