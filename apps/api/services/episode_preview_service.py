from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import tempfile
from typing import Any

from apps.api.services.lance_store import VideoSource, store


PREVIEW_CACHE_ROOT = Path("data/cache/previews")


class EpisodePreviewUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EpisodePreview:
    path: Path
    content_type: str
    frame_index: int


class EpisodePreviewService:
    def __init__(self, cache_root: Path = PREVIEW_CACHE_ROOT) -> None:
        self.cache_root = cache_root

    def get_or_create_preview(
        self,
        *,
        dataset_id: str,
        episode_index: int,
        camera: str,
        frame_index: int = 0,
    ) -> EpisodePreview | None:
        source = store.get_video_source(dataset_id, episode_index, camera)
        if source is None:
            return None

        cache_path = self._cache_path(
            dataset_id=dataset_id,
            episode_index=episode_index,
            camera=camera,
            frame_index=frame_index,
            source=source,
        )
        if not cache_path.exists():
            self._extract_preview(source=source, frame_index=frame_index, output_path=cache_path)
        return EpisodePreview(path=cache_path, content_type="image/jpeg", frame_index=frame_index)

    def _cache_path(
        self,
        *,
        dataset_id: str,
        episode_index: int,
        camera: str,
        frame_index: int,
        source: VideoSource,
    ) -> Path:
        source_key = f"bytes:{source.size}"
        if source.path is not None:
            stat = source.path.stat()
            source_key = f"path:{source.path}:{stat.st_size}:{stat.st_mtime_ns}"
        digest = hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:12]
        return (
            self.cache_root
            / _safe_name(dataset_id)
            / f"episode_{episode_index:06d}"
            / f"{_safe_name(camera)}_frame_{frame_index:06d}_{digest}.jpg"
        )

    def _extract_preview(
        self,
        *,
        source: VideoSource,
        frame_index: int,
        output_path: Path,
    ) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise EpisodePreviewUnavailable(
                "OpenCV is required for episode preview extraction. Install optional video dependencies."
            ) from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with _capture_input_path(source) as input_path:
            capture = cv2.VideoCapture(input_path)
            try:
                if not capture.isOpened():
                    raise EpisodePreviewUnavailable("Video source could not be opened for preview extraction.")
                if frame_index > 0:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise EpisodePreviewUnavailable("Preview frame could not be decoded.")
                written = cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if not written:
                    raise EpisodePreviewUnavailable("Preview JPEG could not be written.")
            finally:
                capture.release()


class _capture_input_path:
    def __init__(self, source: VideoSource) -> None:
        self.source = source
        self._temp_file: tempfile.NamedTemporaryFile[Any] | None = None

    def __enter__(self) -> str:
        if self.source.path is not None:
            return str(self.source.path)
        data = self.source.read_all()
        if data is None:
            raise EpisodePreviewUnavailable("Video source has no readable bytes.")
        self._temp_file = tempfile.NamedTemporaryFile(suffix=".mp4")
        self._temp_file.write(data)
        self._temp_file.flush()
        return self._temp_file.name

    def __exit__(self, *_: object) -> None:
        if self._temp_file is not None:
            self._temp_file.close()


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("_") or "item"


episode_preview_service = EpisodePreviewService()
