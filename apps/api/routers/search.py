from fastapi import APIRouter

from apps.api.schemas.search import FilterSearchRequest, SearchResult, SemanticSearchRequest
from apps.api.services.lance_store import store


router = APIRouter(tags=["search"])


@router.post("/search/filter", response_model=list[SearchResult])
def filter_search(payload: FilterSearchRequest) -> list[SearchResult]:
    return store.filter_search(payload)


@router.post("/search/semantic", response_model=list[SearchResult])
def semantic_search(payload: SemanticSearchRequest) -> list[SearchResult]:
    return store.semantic_search(payload)
