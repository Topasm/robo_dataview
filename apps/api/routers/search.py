from fastapi import APIRouter

from apps.api.schemas.search import FilterSearchRequest, SearchResult, SemanticSearchRequest
from apps.api.services.annotation_service import annotation_store
from apps.api.services.embedding_service import embedding_index
from apps.api.services.lance_store import store


router = APIRouter(tags=["search"])


@router.post("/search/filter", response_model=list[SearchResult])
def filter_search(payload: FilterSearchRequest) -> list[SearchResult]:
    return store.filter_search(payload)


@router.post("/search/semantic", response_model=list[SearchResult])
def semantic_search(payload: SemanticSearchRequest) -> list[SearchResult]:
    episodes = store.list_episodes(payload.dataset_id, limit=1000, offset=0)
    annotations = annotation_store.list(payload.dataset_id, episode_index=None)
    return embedding_index.search(payload, episodes=episodes, annotations=annotations)
