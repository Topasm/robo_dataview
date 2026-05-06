from fastapi import APIRouter, HTTPException, Query

from apps.api.schemas.search import (
    FilterPresetCreate,
    FilterPresetRecord,
    FilterSearchRequest,
    FullTextSearchRequest,
    SearchResult,
    SemanticSearchRequest,
)
from apps.api.services.annotation_service import annotation_store
from apps.api.services.embedding_service import embedding_index
from apps.api.services.filter_preset_service import filter_preset_store
from apps.api.services.full_text_search_service import full_text_search as run_full_text_search
from apps.api.services.lance_store import store
from apps.api.services.pagination import list_all_episodes


router = APIRouter(tags=["search"])


@router.post("/search/filter", response_model=list[SearchResult])
def filter_search(payload: FilterSearchRequest) -> list[SearchResult]:
    return store.filter_search(payload)


@router.post("/search/semantic", response_model=list[SearchResult])
def semantic_search(payload: SemanticSearchRequest) -> list[SearchResult]:
    episodes = list_all_episodes(store, payload.dataset_id)
    annotations = annotation_store.list(payload.dataset_id, episode_index=None)
    persist_records = True
    if payload.filter_query and payload.filter_query.strip():
        episode_indices = {
            episode.episode_index
            for episode in store.filter_episode_items(payload.dataset_id, payload.filter_query)
        }
        if not episode_indices:
            return []
        episodes = [
            episode
            for episode in episodes
            if episode.episode_index in episode_indices
        ]
        annotations = [
            annotation
            for annotation in annotations
            if annotation.episode_index in episode_indices
        ]
        persist_records = False
    return embedding_index.search(
        payload,
        episodes=episodes,
        annotations=annotations,
        persist_records=persist_records,
    )


@router.post("/search/full-text", response_model=list[SearchResult])
def full_text_search(payload: FullTextSearchRequest) -> list[SearchResult]:
    episodes = list_all_episodes(store, payload.dataset_id)
    annotations = annotation_store.list(payload.dataset_id, episode_index=None)
    return run_full_text_search(payload, episodes=episodes, annotations=annotations)


@router.get("/search/filter-presets", response_model=list[FilterPresetRecord])
def list_filter_presets(dataset_id: str = Query(...)) -> list[FilterPresetRecord]:
    return filter_preset_store.list(dataset_id)


@router.post("/search/filter-presets", response_model=FilterPresetRecord)
def create_filter_preset(payload: FilterPresetCreate) -> FilterPresetRecord:
    return filter_preset_store.create(payload)


@router.delete("/search/filter-presets/{preset_id}")
def delete_filter_preset(preset_id: str) -> dict[str, str]:
    if not filter_preset_store.delete(preset_id):
        raise HTTPException(status_code=404, detail="Filter preset not found")
    return {"status": "deleted"}
