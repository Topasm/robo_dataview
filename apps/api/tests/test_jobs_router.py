from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.api.routers import jobs as jobs_router
from apps.api.schemas.common import ExportFormat, JobStatus
from apps.api.schemas.exports import ExportCreateRequest
from apps.api.schemas.jobs import JobRecord, VisualEmbeddingJobCreateRequest
from apps.api.schemas.rerun import RerunSessionCreate


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

    def test_create_rerun_session_job_routes_to_job_store(self) -> None:
        fake_jobs = FakeJobs()
        payload = RerunSessionCreate(dataset_id="dataset-a", episode_index=1)

        with patch.object(jobs_router, "jobs", fake_jobs):
            record = jobs_router.create_rerun_session_job(payload)

        self.assertEqual(fake_jobs.kind, "rerun_session")
        self.assertEqual(fake_jobs.payload, payload)
        self.assertEqual(record.created_rerun_session_id, "session-1")

    def test_job_sse_event_includes_progress_payload(self) -> None:
        record = JobRecord(
            job_id="job-1",
            kind="rerun_session",
            status=JobStatus.queued,
            dataset_id="dataset-a",
            episode_indices=[1],
            progress=0.25,
            message="Queued for background worker.",
            queue_job_id="rq-job-1",
            created_export_id="export-1",
            export_format=ExportFormat.jsonl,
            export_uri="data/exports/export-1/manifest.json",
            created_rerun_session_id="session-1",
            rerun_rrd_url="/api/rerun/recordings/session-1.rrd",
            rerun_rrd_path="data/cache/rerun/session-1.rrd",
            rerun_published_uri="s3://bucket/rerun/session-1.rrd",
            raw_response_ids=["response-1"],
            raw_response_uri="data/lance/vlm_responses/dataset-a/job-1.jsonl",
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
        self.assertIn('"created_rerun_session_id": "session-1"', event)
        self.assertIn('"rerun_rrd_url": "/api/rerun/recordings/session-1.rrd"', event)
        self.assertIn('"rerun_rrd_path": "data/cache/rerun/session-1.rrd"', event)
        self.assertIn('"rerun_published_uri": "s3://bucket/rerun/session-1.rrd"', event)
        self.assertIn('"raw_response_ids": ["response-1"]', event)
        self.assertIn('"raw_response_uri": "data/lance/vlm_responses/dataset-a/job-1.jsonl"', event)

    def test_stream_job_events_returns_sse_response(self) -> None:
        fake_jobs = FakeJobs()

        with patch.object(jobs_router, "jobs", fake_jobs):
            response = jobs_router.stream_job_events("job-1")

        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_list_vlm_responses_uses_job_dataset(self) -> None:
        fake_jobs = FakeJobs()
        fake_store = FakeVlmResponseStore()

        with (
            patch.object(jobs_router, "jobs", fake_jobs),
            patch.object(jobs_router, "vlm_response_store", fake_store),
        ):
            responses = jobs_router.list_vlm_responses("job-1")

        self.assertEqual(fake_store.calls, [("dataset-a", "job-1")])
        self.assertEqual(
            responses[0]["raw_response"]["parsed_rationales"]["success_label"]["confidence"],
            0.9,
        )


class FakeJobs:
    def __init__(self) -> None:
        self.kind: str | None = None
        self.payload: VisualEmbeddingJobCreateRequest | ExportCreateRequest | RerunSessionCreate | None = None

    def create(
        self,
        kind: str,
        payload: VisualEmbeddingJobCreateRequest | ExportCreateRequest | RerunSessionCreate,
    ) -> JobRecord:
        self.kind = kind
        self.payload = payload
        episode_indices = getattr(payload, "episode_indices", None)
        if episode_indices is None:
            episode_indices = [payload.episode_index]
        record = JobRecord(
            job_id="job-1",
            kind=kind,
            status=JobStatus.succeeded,
            dataset_id=payload.dataset_id,
            episode_indices=episode_indices,
            created_embedding_ids=["embedding-1"],
        )
        if kind == "export":
            record.created_export_id = "export-1"
            record.export_format = ExportFormat.jsonl
            record.export_uri = "data/exports/export-1/manifest.json"
        if kind == "rerun_session":
            record.created_rerun_session_id = "session-1"
            record.rerun_rrd_url = "/api/rerun/recordings/session-1.rrd"
            record.rerun_published_uri = "s3://bucket/rerun/session-1.rrd"
        return record

    def get(self, job_id: str) -> JobRecord:
        return JobRecord(
            job_id=job_id,
            kind="vlm_label",
            status=JobStatus.succeeded,
            dataset_id="dataset-a",
            episode_indices=[1],
            raw_response_ids=["response-1"],
            raw_response_uri="data/lance/vlm_responses/dataset-a/job-1.jsonl",
        )


class FakeVlmResponseStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def list_for_job(self, *, dataset_id: str, job_id: str):
        self.calls.append((dataset_id, job_id))
        return [
            {
                "response_id": "response-1",
                "dataset_id": dataset_id,
                "job_id": job_id,
                "episode_index": 1,
                "provider": "openai-compatible",
                "created_at": "2026-05-05T00:00:00Z",
                "raw_response": {
                    "parsed_rationales": {
                        "success_label": {
                            "confidence": 0.9,
                            "rationale": "The model saw task completion.",
                        }
                    }
                },
            }
        ]


if __name__ == "__main__":
    unittest.main()
