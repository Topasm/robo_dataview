from datetime import datetime

from pydantic import BaseModel, Field


class FilterSearchRequest(BaseModel):
    dataset_id: str
    query: str
    limit: int = Field(default=100, ge=1, le=1000)


class SemanticSearchRequest(BaseModel):
    dataset_id: str
    text: str
    filter_query: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class FullTextSearchRequest(BaseModel):
    dataset_id: str
    text: str
    limit: int = Field(default=50, ge=1, le=500)


class SearchResult(BaseModel):
    dataset_id: str
    episode_index: int
    frame_index: int | None = None
    score: float | None = None
    match_type: str
    label: str | None = None


class FilterPresetCreate(BaseModel):
    dataset_id: str
    name: str = Field(..., min_length=1, max_length=80)
    query: str = Field(..., min_length=1)


class FilterPresetRecord(BaseModel):
    preset_id: str
    dataset_id: str
    name: str
    query: str
    created_at: datetime
    updated_at: datetime
