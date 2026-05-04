from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from fastapi import HTTPException

from apps.api.schemas.common import JobStatus, ReviewStatus
from apps.api.schemas.jobs import JobCreateRequest, VisualEmbeddingJobCreateRequest
from apps.api.services.embedding_service import EmbeddingRecord
from apps.api.services.annotation_service import annotation_store
from apps.api.services.job_service import JobStore
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


class FakeEmbeddingIndex:
    def __init__(self) -> None:
        self.dataset_id: str | None = None
        self.records: list[EmbeddingRecord] = []

    def upsert_records(self, dataset_id: str, records: list[EmbeddingRecord]):
        self.dataset_id = dataset_id
        self.records = records
        return records


if __name__ == "__main__":
    unittest.main()
