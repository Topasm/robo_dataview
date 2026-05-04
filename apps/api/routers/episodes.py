from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from apps.api.schemas.episodes import EpisodeDetail, EpisodeListItem, StateActionSummary
from apps.api.services.lance_store import store


router = APIRouter(tags=["episodes"])


@router.get("/episodes", response_model=list[EpisodeListItem])
def list_episodes(
    dataset_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[EpisodeListItem]:
    return store.list_episodes(dataset_id, limit=limit, offset=offset)


@router.get("/episodes/{episode_index}", response_model=EpisodeDetail)
def episode_detail(episode_index: int, dataset_id: str = Query(...)) -> EpisodeDetail:
    episode = store.get_episode(dataset_id, episode_index)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/episodes/{episode_index}/state-action", response_model=StateActionSummary)
def state_action_summary(episode_index: int, dataset_id: str = Query(...)) -> StateActionSummary:
    summary = store.get_state_action_summary(dataset_id, episode_index)
    if summary is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return summary


@router.get("/episodes/{episode_index}/video/{camera}")
def episode_video(episode_index: int, camera: str, dataset_id: str = Query(...)) -> StreamingResponse:
    blob = store.get_video_blob(dataset_id, episode_index, camera)
    if blob is None:
        raise HTTPException(status_code=404, detail="Video blob not found")
    return StreamingResponse(
        BytesIO(blob),
        media_type="video/mp4",
        headers={"Content-Length": str(len(blob))},
    )
