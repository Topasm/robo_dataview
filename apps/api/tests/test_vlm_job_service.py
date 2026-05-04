from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from fastapi import HTTPException

from apps.api.schemas.common import ExportFormat, JobStatus, ReviewStatus
from apps.api.schemas.exports import ExportCreateRequest, ExportRecord
from apps.api.schemas.jobs import JobCreateRequest, JobRecord, VisualEmbeddingJobCreateRequest
from apps.api.schemas.rerun import RerunSessionCreate, RerunSessionRecord
from apps.api.services.embedding_service import EmbeddingRecord
from apps.api.services.annotation_service import annotation_store
from apps.api.services.job_service import JobStore
from apps.api.services.job_queue import (
    JobQueueUnavailableError,
    RQJobQueueBackend,
    build_job_queue_from_env,
)
from workers.job_runner import run_queued_job
from workers.visual_embedding_worker import VisualEmbeddingResult


class VlmJobServiceTest(unittest.TestCase):
    def test_vlm_label_job_creates_pending_annotations(self) -> None:
        jobs = JobStore()
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_VLM_PROVIDER": ""}, clear=False):
            record = jobs.create(
                kind="vlm_label",
                payload=JobCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    model="test-vlm",
                    prompt_template="episode_autolabel_v1",
                ),
            )
        created = annotation_store.list("sample-xvla-soft-fold", episode_index=0)
        created_by_job = [
            annotation
            for annotation in created
            if annotation.annotation_id in set(record.created_annotation_ids)
        ]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(record.prompt_template, "episode_autolabel_v1")
        self.assertEqual(record.prompt_version, "v1")
        self.assertEqual(record.provider, "heuristic-fallback")
        self.assertEqual(len(record.raw_response_ids), 1)
        self.assertIsNotNone(record.raw_response_uri)
        self.assertTrue(Path(record.raw_response_uri or "").exists())
        self.assertGreaterEqual(len(record.created_annotation_ids), 20)
        self.assertEqual(len(created_by_job), len(record.created_annotation_ids))
        self.assertTrue(
            all(annotation.review_status == ReviewStatus.pending for annotation in created_by_job)
        )
        self.assertGreaterEqual(
            sum(1 for annotation in created_by_job if annotation.label_type == "important_frame"),
            8,
        )
        self.assertIn("Generated", record.message or "")

        for annotation_id in record.created_annotation_ids:
            annotation_store.delete(annotation_id)
        Path(record.raw_response_uri or "").unlink(missing_ok=True)

    def test_vlm_label_job_uses_requested_keyframe_window(self) -> None:
        jobs = JobStore()
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_VLM_PROVIDER": ""}, clear=False):
            record = jobs.create(
                kind="vlm_label",
                payload=JobCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    model="test-vlm",
                    prompt_template="episode_autolabel_v1",
                    min_keyframes=3,
                    max_keyframes=3,
                ),
            )
        created = annotation_store.list("sample-xvla-soft-fold", episode_index=0)
        created_by_job = [
            annotation
            for annotation in created
            if annotation.annotation_id in set(record.created_annotation_ids)
        ]
        response_rows = [
            json.loads(line)
            for line in Path(record.raw_response_uri or "").read_text(encoding="utf-8").splitlines()
        ]

        self.assertEqual(record.status, JobStatus.succeeded)
        self.assertEqual(response_rows[0]["raw_response"]["keyframes"], [0, 90, 179])
        self.assertEqual(
            sum(1 for annotation in created_by_job if annotation.label_type == "important_frame"),
            3,
        )

        for annotation_id in record.created_annotation_ids:
            annotation_store.delete(annotation_id)
        Path(record.raw_response_uri or "").unlink(missing_ok=True)

    def test_vlm_label_job_fails_for_missing_episode(self) -> None:
        jobs = JobStore()
        record = jobs.create(
            kind="vlm_label",
            payload=JobCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[99999],
            ),
        )

        self.assertEqual(record.status, JobStatus.failed)
        self.assertEqual(record.created_annotation_ids, [])
        self.assertIn("Missing episodes", record.message or "")

    def test_vlm_label_job_rejects_unknown_prompt_template(self) -> None:
        jobs = JobStore()

        with self.assertRaises(HTTPException) as context:
            jobs.create(
                kind="vlm_label",
                payload=JobCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    prompt_template="missing_prompt",
                ),
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Unknown prompt template", str(context.exception.detail))

    def test_visual_embedding_job_persists_created_records(self) -> None:
        jobs = JobStore()
        record = EmbeddingRecord(
            embedding_id="embedding-1",
            episode_index=0,
            frame_index=0,
            clip_start_frame=0,
            clip_end_frame=0,
            modality="image",
            embedding=[1.0, 0.0],
            text="cam_high frame 0 visual keyframe",
            source_model="fake-vision",
            created_at=datetime.now(timezone.utc),
            camera="cam_high",
            source_uri="/tmp/keyframe.jpg",
            content_hash="abc123",
        )
        fake_index = FakeEmbeddingIndex()

        with (
            patch(
                "apps.api.services.job_service.build_visual_embedding_records",
                return_value=VisualEmbeddingResult(
                    records=[record],
                    artifact_count=1,
                    skipped=[],
                    provider="fake-vision",
                ),
            ),
            patch("apps.api.services.job_service.embedding_index", fake_index),
        ):
            result = jobs.create(
                kind="visual_embedding",
                payload=VisualEmbeddingJobCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    model="fake-vision",
                    camera_names=["cam_high"],
                    min_keyframes=1,
                    max_keyframes=1,
                ),
            )

        self.assertEqual(result.status, JobStatus.succeeded)
        self.assertEqual(result.created_embedding_ids, ["embedding-1"])
        self.assertEqual(result.artifact_count, 1)
        self.assertEqual(result.provider, "fake-vision")
        self.assertEqual(fake_index.dataset_id, "sample-xvla-soft-fold")
        self.assertEqual(fake_index.records, [record])

    def test_export_job_creates_export_record(self) -> None:
        jobs = JobStore()
        fake_exports = FakeExportStore(
            ExportRecord(
                export_id="export-1",
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
                format=ExportFormat.jsonl,
                status=JobStatus.succeeded,
                output_uri="data/exports/export-1/manifest.json",
                message="Export completed.",
            )
        )
        payload = ExportCreateRequest(
            dataset_id="sample-xvla-soft-fold",
            episode_indices=[0],
            format=ExportFormat.jsonl,
            version_description="job export",
        )

        with patch("apps.api.services.job_service.exports", fake_exports):
            result = jobs.create(kind="export", payload=payload)

        self.assertEqual(result.status, JobStatus.succeeded)
        self.assertEqual(result.created_export_id, "export-1")
        self.assertEqual(result.export_format, ExportFormat.jsonl)
        self.assertEqual(result.export_uri, "data/exports/export-1/manifest.json")
        self.assertEqual(result.message, "Export completed.")
        self.assertEqual(fake_exports.payload, payload)

    def test_rerun_session_job_creates_session_record(self) -> None:
        jobs = JobStore()
        fake_sessions = FakeRerunSessionStore(
            RerunSessionRecord(
                session_id="session-1",
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                mode="rrd_cache",
                status="ready",
                rrd_url="/api/rerun/recordings/session-1.rrd",
                rrd_path="data/cache/rerun/session-1.rrd",
                published_uri="s3://bucket/rerun/session-1.rrd",
                message="Generated Rerun recording.",
            )
        )
        payload = RerunSessionCreate(dataset_id="sample-xvla-soft-fold", episode_index=0)

        with patch("apps.api.services.job_service.rerun_sessions", fake_sessions):
            result = jobs.create(kind="rerun_session", payload=payload)

        self.assertEqual(result.status, JobStatus.succeeded)
        self.assertEqual(result.episode_indices, [0])
        self.assertEqual(result.created_rerun_session_id, "session-1")
        self.assertEqual(result.rerun_rrd_url, "/api/rerun/recordings/session-1.rrd")
        self.assertEqual(result.rerun_rrd_path, "data/cache/rerun/session-1.rrd")
        self.assertEqual(result.rerun_published_uri, "s3://bucket/rerun/session-1.rrd")
        self.assertEqual(fake_sessions.payload, payload)

    def test_job_store_persists_records_to_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "metadata.sqlite3"
            first = JobStore(sqlite_path=sqlite_path)
            created = first.create(
                kind="unconfigured_job",
                payload=JobCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    model="test-model",
                ),
            )

            second = JobStore(sqlite_path=sqlite_path)
            loaded = second.get(created.job_id)

        self.assertEqual(loaded.job_id, created.job_id)
        self.assertEqual(loaded.kind, "unconfigured_job")
        self.assertEqual(loaded.status, JobStatus.queued)
        self.assertEqual(loaded.dataset_id, "sample-xvla-soft-fold")
        self.assertEqual(loaded.episode_indices, [0])

    def test_job_store_refreshes_sqlite_updates_from_worker_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_path = Path(tmpdir) / "metadata.sqlite3"
            api_store = JobStore(sqlite_path=sqlite_path)
            queued = api_store.create(
                kind="unconfigured_job",
                payload=JobCreateRequest(
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                ),
            )
            worker_store = JobStore(sqlite_path=sqlite_path)
            worker_store._save(
                JobRecord(
                    job_id=queued.job_id,
                    kind="unconfigured_job",
                    status=JobStatus.succeeded,
                    dataset_id="sample-xvla-soft-fold",
                    episode_indices=[0],
                    progress=1.0,
                    message="Worker finished.",
                )
            )

            refreshed = api_store.get(queued.job_id)

        self.assertEqual(refreshed.status, JobStatus.succeeded)
        self.assertEqual(refreshed.progress, 1.0)
        self.assertEqual(refreshed.message, "Worker finished.")

    def test_job_store_enqueues_when_queue_backend_is_configured(self) -> None:
        queue = FakeQueueBackend(queue_job_id="rq-job-1")
        jobs = JobStore(queue_backend=queue)
        payload = VisualEmbeddingJobCreateRequest(
            dataset_id="sample-xvla-soft-fold",
            episode_indices=[0],
            model="fake-vision",
        )

        record = jobs.create(kind="visual_embedding", payload=payload)

        self.assertEqual(record.status, JobStatus.queued)
        self.assertEqual(record.queue_job_id, "rq-job-1")
        self.assertEqual(record.message, "Queued for background worker.")
        self.assertEqual(queue.enqueued, [("visual_embedding", payload)])

    def test_job_store_enqueues_export_jobs_when_queue_backend_is_configured(self) -> None:
        queue = FakeQueueBackend(queue_job_id="rq-export-1")
        jobs = JobStore(queue_backend=queue)
        payload = ExportCreateRequest(
            dataset_id="sample-xvla-soft-fold",
            episode_indices=[0],
            format=ExportFormat.jsonl,
        )

        record = jobs.create(kind="export", payload=payload)

        self.assertEqual(record.status, JobStatus.queued)
        self.assertEqual(record.queue_job_id, "rq-export-1")
        self.assertEqual(ExportCreateRequest(**queue.payloads[0]), payload)

    def test_job_store_enqueues_rerun_session_jobs_when_queue_backend_is_configured(self) -> None:
        queue = FakeQueueBackend(queue_job_id="rq-rerun-1")
        jobs = JobStore(queue_backend=queue)
        payload = RerunSessionCreate(dataset_id="sample-xvla-soft-fold", episode_index=0)

        record = jobs.create(kind="rerun_session", payload=payload)

        self.assertEqual(record.status, JobStatus.queued)
        self.assertEqual(record.episode_indices, [0])
        self.assertEqual(record.queue_job_id, "rq-rerun-1")
        self.assertEqual(RerunSessionCreate(**queue.payloads[0]), payload)

    def test_queued_job_runner_updates_existing_record(self) -> None:
        queue = FakeQueueBackend(queue_job_id="rq-job-1")
        jobs = JobStore(queue_backend=queue)
        payload = VisualEmbeddingJobCreateRequest(
            dataset_id="sample-xvla-soft-fold",
            episode_indices=[0],
            model="fake-vision",
        )
        queued = jobs.create(kind="visual_embedding", payload=payload)
        record = EmbeddingRecord(
            embedding_id="embedding-1",
            episode_index=0,
            frame_index=0,
            clip_start_frame=0,
            clip_end_frame=0,
            modality="image",
            embedding=[1.0, 0.0],
            text="cam_high frame 0 visual keyframe",
            source_model="fake-vision",
            created_at=datetime.now(timezone.utc),
            camera="cam_high",
            source_uri="/tmp/keyframe.jpg",
            content_hash="abc123",
        )
        fake_index = FakeEmbeddingIndex()

        with (
            patch(
                "apps.api.services.job_service.build_visual_embedding_records",
                return_value=VisualEmbeddingResult(
                    records=[record],
                    artifact_count=1,
                    skipped=[],
                    provider="fake-vision",
                ),
            ),
            patch("apps.api.services.job_service.embedding_index", fake_index),
        ):
            result = jobs.run(queued.job_id, "visual_embedding", queue.payloads[0])

        self.assertEqual(result.status, JobStatus.succeeded)
        self.assertEqual(result.progress, 1.0)
        self.assertEqual(result.created_embedding_ids, ["embedding-1"])
        self.assertEqual(jobs.get(queued.job_id).status, JobStatus.succeeded)

    def test_queued_export_job_runner_updates_existing_record(self) -> None:
        queue = FakeQueueBackend(queue_job_id="rq-export-1")
        jobs = JobStore(queue_backend=queue)
        payload = ExportCreateRequest(
            dataset_id="sample-xvla-soft-fold",
            episode_indices=[0],
            format=ExportFormat.jsonl,
        )
        queued = jobs.create(kind="export", payload=payload)
        fake_exports = FakeExportStore(
            ExportRecord(
                export_id="export-1",
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
                format=ExportFormat.jsonl,
                status=JobStatus.succeeded,
                output_uri="data/exports/export-1/manifest.json",
            )
        )

        with patch("apps.api.services.job_service.exports", fake_exports):
            result = jobs.run(queued.job_id, "export", queue.payloads[0])

        self.assertEqual(result.status, JobStatus.succeeded)
        self.assertEqual(result.progress, 1.0)
        self.assertEqual(result.created_export_id, "export-1")
        self.assertEqual(jobs.get(queued.job_id).export_uri, "data/exports/export-1/manifest.json")

    def test_queued_rerun_session_job_runner_updates_existing_record(self) -> None:
        queue = FakeQueueBackend(queue_job_id="rq-rerun-1")
        jobs = JobStore(queue_backend=queue)
        payload = RerunSessionCreate(dataset_id="sample-xvla-soft-fold", episode_index=0)
        queued = jobs.create(kind="rerun_session", payload=payload)
        fake_sessions = FakeRerunSessionStore(
            RerunSessionRecord(
                session_id="session-1",
                dataset_id="sample-xvla-soft-fold",
                episode_index=0,
                mode="rrd_cache",
                status="ready",
                rrd_url="/api/rerun/recordings/session-1.rrd",
                rrd_path="data/cache/rerun/session-1.rrd",
                published_uri="s3://bucket/rerun/session-1.rrd",
            )
        )

        with patch("apps.api.services.job_service.rerun_sessions", fake_sessions):
            result = jobs.run(queued.job_id, "rerun_session", queue.payloads[0])

        self.assertEqual(result.status, JobStatus.succeeded)
        self.assertEqual(result.progress, 1.0)
        self.assertEqual(result.created_rerun_session_id, "session-1")
        self.assertEqual(jobs.get(queued.job_id).rerun_rrd_path, "data/cache/rerun/session-1.rrd")
        self.assertEqual(jobs.get(queued.job_id).rerun_published_uri, "s3://bucket/rerun/session-1.rrd")

    def test_job_store_reports_queue_enqueue_failure(self) -> None:
        jobs = JobStore(queue_backend=FakeQueueBackend(error="redis unavailable"))

        record = jobs.create(
            kind="visual_embedding",
            payload=VisualEmbeddingJobCreateRequest(
                dataset_id="sample-xvla-soft-fold",
                episode_indices=[0],
            ),
        )

        self.assertEqual(record.status, JobStatus.failed)
        self.assertEqual(record.progress, 1.0)
        self.assertIn("redis unavailable", record.message or "")

    def test_worker_entrypoint_delegates_to_job_store(self) -> None:
        fake_jobs = FakeJobs()

        with patch("apps.api.services.job_service.jobs", fake_jobs):
            result = run_queued_job(
                "job-1",
                "visual_embedding",
                {"dataset_id": "sample-xvla-soft-fold", "episode_indices": [0]},
            )

        self.assertEqual(fake_jobs.calls, [("job-1", "visual_embedding")])
        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(result["status"], JobStatus.succeeded)

    def test_build_job_queue_from_env_returns_none_for_sync_mode(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_JOB_QUEUE": "sync"}, clear=False):
            self.assertIsNone(build_job_queue_from_env())

    def test_build_job_queue_from_env_builds_rq_backend(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ROBOT_DATA_STUDIO_JOB_QUEUE": "rq",
                "ROBOT_DATA_STUDIO_REDIS_URL": "redis://example:6379/2",
                "ROBOT_DATA_STUDIO_RQ_QUEUE": "robot-data-studio-test",
                "ROBOT_DATA_STUDIO_JOB_TIMEOUT_SECONDS": "42",
            },
            clear=False,
        ):
            backend = build_job_queue_from_env()

        self.assertIsInstance(backend, RQJobQueueBackend)
        assert isinstance(backend, RQJobQueueBackend)
        self.assertEqual(backend.redis_url, "redis://example:6379/2")
        self.assertEqual(backend.queue_name, "robot-data-studio-test")
        self.assertEqual(backend.job_timeout_seconds, 42)

    def test_build_job_queue_from_env_rejects_unknown_backend(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_JOB_QUEUE": "unknown"}, clear=False):
            with self.assertRaises(JobQueueUnavailableError):
                build_job_queue_from_env()

    def test_build_job_queue_from_env_rejects_invalid_timeout(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ROBOT_DATA_STUDIO_JOB_QUEUE": "rq",
                "ROBOT_DATA_STUDIO_JOB_TIMEOUT_SECONDS": "slow",
            },
            clear=False,
        ):
            with self.assertRaises(JobQueueUnavailableError):
                build_job_queue_from_env()


class FakeEmbeddingIndex:
    def __init__(self) -> None:
        self.dataset_id: str | None = None
        self.records: list[EmbeddingRecord] = []

    def upsert_records(self, dataset_id: str, records: list[EmbeddingRecord]):
        self.dataset_id = dataset_id
        self.records = records
        return records


class FakeExportStore:
    def __init__(self, record: ExportRecord) -> None:
        self.record = record
        self.payload: ExportCreateRequest | None = None

    def create(self, payload: ExportCreateRequest) -> ExportRecord:
        self.payload = payload
        return self.record


class FakeRerunSessionStore:
    def __init__(self, record: RerunSessionRecord) -> None:
        self.record = record
        self.payload: RerunSessionCreate | None = None

    def create(self, payload: RerunSessionCreate) -> RerunSessionRecord:
        self.payload = payload
        return self.record


class FakeQueueBackend:
    def __init__(self, queue_job_id: str | None = None, error: str | None = None) -> None:
        self.queue_job_id = queue_job_id
        self.error = error
        self.enqueued: list[tuple[str, VisualEmbeddingJobCreateRequest]] = []
        self.payloads: list[dict[str, object]] = []

    def enqueue(self, job_id: str, kind: str, payload: dict[str, object]) -> str | None:
        del job_id
        if self.error is not None:
            raise JobQueueUnavailableError(self.error)
        self.payloads.append(payload)
        if kind == "visual_embedding":
            self.enqueued.append((kind, VisualEmbeddingJobCreateRequest(**payload)))
        return self.queue_job_id


class FakeJobs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def run(self, job_id: str, kind: str, payload: dict[str, object]) -> JobRecord:
        self.calls.append((job_id, kind))
        return JobRecord(
            job_id=job_id,
            kind=kind,
            status=JobStatus.succeeded,
            dataset_id=str(payload["dataset_id"]),
            episode_indices=list(payload["episode_indices"]),
        )


if __name__ == "__main__":
    unittest.main()
