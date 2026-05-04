from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.api.routers import jobs as jobs_router
from apps.api.schemas.common import JobStatus
from apps.api.schemas.jobs import JobRecord, VisualEmbeddingJobCreateRequest


class JobsRouterTest(unittest.TestCase):
    def test_list_vlm_prompts_exposes_registered_prompt_versions(self) -> None:
        prompts = jobs_router.list_vlm_prompts()

        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].prompt_id, "episode_autolabel_v1")
        self.assertEqual(prompts[0].version, "v1")
        self.assertIn("phase", prompts[0].expected_outputs)

    def test_create_visual_embedding_job_routes_to_job_store(self) -> None:
        fake_jobs = FakeJobs()
        payload = VisualEmbeddingJobCreateRequest(
            dataset_id="dataset-a",
            episode_indices=[1],
            model="fake-vision",
        )

        with patch.object(jobs_router, "jobs", fake_jobs):
            record = jobs_router.create_visual_embedding_job(payload)

        self.assertEqual(fake_jobs.kind, "visual_embedding")
        self.assertEqual(fake_jobs.payload, payload)
        self.assertEqual(record.status, JobStatus.succeeded)


class FakeJobs:
    def __init__(self) -> None:
        self.kind: str | None = None
        self.payload: VisualEmbeddingJobCreateRequest | None = None

    def create(self, kind: str, payload: VisualEmbeddingJobCreateRequest) -> JobRecord:
        self.kind = kind
        self.payload = payload
        return JobRecord(
            job_id="job-1",
            kind=kind,
            status=JobStatus.succeeded,
            dataset_id=payload.dataset_id,
            episode_indices=payload.episode_indices,
            created_embedding_ids=["embedding-1"],
        )


if __name__ == "__main__":
    unittest.main()
