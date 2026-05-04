from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from apps.api.routers import frames as frames_router
from apps.api.schemas.annotations import AnnotationCreate, AnnotationRecord, AnnotationUpdate
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.frames import FrameRecord, FrameUpdate
from apps.api.services.pydantic_compat import model_dump


class FakeFrameStore:
    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        return EpisodeDetail(
            dataset_id=dataset_id,
            episode_index=episode_index,
            task_index=7,
            length=10,
            fps=20.0,
            camera_names=[],
        )

    def list_frames(
        self,
        dataset_id: str,
        episode_index: int,
        *,
        start_frame: int,
        end_frame: int | None,
        limit: int,
    ) -> list[FrameRecord] | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        return [
            FrameRecord(
                dataset_id=dataset_id,
                episode_index=episode_index,
                frame_index=frame_index,
                timestamp=frame_index / 20.0,
                task_index=7,
                observation_state=[float(frame_index), 0.0],
                action=[0.0, float(frame_index)],
                state_norm=float(frame_index),
                action_norm=float(frame_index),
            )
            for frame_index in range(start_frame, min((end_frame or start_frame) + 1, start_frame + limit))
        ]


class FakeAnnotationStore:
    def list(self, dataset_id: str, episode_index: int | None) -> list[AnnotationRecord]:
        now = datetime.now(timezone.utc)
        return [
            AnnotationRecord(
                annotation_id="phase-1",
                dataset_id=dataset_id,
                episode_index=episode_index or 0,
                start_frame=4,
                end_frame=4,
                label_type="phase",
                label_value="approach",
                source=AnnotationSource.human,
                confidence=1.0,
                review_status=ReviewStatus.accepted,
                created_by="test",
                created_at=now,
                updated_at=now,
            ),
            AnnotationRecord(
                annotation_id="bad-1",
                dataset_id=dataset_id,
                episode_index=episode_index or 0,
                start_frame=5,
                end_frame=6,
                label_type="bad_range",
                label_value="camera_occluded",
                source=AnnotationSource.human,
                confidence=0.8,
                review_status=ReviewStatus.pending,
                created_by="test",
                created_at=now,
                updated_at=now,
            ),
        ]


class MutableAnnotationStore:
    def __init__(self, records: list[AnnotationRecord] | None = None) -> None:
        self.records = records or []
        self.created_payloads: list[AnnotationCreate] = []

    def list(self, dataset_id: str, episode_index: int | None) -> list[AnnotationRecord]:
        return [
            record
            for record in self.records
            if record.dataset_id == dataset_id
            and (episode_index is None or record.episode_index == episode_index)
        ]

    def create(self, payload: AnnotationCreate) -> AnnotationRecord:
        now = datetime.now(timezone.utc)
        record = AnnotationRecord(
            annotation_id=f"created-{len(self.records) + 1}",
            created_at=now,
            updated_at=now,
            **model_dump(payload),
        )
        self.created_payloads.append(payload)
        self.records.append(record)
        return record

    def update(self, annotation_id: str, payload: AnnotationUpdate) -> AnnotationRecord | None:
        for index, record in enumerate(self.records):
            if record.annotation_id != annotation_id:
                continue
            data = model_dump(record)
            update_data = model_dump(payload, exclude_unset=True)
            update_data.pop("updated_by", None)
            data.update(update_data)
            data["updated_at"] = datetime.now(timezone.utc)
            updated = AnnotationRecord(**data)
            self.records[index] = updated
            return updated
        return None


def make_annotation(
    *,
    annotation_id: str,
    frame_index: int,
    label_type: str = "bad_frame",
    review_status: ReviewStatus = ReviewStatus.accepted,
) -> AnnotationRecord:
    now = datetime.now(timezone.utc)
    return AnnotationRecord(
        annotation_id=annotation_id,
        dataset_id="dataset-a",
        episode_index=3,
        start_frame=frame_index,
        end_frame=frame_index,
        label_type=label_type,
        label_value=label_type,
        source=AnnotationSource.human,
        confidence=1.0,
        review_status=review_status,
        created_by="test",
        created_at=now,
        updated_at=now,
    )


class FramesEndpointTest(unittest.TestCase):
    def test_list_frames_returns_annotation_labels_and_bad_flags(self) -> None:
        with (
            patch.object(frames_router, "store", FakeFrameStore()),
            patch.object(frames_router, "annotation_store", FakeAnnotationStore()),
        ):
            response = frames_router.list_frames(
                dataset_id="dataset-a",
                episode_index=3,
                start_frame=4,
                end_frame=6,
                limit=10,
            )

        self.assertEqual(response.frame_count, 10)
        self.assertEqual(response.returned_count, 3)
        self.assertEqual([frame.frame_index for frame in response.items], [4, 5, 6])
        self.assertEqual(response.items[0].labels[0].label_value, "approach")
        self.assertFalse(response.items[0].is_bad_frame)
        self.assertEqual(response.items[1].labels[0].label_type, "bad_range")
        self.assertTrue(response.items[1].is_bad_frame)

    def test_list_frames_rejects_invalid_range(self) -> None:
        with self.assertRaises(HTTPException) as context:
            frames_router.list_frames(
                dataset_id="dataset-a",
                episode_index=3,
                start_frame=8,
                end_frame=4,
                limit=10,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_list_frames_returns_404_for_missing_episode(self) -> None:
        with patch.object(frames_router, "store", FakeFrameStore()):
            with self.assertRaises(HTTPException) as context:
                frames_router.list_frames(
                    dataset_id="dataset-a",
                    episode_index=99,
                    start_frame=0,
                    end_frame=None,
                    limit=10,
                )

        self.assertEqual(context.exception.status_code, 404)

    def test_update_frame_marks_bad_frame_through_annotation(self) -> None:
        annotation_store = MutableAnnotationStore()
        with (
            patch.object(frames_router, "store", FakeFrameStore()),
            patch.object(frames_router, "annotation_store", annotation_store),
        ):
            response = frames_router.update_frame(
                dataset_id="dataset-a",
                episode_index=3,
                frame_index=4,
                payload=FrameUpdate(is_bad_frame=True, label_value="occluded"),
            )

        self.assertTrue(response.is_bad_frame)
        self.assertEqual(response.labels[0].label_type, "bad_frame")
        self.assertEqual(response.labels[0].label_value, "occluded")
        self.assertEqual(annotation_store.created_payloads[0].label_value, "occluded")

    def test_update_frame_clears_exact_bad_frame_annotation(self) -> None:
        annotation_store = MutableAnnotationStore([make_annotation(annotation_id="bad-frame", frame_index=4)])
        with (
            patch.object(frames_router, "store", FakeFrameStore()),
            patch.object(frames_router, "annotation_store", annotation_store),
        ):
            response = frames_router.update_frame(
                dataset_id="dataset-a",
                episode_index=3,
                frame_index=4,
                payload=FrameUpdate(is_bad_frame=False),
            )

        self.assertFalse(response.is_bad_frame)
        self.assertEqual(response.labels[0].review_status, ReviewStatus.rejected)

    def test_update_frame_rejects_empty_mutation(self) -> None:
        with (
            patch.object(frames_router, "store", FakeFrameStore()),
            patch.object(frames_router, "annotation_store", MutableAnnotationStore()),
        ):
            with self.assertRaises(HTTPException) as context:
                frames_router.update_frame(
                    dataset_id="dataset-a",
                    episode_index=3,
                    frame_index=4,
                    payload=FrameUpdate(),
                )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
