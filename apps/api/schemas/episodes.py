from pydantic import BaseModel


class EpisodeListItem(BaseModel):
    dataset_id: str
    episode_index: int
    task_index: int | None = None
    length: int | None = None
    success_label: bool | None = None
    quality_score: float | None = None
    review_status: str = "pending"
    caption: str | None = None
    has_vlm_label: bool = False
    has_human_label: bool = False
    split: str | None = None


class EpisodeDetail(EpisodeListItem):
    fps: float | None = None
    camera_names: list[str]
    duration_seconds: float | None = None
    language_instruction: str | None = None


class StateActionSummary(BaseModel):
    dataset_id: str
    episode_index: int
    frame_count: int
    state_dim: int | None = None
    action_dim: int | None = None
    state_norm_min: float | None = None
    state_norm_max: float | None = None
    action_norm_min: float | None = None
    action_norm_max: float | None = None


class EpisodeTimeseries(BaseModel):
    dataset_id: str
    episode_index: int
    frame_count: int
    fps: float | None = None
    sample_count: int
    sample_indices: list[int]
    timestamps: list[float | None] | None = None
    state_norms: list[float | None]
    action_norms: list[float | None]
    state_dim: int | None = None
    action_dim: int | None = None
