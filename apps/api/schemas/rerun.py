from pydantic import BaseModel


class RerunSessionCreate(BaseModel):
    dataset_id: str
    episode_index: int
    mode: str = "rrd_cache"
    publish_uri: str | None = None


class RerunSessionRecord(BaseModel):
    session_id: str
    dataset_id: str
    episode_index: int
    mode: str
    status: str
    cache_key: str | None = None
    cache_hit: bool = False
    camera_count: int = 0
    viewer_url: str | None = None
    rrd_url: str | None = None
    rrd_path: str | None = None
    publish_uri: str | None = None
    published_uri: str | None = None
    publish_size_bytes: int | None = None
    message: str | None = None
