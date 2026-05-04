from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from apps.api.services.version_service import (
    VersionStore,
    create_export_version_record,
)


class VersionServiceTest(unittest.TestCase):
    def test_version_store_persists_export_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_root = Path(tmpdir)
            first_store = VersionStore(storage_root=storage_root, mirror_lance=False)
            record = first_store.append(
                create_export_version_record(
                    version_id="v-export",
                    dataset_id="sample-xvla-soft-fold",
                    description="accepted subset",
                    filter_query="success_label == true",
                    num_episodes=2,
                    num_frames=360,
                    export_format="lerobot",
                    export_uri="data/exports/v-export/manifest.json",
                )
            )

            second_store = VersionStore(storage_root=storage_root, mirror_lance=False)
            loaded = second_store.list("sample-xvla-soft-fold")
            paths = second_store.storage_paths()

            self.assertEqual([version.version_id for version in loaded], [record.version_id])
            self.assertEqual(loaded[0].filter_query, "success_label == true")
            self.assertEqual(loaded[0].num_frames, 360)
            self.assertTrue(Path(paths["jsonl"]).exists())
            self.assertTrue(paths["lance"].endswith("/versions.lance"))


if __name__ == "__main__":
    unittest.main()
