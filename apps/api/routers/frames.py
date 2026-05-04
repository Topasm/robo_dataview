from fastapi import APIRouter, Query


router = APIRouter(tags=["frames"])


@router.get("/frames")
def list_frames(
    dataset_id: str = Query(...),
    episode_index: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "episode_index": episode_index,
        "limit": limit,
        "items": [],
        "status": "not_implemented",
    }
