from __future__ import annotations

import unittest

from fastapi import HTTPException

from apps.api.schemas.common import JobStatus, ReviewStatus
from apps.api.schemas.jobs import JobCreateRequest
from apps.api.services.annotation_service import annotation_store
from apps.api.services.job_service import JobStore


class VlmJobServiceTest(unittest.TestCase):
    def test_vlm_label_job_creates_pending_annotations(self) -> None:
        jobs = JobStore()
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
        self.assertGreaterEqual(len(record.created_annotation_ids), 20)
        self.assertEqual(len(created_by_job), len(record.created_annotation_ids))
        self.assertTrue(all(annotation.review_status == ReviewStatus.pending for annotation in created_by_job))
        self.assertGreaterEqual(
            sum(1 for annotation in created_by_job if annotation.label_type == "important_frame"),
            8,
        )
        self.assertIn("Generated", record.message or "")

        for annotation_id in record.created_annotation_ids:
            annotation_store.delete(annotation_id)

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


if __name__ == "__main__":
    unittest.main()
