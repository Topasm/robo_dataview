from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.api.routers import jobs as jobs_router
from apps.api.schemas.common import ExportFormat, JobStatus
from apps.api.schemas.exports import ExportCreateRequest
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

    def test_create_export_job_routes_to_job_store(self) -> None:
        fake_jobs = FakeJobs()
        payload = ExportCreateRequest(
            dataset_id="dataset-a",
            episode_indices=[1],
            format=ExportFormat.jsonl,
        )

        with patch.object(jobs_router, "jobs", fake_jobs):
            record = jobs_router.create_export_job(payload)

        self.assertEqual(fake_jobs.kind, "export")
        self.assertEqual(fake_jobs.payload, payload)
        self.assertEqual(record.created_export_id, "export-1")

    def test_job_sse_event_includes_progress_payload(self) -> None:
        record = JobRecord(
            job_id="job-1",
            kind="export",
            status=JobStatus.queued,
            dataset_id="dataset-a",
            episode_indices=[1],
            progress=0.25,
            message="Queued for background worker.",
            queue_job_id="rq-job-1",
            created_export_id="export-1",
            export_format=ExportFormat.jsonl,
            export_uri="data/exports/export-1/manifest.json",
        )

        event = jobs_router._job_sse_event(record)

        self.assertIn("event: job", event)
        self.assertIn('"job_id": "job-1"', event)
        self.assertIn('"progress": 0.25', event)
        self.assertIn('"queue_job_id": "rq-job-1"', event)
        self.assertIn('"status": "queued"', event)
        self.assertIn('"created_export_id": "export-1"', event)
        self.assertIn('"export_format": "jsonl"', event)
        self.assertIn('"export_uri": "data/exports/export-1/manifest.json"', event)

    def test_stream_job_events_returns_sse_response(self) -> None:
        fake_jobs = FakeJobs()

        with patch.object(jobs_router, "jobs", fake_jobs):
            response = jobs_router.stream_job_events("job-1")

        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["cache-control"], "no-cache")


class FakeJobs:
    def __init__(self) -> None:
        self.kind: str | None = None
        self.payload: VisualEmbeddingJobCreateRequest | ExportCreateRequest | None = None

    def create(
        self,
        kind: str,
        payload: VisualEmbeddingJobCreateRequest | ExportCreateRequest,
    ) -> JobRecord:
        self.kind = kind
        self.payload = payload
        record = JobRecord(
            job_id="job-1",
            kind=kind,
            status=JobStatus.succeeded,
            dataset_id=payload.dataset_id,
            episode_indices=payload.episode_indices,
            created_embedding_ids=["embedding-1"],
        )
        if kind == "export":
            record.created_export_id = "export-1"
            record.export_format = ExportFormat.jsonl
            record.export_uri = "data/exports/export-1/manifest.json"
        return record


if __name__ == "__main__":
    unittest.main()
