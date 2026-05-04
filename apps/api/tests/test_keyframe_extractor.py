from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from workers.keyframe_extractor import extract_keyframes_from_blob


class KeyframeExtractorTest(unittest.TestCase):
    def test_extract_keyframes_from_mp4_blob(self) -> None:
        cv2 = _cv2_or_skip(self)
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "sample.mp4"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                10.0,
                (32, 24),
            )
            if not writer.isOpened():
                self.skipTest("OpenCV MP4 writer is not available")
            try:
                for index in range(6):
                    frame = _solid_frame(cv2, width=32, height=24, value=index * 30)
                    writer.write(frame)
            finally:
                writer.release()

            blob = video_path.read_bytes()
            output_dir = Path(tmpdir) / "keyframes"
            artifacts = extract_keyframes_from_blob(
                blob=blob,
                camera="cam high",
                frame_indices=[0, 3, 5],
                output_dir=output_dir,
            )

            self.assertEqual([artifact.frame_index for artifact in artifacts], [0, 3, 5])
            self.assertTrue(all(Path(artifact.uri).exists() for artifact in artifacts))
            self.assertEqual({artifact.camera for artifact in artifacts}, {"cam high"})
            self.assertEqual({artifact.width for artifact in artifacts}, {32})
            self.assertEqual({artifact.height for artifact in artifacts}, {24})

    def test_invalid_blob_returns_no_artifacts(self) -> None:
        _cv2_or_skip(self)
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts = extract_keyframes_from_blob(
                blob=b"not a video",
                camera="cam_high",
                frame_indices=[0],
                output_dir=Path(tmpdir),
            )

        self.assertEqual(artifacts, [])


def _cv2_or_skip(test_case: unittest.TestCase):
    try:
        import cv2
    except ImportError:
        test_case.skipTest("OpenCV is not installed")
    return cv2


def _solid_frame(cv2, *, width: int, height: int, value: int):
    try:
        import numpy as np
    except ImportError:
        frame = cv2.UMat(height, width, cv2.CV_8UC3).get()
        frame[:] = value
        return frame
    return np.full((height, width, 3), value, dtype=np.uint8)


if __name__ == "__main__":
    unittest.main()
