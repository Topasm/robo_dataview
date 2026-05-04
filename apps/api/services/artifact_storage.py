from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
import posixpath
import shutil
from typing import BinaryIO


class ArtifactPublishDependencyError(RuntimeError):
    pass


class ArtifactPublishError(RuntimeError):
    pass


def publish_directory(
    source_dir: Path,
    destination_uri: str,
    *,
    exclude_names: Iterable[str] = (),
) -> dict[str, object]:
    if not destination_uri:
        raise ArtifactPublishError("publish_uri is required to publish export artifacts.")
    if not source_dir.exists() or not source_dir.is_dir():
        raise ArtifactPublishError(f"Export directory does not exist: {source_dir}")

    excluded = set(exclude_names)
    files = [
        path
        for path in sorted(source_dir.rglob("*"))
        if path.is_file() and path.relative_to(source_dir).as_posix() not in excluded
    ]
    written_files = [
        publish_file(
            path,
            destination_uri,
            relative_path=path.relative_to(source_dir).as_posix(),
        )
        for path in files
    ]
    return {
        "destination_uri": destination_uri.rstrip("/"),
        "file_count": len(written_files),
        "total_bytes": sum(int(file["size_bytes"]) for file in written_files),
        "files": written_files,
    }


def publish_file(
    source_path: Path,
    destination_uri: str,
    *,
    relative_path: str | None = None,
) -> dict[str, object]:
    if not source_path.exists() or not source_path.is_file():
        raise ArtifactPublishError(f"Export artifact does not exist: {source_path}")
    relative_path = relative_path or source_path.name
    destination = _join_uri(destination_uri, relative_path)
    if _is_local_uri(destination):
        destination_path = _local_path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
    else:
        _copy_to_fsspec(source_path, destination)
    return {
        "path": relative_path,
        "uri": destination,
        "size_bytes": source_path.stat().st_size,
    }


def _copy_to_fsspec(source_path: Path, destination_uri: str) -> None:
    try:
        from fsspec.core import url_to_fs
    except ImportError as exc:
        raise ArtifactPublishDependencyError(
            "Publishing to remote object storage requires optional `fsspec`; install `.[storage]`."
        ) from exc

    try:
        fs, path = url_to_fs(destination_uri)
        parent = posixpath.dirname(path)
        if parent and hasattr(fs, "makedirs"):
            fs.makedirs(parent, exist_ok=True)
        with source_path.open("rb") as source, fs.open(path, "wb") as destination:
            _copy_stream(source, destination)
    except ArtifactPublishDependencyError:
        raise
    except Exception as exc:
        raise ArtifactPublishError(f"Failed to publish artifact to {destination_uri}: {exc}") from exc


def _copy_stream(source: BinaryIO, destination: BinaryIO, chunk_size: int = 1024 * 1024) -> None:
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            return
        destination.write(chunk)


def _join_uri(base_uri: str, relative_path: str) -> str:
    base = base_uri.rstrip("/")
    relative = relative_path.strip("/")
    if _is_local_uri(base_uri):
        return str(_local_path(base_uri) / Path(relative))
    return f"{base}/{relative}"


def _is_local_uri(uri: str) -> bool:
    return uri.startswith("file://") or "://" not in uri


def _local_path(uri: str) -> Path:
    if uri.startswith("file://"):
        return Path(uri.removeprefix("file://"))
    return Path(uri)


def configured_export_publish_uri() -> str | None:
    return os.getenv("ROBOT_DATA_STUDIO_EXPORT_PUBLISH_URI") or None


def configured_rerun_cache_publish_uri() -> str | None:
    return (
        os.getenv("ROBOT_DATA_STUDIO_RERUN_CACHE_PUBLISH_URI")
        or os.getenv("ROBOT_DATA_STUDIO_CACHE_PUBLISH_URI")
        or None
    )


def configured_keyframe_cache_publish_uri() -> str | None:
    return (
        os.getenv("ROBOT_DATA_STUDIO_KEYFRAME_CACHE_PUBLISH_URI")
        or os.getenv("ROBOT_DATA_STUDIO_CACHE_PUBLISH_URI")
        or None
    )


def configured_preview_cache_publish_uri() -> str | None:
    return (
        os.getenv("ROBOT_DATA_STUDIO_PREVIEW_CACHE_PUBLISH_URI")
        or os.getenv("ROBOT_DATA_STUDIO_CACHE_PUBLISH_URI")
        or None
    )
