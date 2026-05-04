from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import StreamingResponse

from apps.api.routers import episodes


class FakeVideoStore:
    def __init__(self, blob: bytes | None) -> None:
        self.blob = blob

    def get_video_blob(self, dataset_id: str, episode_index: int, camera: str) -> bytes | None:
        if dataset_id != "dataset-a" or episode_index != 3 or camera != "cam_high":
            return None
        return self.blob


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
        self.assertEqual(response.body, b"2345")

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
        self.assertEqual(response.body, b"abcdef")

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
