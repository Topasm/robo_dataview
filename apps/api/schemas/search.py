from pydantic import BaseModel, Field


class FilterSearchRequest(BaseModel):
    dataset_id: str
    query: str
    limit: int = Field(default=100, ge=1, le=1000)


class SemanticSearchRequest(BaseModel):
    dataset_id: str
    text: str
    limit: int = Field(default=20, ge=1, le=100)


class SearchResult(BaseModel):
    dataset_id: str
    episode_index: int
    frame_index: int | None = None
    score: float | None = None
    match_type: str
    label: str | None = None
