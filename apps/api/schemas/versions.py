from datetime import datetime

from pydantic import BaseModel


class VersionRecordResponse(BaseModel):
    version_id: str
    parent_version_id: str | None
    dataset_id: str
    description: str | None
    filter_query: str | None
    num_episodes: int
    num_frames: int
    export_format: str
    export_uri: str | None
    created_at: datetime
    created_by: str
