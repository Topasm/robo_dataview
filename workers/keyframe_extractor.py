from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile


class KeyframeExtractionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyframeArtifact:
    camera: str
    frame_index: int
    uri: str
    width: int
    height: int
    content_type: str = "image/jpeg"


def extract_keyframes_from_blob(
    *,
    blob: bytes,
    camera: str,
    frame_indices: list[int],
    output_dir: Path,
    jpeg_quality: int = 85,
) -> list[KeyframeArtifact]:
    if not blob or not frame_indices:
        return []

    with tempfile.NamedTemporaryFile(suffix=".mp4") as handle:
        handle.write(blob)
        handle.flush()
        return extract_keyframes_from_path(
            path=Path(handle.name),
            camera=camera,
            frame_indices=frame_indices,
            output_dir=output_dir,
            jpeg_quality=jpeg_quality,
        )


def extract_keyframes_from_path(
    *,
    path: Path,
    camera: str,
    frame_indices: list[int],
    output_dir: Path,
    jpeg_quality: int = 85,
) -> list[KeyframeArtifact]:
    if not frame_indices:
        return []

    try:
        import cv2
    except ImportError as exc:
        raise KeyframeExtractionUnavailable(
            "OpenCV is required for keyframe extraction. Install the optional video dependencies."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    camera_name = _safe_name(camera)
    artifacts: list[KeyframeArtifact] = []
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return []
        for frame_index in sorted(set(frame_indices)):
            if frame_index < 0:
                continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            artifact_path = output_dir / f"{camera_name}_frame_{frame_index:06d}.jpg"
            written = cv2.imwrite(
                str(artifact_path),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
            )
            if not written:
                continue
            artifacts.append(
                KeyframeArtifact(
                    camera=camera,
                    frame_index=frame_index,
                    uri=str(artifact_path),
                    width=int(width),
                    height=int(height),
                )
            )
    finally:
        capture.release()
    return artifacts


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("_") or "camera"
