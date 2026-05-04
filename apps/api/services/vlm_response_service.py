from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4


VLM_RESPONSE_STORAGE_ROOT = Path("data/lance/vlm_responses")


class VlmResponseStore:
    def __init__(self, storage_root: Path = VLM_RESPONSE_STORAGE_ROOT) -> None:
        self.storage_root = storage_root

    def append(
        self,
        *,
        dataset_id: str,
        job_id: str,
        episode_index: int,
        provider: str,
        raw_response: dict[str, object],
    ) -> str:
        response_id = str(uuid4())
        path = self.job_path(dataset_id=dataset_id, job_id=job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "response_id": response_id,
            "dataset_id": dataset_id,
            "job_id": job_id,
            "episode_index": episode_index,
            "provider": provider,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw_response": raw_response,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        return response_id

    def job_uri(self, *, dataset_id: str, job_id: str) -> str:
        return str(self.job_path(dataset_id=dataset_id, job_id=job_id))

    def job_path(self, *, dataset_id: str, job_id: str) -> Path:
        return self._dataset_dir(dataset_id) / f"{job_id}.jsonl"

    def _dataset_dir(self, dataset_id: str) -> Path:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_id).strip("._-")
        digest = hashlib.sha1(dataset_id.encode("utf-8")).hexdigest()[:12]
        return self.storage_root / f"{slug[:80] or 'dataset'}-{digest}"


vlm_response_store = VlmResponseStore()
