from typing import Any

from pydantic import BaseModel, Field


class ActionSemantics(BaseModel):
    """Mirrors `manifest.actions.action.body.semantics` from the v2 contract.

    Surfaces what the action vector actually means so the viewer can label
    joint-position vs. EE pose, absolute vs. delta, units, etc., instead of
    showing a bare numeric strip.
    """

    command_type: str | None = Field(
        default=None,
        description="e.g. 'joint_position', 'ee_pose', 'velocity', 'unknown'.",
    )
    absolute_or_delta: str | None = None
    units: str | None = None
    control_frame: str | None = None
    applies_to_interval: str | None = None
    normalized: bool | None = None


class DatasetOpenRequest(BaseModel):
    uri: str = Field(..., description="Local path, hf:// URI, s3:// URI, or other Lance location.")
    name: str | None = Field(default=None, description="Optional display name.")


class DatasetRecord(BaseModel):
    dataset_id: str
    name: str
    uri: str
    status: str
    message: str | None = None


class DatasetSummary(BaseModel):
    dataset_id: str
    name: str
    uri: str
    status: str
    episode_count: int
    frame_count: int
    fps: float | None = None
    camera_names: list[str]
    camera_info: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Per-camera encoding metadata sourced from a sibling LeRobot "
            "meta/info.json when present (codec, fps, resolution, channels). "
            "Null when the dataset does not ship info.json."
        ),
    )
    reviewed_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    storage_layout: str = Field(
        default="flat_session",
        description=(
            "Either 'flat_session' (raw rllab session bundle with tables at the "
            "root) or 'published_hf' (HF-style root with manifest.json at the top "
            "and tables under data/)."
        ),
    )
    primary_training_table: str | None = Field(
        default=None,
        description=(
            "Manifest-declared primary training table (e.g. data/train_skill_clips.lance). "
            "Resolved relative to the bundle root; null when the manifest does not "
            "specify one."
        ),
    )
    annotation_storage: str = Field(
        default="local_overlay",
        description=(
            "Where the viewer writes review/annotation state. Always 'local_overlay' — "
            "HF/published bundles are treated as immutable source tables."
        ),
    )
    source_session_count: int | None = Field(
        default=None,
        description=(
            "Number of source raw sessions that were merged to produce this published "
            "bundle. Null when the dataset is a single flat session."
        ),
    )
    dataset_id_source: str = Field(
        default="uri",
        description=(
            "'manifest' when dataset_id was adopted from manifest.json (published "
            "bundles), 'uri' when derived from the open URI slug."
        ),
    )
    action_semantics: ActionSemantics | None = Field(
        default=None,
        description=(
            "Resolved from manifest.actions.action.body.semantics. Tells the UI "
            "what the action vector represents (joint vs EE pose, absolute vs "
            "delta, units, normalized). Null on bundles without an actions "
            "registry."
        ),
    )
    message: str | None = None


class DatasetTableHealth(BaseModel):
    table: str
    present: bool
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    missing_required_columns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DatasetHealth(BaseModel):
    dataset_id: str
    ok: bool
    status: str
    storage_model: str
    level: str = "shallow"
    episode_count: int = 0
    frame_count: int = 0
    camera_count: int = 0
    tables: list[DatasetTableHealth] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
