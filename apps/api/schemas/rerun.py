from pydantic import BaseModel


class RerunSessionCreate(BaseModel):
    dataset_id: str
    episode_index: int
    mode: str = "rrd_cache"


class RerunSessionRecord(BaseModel):
    session_id: str
    dataset_id: str
    episode_index: int
    mode: str
    status: str
    viewer_url: str | None = None
    rrd_url: str | None = None
    rrd_path: str | None = None
    message: str | None = None
