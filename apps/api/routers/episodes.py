from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from apps.api.schemas.episodes import (
    EpisodeDetail,
    EpisodeLabelUpdate,
    EpisodeListItem,
    EpisodeListPage,
    EpisodeTimeseries,
    StateActionSummary,
)
from apps.api.services.lance_store import store
from apps.api.services.episode_preview_service import (
    EpisodePreviewUnavailable,
    episode_preview_service,
)


router = APIRouter(tags=["episodes"])


@router.get("/episodes", response_model=list[EpisodeListItem])
def list_episodes(
    dataset_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="episode_index"),
    sort_order: str = Query(default="asc"),
    filter_query: str | None = Query(default=None),
) -> list[EpisodeListItem]:
    try:
        return store.list_episodes(
            dataset_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_query=filter_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/episodes/page", response_model=EpisodeListPage)
def list_episode_page(
    dataset_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="episode_index"),
    sort_order: str = Query(default="asc"),
    filter_query: str | None = Query(default=None),
) -> EpisodeListPage:
    try:
        return store.list_episode_page(
            dataset_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_query=filter_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/episodes/{episode_index}", response_model=EpisodeDetail)
def episode_detail(episode_index: int, dataset_id: str = Query(...)) -> EpisodeDetail:
    episode = store.get_episode(dataset_id, episode_index)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.patch("/episodes/{episode_index}/labels", response_model=EpisodeDetail)
def update_episode_labels(
    episode_index: int,
    payload: EpisodeLabelUpdate,
    dataset_id: str = Query(...),
) -> EpisodeDetail:
    episode = store.update_episode_labels(dataset_id, episode_index, payload)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/episodes/{episode_index}/state-action", response_model=StateActionSummary)
def state_action_summary(episode_index: int, dataset_id: str = Query(...)) -> StateActionSummary:
    summary = store.get_state_action_summary(dataset_id, episode_index)
    if summary is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return summary


@router.get("/episodes/{episode_index}/timeseries", response_model=EpisodeTimeseries)
def episode_timeseries(episode_index: int, dataset_id: str = Query(...)) -> EpisodeTimeseries:
    series = store.get_episode_norm_series(dataset_id, episode_index)
    if series is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return series


@router.get("/episodes/{episode_index}/preview/{camera}", response_model=None)
def episode_preview(
    episode_index: int,
    camera: str,
    dataset_id: str = Query(...),
    frame_index: int = Query(default=0, ge=0),
) -> FileResponse:
    try:
        preview = episode_preview_service.get_or_create_preview(
            dataset_id=dataset_id,
            episode_index=episode_index,
            camera=camera,
            frame_index=frame_index,
        )
    except EpisodePreviewUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if preview is None:
        raise HTTPException(status_code=404, detail="Video source not found")
    return FileResponse(preview.path, media_type=preview.content_type)


@router.get("/episodes/{episode_index}/video/{camera}", response_model=None)
@router.head("/episodes/{episode_index}/video/{camera}", response_model=None)
def episode_video(
    episode_index: int,
    camera: str,
    request: Request,
    dataset_id: str = Query(...),
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response | StreamingResponse:
    source = store.get_video_source(dataset_id, episode_index, camera)
    if source is None:
        raise HTTPException(status_code=404, detail="Video blob not found")
    blob_len = source.size
    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(blob_len),
    }
    if range_header is not None:
        byte_range = _parse_byte_range(range_header, blob_len)
        if byte_range is None:
            return Response(
                status_code=416,
                media_type="video/mp4",
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{blob_len}",
                },
            )
        start, end = byte_range
        content_length = end - start + 1
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{blob_len}",
            "Content-Length": str(content_length),
        }
        if request.method == "HEAD":
            return Response(status_code=206, media_type="video/mp4", headers=headers)
        if source.path is not None:
            return StreamingResponse(
                _iter_file_range(source.path, start, end),
                status_code=206,
                media_type="video/mp4",
                headers=headers,
            )
        return Response(
            content=(source.data or b"")[start : end + 1],
            status_code=206,
            media_type="video/mp4",
            headers=headers,
        )
    if request.method == "HEAD":
        return Response(media_type="video/mp4", headers=base_headers)
    if source.path is not None:
        return StreamingResponse(
            _iter_file_range(source.path, 0, blob_len - 1),
            media_type="video/mp4",
            headers=base_headers,
        )
    return StreamingResponse(
        BytesIO(source.data or b""),
        media_type="video/mp4",
        headers=base_headers,
    )


def _iter_file_range(
    path: Path,
    start: int,
    end: int,
    chunk_size: int = 1024 * 1024,
) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _parse_byte_range(range_header: str, blob_len: int) -> tuple[int, int] | None:
    if not range_header.startswith("bytes="):
        return None
    range_spec = range_header.removeprefix("bytes=").strip()
    if "," in range_spec or "-" not in range_spec:
        return None
    start_text, end_text = range_spec.split("-", 1)
    if not start_text.strip():
        return None
    try:
        start = int(start_text)
        end = blob_len - 1 if not end_text.strip() else int(end_text)
    except ValueError:
        return None
    if start < 0 or end < start or start >= blob_len:
        return None
    return start, min(end, blob_len - 1)
