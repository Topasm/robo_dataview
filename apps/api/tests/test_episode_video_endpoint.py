from __future__ import annotations

import asyncio
from io import BytesIO
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import StreamingResponse

from apps.api.routers import episodes
from apps.api.schemas.common import ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail, EpisodeLabelUpdate, EpisodeListItem, EpisodeListPage
from apps.api.services.episode_preview_service import EpisodePreview
from apps.api.services.lance_store import VideoSource


class FakeVideoStore:
    def __init__(self, blob: bytes | None) -> None:
        self.blob = blob

    def get_video_source(self, dataset_id: str, episode_index: int, camera: str) -> VideoSource | None:
        if dataset_id != "dataset-a" or episode_index != 3 or camera != "cam_high":
            return None
        if self.blob is None:
            return None
        return VideoSource(size=len(self.blob), data=self.blob)


class FakeVideoFileStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_video_source(self, dataset_id: str, episode_index: int, camera: str) -> VideoSource | None:
        if dataset_id != "dataset-a" or episode_index != 3 or camera != "cam_high":
            return None
        return VideoSource(size=self.path.stat().st_size, path=self.path)


class FakeSeekableReader:
    def __init__(self, payload: bytes) -> None:
        self._handle = BytesIO(payload)
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self._handle.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._handle.seek(offset, whence)

    def tell(self) -> int:
        return self._handle.tell()

    def close(self) -> None:
        self.closed = True
        self._handle.close()


class FakeVideoReaderStore:
    def __init__(self, payload: bytes) -> None:
        self.reader = FakeSeekableReader(payload)
        self.payload = payload

    def get_video_source(self, dataset_id: str, episode_index: int, camera: str) -> VideoSource | None:
        if dataset_id != "dataset-a" or episode_index != 3 or camera != "cam_high":
            return None
        return VideoSource(size=len(self.payload), reader=self.reader)


class FakePreviewService:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def get_or_create_preview(
        self,
        *,
        dataset_id: str,
        episode_index: int,
        camera: str,
        frame_index: int = 0,
    ) -> EpisodePreview | None:
        if (
            self.path is None
            or dataset_id != "dataset-a"
            or episode_index != 3
            or camera != "cam_high"
            or frame_index != 4
        ):
            return None
        return EpisodePreview(path=self.path, content_type="image/jpeg", frame_index=frame_index)


class FakeEpisodeLabelStore:
    def __init__(self) -> None:
        self.payload: EpisodeLabelUpdate | None = None

    def update_episode_labels(
        self,
        dataset_id: str,
        episode_index: int,
        payload: EpisodeLabelUpdate,
    ) -> EpisodeDetail | None:
        if dataset_id != "dataset-a" or episode_index != 3:
            return None
        self.payload = payload
        return EpisodeDetail(
            dataset_id=dataset_id,
            episode_index=episode_index,
            caption=payload.caption,
            failure_reason=payload.failure_reason,
            quality_score=payload.quality_score,
            review_status=payload.review_status.value if payload.review_status else "pending",
            split=payload.split,
            success_label=payload.success_label,
            has_human_label=True,
            camera_names=[],
        )


class FakeEpisodePageStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def list_episode_page(
        self,
        dataset_id: str,
        limit: int,
        offset: int,
        *,
        sort_by: str = "episode_index",
        sort_order: str = "asc",
        filter_query: str | None = None,
    ) -> EpisodeListPage:
        self.calls.append(
            {
                "dataset_id": dataset_id,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "filter_query": filter_query,
            }
        )
        return EpisodeListPage(
            dataset_id=dataset_id,
            items=[
                EpisodeListItem(
                    dataset_id=dataset_id,
                    episode_index=7,
                    review_status="accepted",
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_query=filter_query,
        )


class EpisodeVideoEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = b"0123456789abcdef"

    def test_get_video_returns_mp4_blob(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(self.blob)):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("GET"),
                dataset_id="dataset-a",
                range_header=None,
            )

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.media_type, "video/mp4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-length"], str(len(self.blob)))
        self.assertEqual(_stream_content(response), self.blob)

    def test_head_video_returns_headers_without_body(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(self.blob)):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("HEAD"),
                dataset_id="dataset-a",
                range_header=None,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "video/mp4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-length"], str(len(self.blob)))
        self.assertEqual(response.body, b"")

    def test_get_video_supports_closed_byte_range(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(self.blob)):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("GET"),
                dataset_id="dataset-a",
                range_header="bytes=2-5",
            )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.media_type, "video/mp4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-range"], "bytes 2-5/16")
        self.assertEqual(response.headers["content-length"], "4")
        self.assertEqual(_stream_content(response), b"2345")

    def test_get_video_supports_open_ended_byte_range(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(self.blob)):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("GET"),
                dataset_id="dataset-a",
                range_header="bytes=10-",
            )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 10-15/16")
        self.assertEqual(response.headers["content-length"], "6")
        self.assertEqual(_stream_content(response), b"abcdef")

    def test_get_video_streams_byte_range_from_file_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "episode.mp4"
            path.write_bytes(self.blob)
            with patch.object(episodes, "store", FakeVideoFileStore(path)):
                response = episodes.episode_video(
                    3,
                    "cam_high",
                    _request("GET"),
                    dataset_id="dataset-a",
                    range_header="bytes=3-6",
                )

            self.assertIsInstance(response, StreamingResponse)
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.headers["content-range"], "bytes 3-6/16")
            self.assertEqual(response.headers["content-length"], "4")
            self.assertEqual(_stream_content(response), b"3456")

    def test_get_video_streams_full_file_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "episode.mp4"
            path.write_bytes(self.blob)
            with patch.object(episodes, "store", FakeVideoFileStore(path)):
                response = episodes.episode_video(
                    3,
                    "cam_high",
                    _request("GET"),
                    dataset_id="dataset-a",
                    range_header=None,
                )

            self.assertIsInstance(response, StreamingResponse)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-length"], "16")
            self.assertEqual(_stream_content(response), self.blob)

    def test_get_video_streams_byte_range_from_reader_source(self) -> None:
        fake_store = FakeVideoReaderStore(self.blob)
        with patch.object(episodes, "store", fake_store):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("GET"),
                dataset_id="dataset-a",
                range_header="bytes=4-8",
            )

        self.assertIsInstance(response, StreamingResponse)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 4-8/16")
        self.assertEqual(response.headers["content-length"], "5")
        self.assertEqual(_stream_content(response), b"45678")
        self.assertTrue(fake_store.reader.closed)

    def test_head_video_supports_byte_range_headers_without_body(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(self.blob)):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("HEAD"),
                dataset_id="dataset-a",
                range_header="bytes=4-7",
            )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 4-7/16")
        self.assertEqual(response.headers["content-length"], "4")
        self.assertEqual(response.body, b"")

    def test_get_video_returns_416_for_invalid_range(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(self.blob)):
            response = episodes.episode_video(
                3,
                "cam_high",
                _request("GET"),
                dataset_id="dataset-a",
                range_header="bytes=20-30",
            )

        self.assertEqual(response.status_code, 416)
        self.assertEqual(response.media_type, "video/mp4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-range"], "bytes */16")

    def test_get_video_keeps_404_when_blob_missing(self) -> None:
        with patch.object(episodes, "store", FakeVideoStore(None)):
            with self.assertRaises(HTTPException) as context:
                episodes.episode_video(
                    3,
                    "cam_high",
                    _request("GET"),
                    dataset_id="dataset-a",
                    range_header=None,
                )

        self.assertEqual(context.exception.status_code, 404)

    def test_episode_preview_returns_file_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "preview.jpg"
            path.write_bytes(b"jpeg")
            with patch.object(episodes, "episode_preview_service", FakePreviewService(path)):
                response = episodes.episode_preview(
                    3,
                    "cam_high",
                    dataset_id="dataset-a",
                    frame_index=4,
                )

            self.assertEqual(response.media_type, "image/jpeg")
            self.assertEqual(Path(response.path), path)

    def test_episode_preview_returns_404_when_source_missing(self) -> None:
        with patch.object(episodes, "episode_preview_service", FakePreviewService(None)):
            with self.assertRaises(HTTPException) as context:
                episodes.episode_preview(
                    3,
                    "cam_high",
                    dataset_id="dataset-a",
                    frame_index=4,
                )

        self.assertEqual(context.exception.status_code, 404)

    def test_update_episode_labels_returns_updated_episode(self) -> None:
        fake_store = FakeEpisodeLabelStore()
        payload = EpisodeLabelUpdate(
            caption="Reviewed episode",
            success_label=False,
            failure_reason="slipped",
            quality_score=0.4,
            split="val",
            review_status=ReviewStatus.edited,
        )

        with patch.object(episodes, "store", fake_store):
            updated = episodes.update_episode_labels(
                3, payload, dataset_id="dataset-a", user_id="local"
            )

        self.assertEqual(updated.caption, "Reviewed episode")
        self.assertFalse(updated.success_label)
        self.assertEqual(updated.failure_reason, "slipped")
        self.assertEqual(updated.quality_score, 0.4)
        self.assertEqual(updated.split, "val")
        self.assertEqual(updated.review_status, "edited")
        self.assertEqual(fake_store.payload.caption, payload.caption)
        self.assertEqual(fake_store.payload.updated_by, "local")

    def test_update_episode_labels_returns_404_for_missing_episode(self) -> None:
        with patch.object(episodes, "store", FakeEpisodeLabelStore()):
            with self.assertRaises(HTTPException) as context:
                episodes.update_episode_labels(
                    99,
                    EpisodeLabelUpdate(caption="missing"),
                    dataset_id="dataset-a",
                    user_id="local",
                )

        self.assertEqual(context.exception.status_code, 404)

    def test_episode_page_forwards_pagination_sort_and_filter(self) -> None:
        fake_store = FakeEpisodePageStore()

        with patch.object(episodes, "store", fake_store):
            page = episodes.list_episode_page(
                dataset_id="dataset-a",
                limit=25,
                offset=50,
                sort_by="quality_score",
                sort_order="desc",
                filter_query='review_status == "accepted"',
            )

        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].episode_index, 7)
        self.assertEqual(fake_store.calls[0]["dataset_id"], "dataset-a")
        self.assertEqual(fake_store.calls[0]["limit"], 25)
        self.assertEqual(fake_store.calls[0]["offset"], 50)
        self.assertEqual(fake_store.calls[0]["sort_by"], "quality_score")
        self.assertEqual(fake_store.calls[0]["sort_order"], "desc")
        self.assertEqual(fake_store.calls[0]["filter_query"], 'review_status == "accepted"')


def _request(method: str) -> Request:
    return Request({"type": "http", "method": method, "path": "/", "headers": []})


def _stream_content(response: StreamingResponse) -> bytes:
    async def collect() -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    return asyncio.run(collect())


if __name__ == "__main__":
    unittest.main()
