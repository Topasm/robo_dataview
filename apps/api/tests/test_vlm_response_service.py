from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from apps.api.services.vlm_response_service import VlmResponseStore


class VlmResponseServiceTest(unittest.TestCase):
    def test_store_appends_raw_response_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VlmResponseStore(storage_root=Path(tmpdir))
            response_id = store.append(
                dataset_id="dataset-a",
                job_id="job-1",
                episode_index=3,
                provider="heuristic-fallback",
                raw_response={"keyframes": [0, 10], "proposal_count": 2},
            )

            path = Path(store.job_uri(dataset_id="dataset-a", job_id="job-1"))
            row = json.loads(path.read_text(encoding="utf-8").strip())

            self.assertEqual(row["response_id"], response_id)
            self.assertEqual(row["dataset_id"], "dataset-a")
            self.assertEqual(row["episode_index"], 3)
            self.assertEqual(row["provider"], "heuristic-fallback")
            self.assertEqual(row["raw_response"]["keyframes"], [0, 10])


if __name__ == "__main__":
    unittest.main()
