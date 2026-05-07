from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from apps.api.schemas.episodes import (
    EpisodeDetail,
    EpisodeDispositionUpdate,
    EpisodeLabelHistoryRecord,
    EpisodeLabelUpdate,
    EpisodeListItem,
    EpisodeListPage,
    EpisodeTimeseries,
    StateActionSummary,
)
from apps.api.services.annotation_service import annotation_store
from apps.api.services.lance_store import store
from apps.api.services.episode_preview_service import (
    EpisodePreviewUnavailable,
    episode_preview_service,
)
from apps.api.services.pydantic_compat import model_copy
from apps.api.services.user_context import current_user_id


router = APIRouter(tags=["episodes"])


def _attach_disposition(
    episodes: list[EpisodeListItem],
    dataset_id: str,
) -> list[EpisodeListItem]:
    if not episodes:
        return episodes
    dispositions = annotation_store.list_episode_dispositions(dataset_id)
    if not dispositions:
        return episodes
    enriched: list[EpisodeListItem] = []
    for episode in episodes:
        info = dispositions.get(episode.episode_index)
        if info is None:
            enriched.append(episode)
            continue
        enriched.append(
            model_copy(
                episode,
                update={
                    "disposition": info.get("disposition"),
                    "disposition_reason": info.get("reason"),
                    "disposition_updated_at": info.get("disposition_updated_at"),
                },
            )
        )
    return enriched


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
        items = store.list_episodes(
            dataset_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_query=filter_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _attach_disposition(items, dataset_id)


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
        page = store.list_episode_page(
            dataset_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            filter_query=filter_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enriched_items = _attach_disposition(list(page.items), dataset_id)
    return model_copy(page, update={"items": enriched_items})


@router.get("/episodes/{episode_index}", response_model=EpisodeDetail)
def episode_detail(episode_index: int, dataset_id: str = Query(...)) -> EpisodeDetail:
    episode = store.get_episode(dataset_id, episode_index)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    enriched = _attach_disposition([episode], dataset_id)
    return enriched[0]


@router.patch("/episodes/{episode_index}/labels", response_model=EpisodeDetail)
def update_episode_labels(
    episode_index: int,
    payload: EpisodeLabelUpdate,
    dataset_id: str = Query(...),
    user_id: str = Depends(current_user_id),
) -> EpisodeDetail:
    if payload.updated_by is None:
        payload = model_copy(payload, update={"updated_by": user_id})
    episode = store.update_episode_labels(dataset_id, episode_index, payload)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    enriched = _attach_disposition([episode], dataset_id)
    return enriched[0]


@router.patch("/episodes/{episode_index}/disposition", response_model=EpisodeDetail)
def update_episode_disposition(
    episode_index: int,
    payload: EpisodeDispositionUpdate,
    dataset_id: str = Query(...),
    user_id: str = Depends(current_user_id),
) -> EpisodeDetail:
    episode = store.get_episode(dataset_id, episode_index)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    actor = payload.updated_by or user_id
    annotation_store.upsert_episode_disposition(
        dataset_id=dataset_id,
        episode_index=episode_index,
        disposition=payload.disposition,
        reason=payload.reason,
        actor=actor,
    )
    enriched = _attach_disposition([episode], dataset_id)
    return enriched[0]


@router.get(
    "/episodes/{episode_index}/labels/history",
    response_model=list[EpisodeLabelHistoryRecord],
)
def list_episode_label_history(
    episode_index: int,
    dataset_id: str = Query(...),
) -> list[EpisodeLabelHistoryRecord]:
    return store.list_episode_label_history(dataset_id, episode_index=episode_index)


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
            source.close()
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
            source.close()
            return Response(status_code=206, media_type="video/mp4", headers=headers)
        return StreamingResponse(
            source.iter_range(start, end),
            status_code=206,
            media_type="video/mp4",
            headers=headers,
        )
    if request.method == "HEAD":
        source.close()
        return Response(media_type="video/mp4", headers=base_headers)
    return StreamingResponse(
        source.iter_range(0, blob_len - 1),
        media_type="video/mp4",
        headers=base_headers,
    )


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
