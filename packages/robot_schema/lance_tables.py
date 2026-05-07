from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str
    nullable: bool = True
    description: str | None = None


ANNOTATIONS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("annotation_id", "string", nullable=False),
    ColumnSpec("dataset_id", "string", nullable=False),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("start_frame", "int64", nullable=False),
    ColumnSpec("end_frame", "int64", nullable=False),
    ColumnSpec("label_type", "string", nullable=False),
    ColumnSpec("label_value", "string", nullable=False),
    ColumnSpec("source", "string", nullable=False, description="human | vlm | heuristic | import"),
    ColumnSpec(
        "confidence",
        "float32",
        nullable=False,
        description="0.0 to 1.0 confidence for machine or heuristic annotations",
    ),
    ColumnSpec(
        "review_status",
        "string",
        nullable=False,
        description="pending | accepted | rejected | edited",
    ),
    ColumnSpec("metadata_json", "string", nullable=False),
    ColumnSpec("created_by", "string", nullable=False),
    ColumnSpec("updated_by", "string", nullable=False),
    ColumnSpec("assigned_to", "string"),
    ColumnSpec("revision", "int64", nullable=False),
    ColumnSpec("deleted_at", "timestamp_us_utc"),
    ColumnSpec("lock_owner", "string"),
    ColumnSpec("lock_expires_at", "timestamp_us_utc"),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
    ColumnSpec("updated_at", "timestamp_us_utc", nullable=False),
    ColumnSpec(
        "applied_export_id",
        "string",
        description="Export id this annotation was last materialized in (null = unapplied / draft).",
    ),
)

ANNOTATIONS_CURRENT_COLUMNS = ANNOTATIONS_COLUMNS

ANNOTATION_EVENTS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("event_id", "string", nullable=False),
    ColumnSpec("annotation_id", "string", nullable=False),
    ColumnSpec("dataset_id", "string", nullable=False),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec(
        "action",
        "string",
        nullable=False,
        description="create | update | delete | accept | reject | assign",
    ),
    ColumnSpec("actor", "string", nullable=False),
    ColumnSpec("before_json", "string"),
    ColumnSpec("after_json", "string"),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
)

EPISODE_LABELS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("dataset_id", "string", nullable=False),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("caption", "string"),
    ColumnSpec("success_label", "bool"),
    ColumnSpec("failure_reason", "string"),
    ColumnSpec("quality_score", "float32"),
    ColumnSpec("split", "string"),
    ColumnSpec(
        "review_status",
        "string",
        description="pending | accepted | rejected | edited",
    ),
    ColumnSpec("language_instruction", "string"),
    ColumnSpec("has_human_label", "bool", nullable=False),
    ColumnSpec("updated_at", "timestamp_us_utc", nullable=False),
)

EPISODE_LABEL_HISTORY_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("event_id", "string", nullable=False),
    ColumnSpec("dataset_id", "string", nullable=False),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("action", "string", nullable=False, description="update | reset"),
    ColumnSpec("actor", "string", nullable=False),
    ColumnSpec("before", "string", description="JSON-serialized snapshot of changed fields"),
    ColumnSpec("after", "string", description="JSON-serialized snapshot of changed fields"),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
)

EMBEDDINGS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("embedding_id", "string", nullable=False),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("frame_index", "int64"),
    ColumnSpec("clip_start_frame", "int64"),
    ColumnSpec("clip_end_frame", "int64"),
    ColumnSpec(
        "modality",
        "string",
        nullable=False,
        description="image | video_clip | text | trajectory",
    ),
    ColumnSpec("embedding", "list_float32", nullable=False),
    ColumnSpec("text", "string"),
    ColumnSpec("source_model", "string", nullable=False),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
    ColumnSpec("camera", "string"),
    ColumnSpec("source_uri", "string"),
    ColumnSpec("content_hash", "string"),
)

VERSIONS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("version_id", "string", nullable=False),
    ColumnSpec("parent_version_id", "string"),
    ColumnSpec("dataset_id", "string", nullable=False),
    ColumnSpec("description", "string"),
    ColumnSpec("filter_query", "string"),
    ColumnSpec("num_episodes", "int64", nullable=False),
    ColumnSpec("num_frames", "int64", nullable=False),
    ColumnSpec("export_format", "string", nullable=False),
    ColumnSpec("export_uri", "string"),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
    ColumnSpec("created_by", "string", nullable=False),
)

RAW_EPISODES_BASE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("episode_id", "string"),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("task_id", "string"),
    ColumnSpec("task_index", "int64"),
    ColumnSpec("num_frames", "int64"),
    ColumnSpec("fps", "float64"),
    ColumnSpec("length", "int64"),
    ColumnSpec("start_time", "float64"),
    ColumnSpec("end_time", "float64"),
    ColumnSpec("timestamps", "list_float64"),
    ColumnSpec("observation_state", "list_list_float32"),
    ColumnSpec("actions", "list_list_float32"),
    ColumnSpec("language_instruction", "string"),
    ColumnSpec("episode_caption", "string"),
    ColumnSpec("success_label", "bool"),
    ColumnSpec("failure_reason", "string"),
    ColumnSpec("quality_score", "float32"),
    ColumnSpec(
        "review_status",
        "string",
        description="pending | accepted | rejected | edited",
    ),
    ColumnSpec("train_val_test_split", "string"),
    ColumnSpec("split", "string"),
    ColumnSpec("created_at", "timestamp_us_utc"),
    ColumnSpec("dataset_version", "string"),
)

EPISODE_METADATA_COLUMNS: tuple[ColumnSpec, ...] = tuple(
    column
    for column in RAW_EPISODES_BASE_COLUMNS
    if column.name not in {"timestamps", "observation_state", "actions"}
)

TRAIN_SKILL_CLIP_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("clip_id", "string", nullable=False),
    ColumnSpec("source_episode_index", "int64", nullable=False),
    ColumnSpec("skill_id", "int64"),
    ColumnSpec("skill_name", "string", nullable=False),
    ColumnSpec("start_frame", "int64", nullable=False),
    ColumnSpec("end_frame", "int64", nullable=False),
    ColumnSpec("video_frame_offset", "int64", nullable=False),
    *RAW_EPISODES_BASE_COLUMNS,
)

SKILLS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("skill_id", "int64", nullable=False),
    ColumnSpec("skill_name", "string", nullable=False),
    ColumnSpec("display_label", "string", nullable=False),
    ColumnSpec("start_condition", "string"),
    ColumnSpec("end_condition", "string"),
    ColumnSpec("mission_section", "string"),
    ColumnSpec("color", "string"),
)

SKILL_SEGMENTS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("clip_id", "string", nullable=False),
    ColumnSpec("source_episode_index", "int64", nullable=False),
    ColumnSpec("skill_id", "int64"),
    ColumnSpec("skill_name", "string", nullable=False),
    ColumnSpec("start_frame", "int64", nullable=False),
    ColumnSpec("end_frame", "int64", nullable=False),
    ColumnSpec("length", "int64", nullable=False),
    ColumnSpec("quality_score", "float32"),
    ColumnSpec("success_label", "bool"),
    ColumnSpec("failure_reason", "string"),
    ColumnSpec("review_status", "string", nullable=False),
    ColumnSpec("split", "string"),
    ColumnSpec("metadata_json", "string", nullable=False),
)

FRAME_SKILL_LABELS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("frame_index", "int64", nullable=False),
    ColumnSpec("segment_id", "string", nullable=False),
    ColumnSpec("skill_id", "int64"),
    ColumnSpec("skill_name", "string", nullable=False),
    ColumnSpec("progress_in_skill", "float32"),
    ColumnSpec("review_status", "string", nullable=False),
)

RAW_FRAMES_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("episode_id", "string"),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("frame_index", "int64", nullable=False),
    ColumnSpec("global_frame_index", "int64"),
    ColumnSpec("timestamp", "float64"),
    ColumnSpec("task_id", "string"),
    ColumnSpec("task_index", "int64"),
    ColumnSpec("observation_state", "list_float32"),
    ColumnSpec("action", "list_float32"),
    ColumnSpec("is_bad_frame", "bool"),
    ColumnSpec("state_norm", "float32"),
    ColumnSpec("action_norm", "float32"),
    ColumnSpec("phase_label", "string"),
    ColumnSpec("vlm_step_caption", "string"),
    ColumnSpec("human_step_caption", "string"),
    ColumnSpec(
        "review_status",
        "string",
        description="pending | accepted | rejected | edited",
    ),
)

MEDIA_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("media_id", "string"),
    ColumnSpec("episode_id", "string"),
    ColumnSpec("episode_index", "int64"),
    ColumnSpec("camera_id", "string"),
    ColumnSpec("camera_name", "string", nullable=False),
    ColumnSpec("media_type", "string", description="video | image_sequence | depth | audio"),
    ColumnSpec("uri", "string", description="Primary local/fsspec/HF media URI"),
    ColumnSpec("relative_path", "string"),
    ColumnSpec("video_blob", "large_binary", description="Optional inline browser-playable MP4 blob"),
    ColumnSpec("video_path", "string", description="Optional local/fsspec/HF path reference"),
    ColumnSpec("from_timestamp", "float64"),
    ColumnSpec("to_timestamp", "float64"),
    ColumnSpec("num_frames", "int64"),
    ColumnSpec("chunk_index", "int64"),
    ColumnSpec("file_index", "int64"),
    ColumnSpec("sha256", "string"),
    ColumnSpec("byte_size", "int64"),
    ColumnSpec("width_pixels", "int64"),
    ColumnSpec("height_pixels", "int64"),
    ColumnSpec("fps", "float64"),
    ColumnSpec("codec", "string"),
)

RAW_VIDEOS_COLUMNS = MEDIA_COLUMNS

CAMERAS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("camera_id", "string", nullable=False),
    ColumnSpec("camera_name", "string", nullable=False),
    ColumnSpec("feature_key", "string"),
    ColumnSpec("width_pixels", "int64"),
    ColumnSpec("height_pixels", "int64"),
    ColumnSpec("fps", "float64"),
    ColumnSpec("intrinsics_json", "string"),
    ColumnSpec("extrinsics_json", "string"),
)

TASKS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("task_id", "string", nullable=False),
    ColumnSpec("task_index", "int64"),
    ColumnSpec("name", "string"),
    ColumnSpec("language_instruction", "string"),
    ColumnSpec("metadata_json", "string"),
)

SPLITS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("dataset_id", "string", nullable=False),
    ColumnSpec("episode_id", "string"),
    ColumnSpec("episode_index", "int64", nullable=False),
    ColumnSpec("split", "string", nullable=False),
    ColumnSpec("version_id", "string"),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
)


def annotations_column_names() -> list[str]:
    return [column.name for column in ANNOTATIONS_COLUMNS]


def annotations_current_column_names() -> list[str]:
    return [column.name for column in ANNOTATIONS_CURRENT_COLUMNS]


def annotation_events_column_names() -> list[str]:
    return [column.name for column in ANNOTATION_EVENTS_COLUMNS]


def embeddings_column_names() -> list[str]:
    return [column.name for column in EMBEDDINGS_COLUMNS]


def episode_labels_column_names() -> list[str]:
    return [column.name for column in EPISODE_LABELS_COLUMNS]


def episode_label_history_column_names() -> list[str]:
    return [column.name for column in EPISODE_LABEL_HISTORY_COLUMNS]


def versions_column_names() -> list[str]:
    return [column.name for column in VERSIONS_COLUMNS]


def raw_episodes_column_names(camera_feature_keys: list[str] | None = None) -> list[str]:
    return [
        column.name
        for column in _raw_episodes_columns(camera_feature_keys=camera_feature_keys)
    ]


def episodes_column_names(camera_feature_keys: list[str] | None = None) -> list[str]:
    return raw_episodes_column_names(camera_feature_keys)


def episode_metadata_column_names() -> list[str]:
    return [column.name for column in EPISODE_METADATA_COLUMNS]


def train_skill_clip_column_names(camera_feature_keys: list[str] | None = None) -> list[str]:
    return [
        column.name
        for column in _train_skill_clip_columns(camera_feature_keys=camera_feature_keys)
    ]


def skills_column_names() -> list[str]:
    return [column.name for column in SKILLS_COLUMNS]


def skill_segments_column_names() -> list[str]:
    return [column.name for column in SKILL_SEGMENTS_COLUMNS]


def frame_skill_labels_column_names() -> list[str]:
    return [column.name for column in FRAME_SKILL_LABELS_COLUMNS]


def raw_frames_column_names() -> list[str]:
    return [column.name for column in RAW_FRAMES_COLUMNS]


def frames_column_names() -> list[str]:
    return raw_frames_column_names()


def raw_videos_column_names() -> list[str]:
    return [column.name for column in RAW_VIDEOS_COLUMNS]


def media_column_names() -> list[str]:
    return [column.name for column in MEDIA_COLUMNS]


def cameras_column_names() -> list[str]:
    return [column.name for column in CAMERAS_COLUMNS]


def tasks_column_names() -> list[str]:
    return [column.name for column in TASKS_COLUMNS]


def splits_column_names() -> list[str]:
    return [column.name for column in SPLITS_COLUMNS]


def build_annotations_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `annotations.lance`.

    PyArrow is optional at scaffold time, so this function imports it lazily.
    """

    try:
        import pyarrow as pa
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to build the annotations.lance schema") from exc

    metadata = {
        column.name: column.description
        for column in ANNOTATIONS_COLUMNS
        if column.description is not None
    }
    return pa.schema(
        [
            pa.field(column.name, _pyarrow_type(pa, column.dtype), nullable=column.nullable)
            for column in ANNOTATIONS_COLUMNS
        ],
        metadata={key.encode(): value.encode() for key, value in metadata.items()},
    )


def build_annotations_current_pyarrow_schema() -> Any:
    """Return the canonical current annotation table schema."""

    return _build_pyarrow_schema(ANNOTATIONS_CURRENT_COLUMNS, "annotations_current.lance")


def build_annotation_events_pyarrow_schema() -> Any:
    """Return the append/audit annotation events table schema."""

    return _build_pyarrow_schema(ANNOTATION_EVENTS_COLUMNS, "annotation_events.lance")


def build_embeddings_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `embeddings.lance`."""

    return _build_pyarrow_schema(EMBEDDINGS_COLUMNS, "embeddings.lance")


def build_episode_labels_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `episode_labels.lance`."""

    return _build_pyarrow_schema(EPISODE_LABELS_COLUMNS, "episode_labels.lance")


def build_episode_label_history_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `episode_label_history.lance`."""

    return _build_pyarrow_schema(
        EPISODE_LABEL_HISTORY_COLUMNS, "episode_label_history.lance"
    )


def build_versions_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `versions.lance`."""

    return _build_pyarrow_schema(VERSIONS_COLUMNS, "versions.lance")


def build_raw_episodes_pyarrow_schema(
    camera_feature_keys: list[str] | None = None,
) -> Any:
    """Return the canonical raw `episodes.lance` schema.

    Camera columns are dynamic. Pass LeRobot-style feature keys such as
    `observation.images.cam_head`; each key becomes a normalized
    `{feature}_video_blob` plus timestamp range columns.
    """

    return _build_pyarrow_schema(
        _raw_episodes_columns(camera_feature_keys=camera_feature_keys),
        "episodes.lance",
    )


def build_episodes_pyarrow_schema(camera_feature_keys: list[str] | None = None) -> Any:
    """Alias for the canonical raw `episodes.lance` schema."""

    return build_raw_episodes_pyarrow_schema(camera_feature_keys)


def build_episode_metadata_pyarrow_schema() -> Any:
    """Return the metadata-only curated export `episodes.lance` schema."""

    return _build_pyarrow_schema(EPISODE_METADATA_COLUMNS, "episodes.lance")


def build_train_skill_clips_pyarrow_schema(
    camera_feature_keys: list[str] | None = None,
) -> Any:
    """Return the clip-level training table schema."""

    return _build_pyarrow_schema(
        _train_skill_clip_columns(camera_feature_keys=camera_feature_keys),
        "train_skill_clips.lance",
    )


def build_skills_pyarrow_schema() -> Any:
    """Return the canonical skill vocabulary table schema."""

    return _build_pyarrow_schema(SKILLS_COLUMNS, "skills.lance")


def build_skill_segments_pyarrow_schema() -> Any:
    """Return the accepted skill segment index table schema."""

    return _build_pyarrow_schema(SKILL_SEGMENTS_COLUMNS, "skill_segments.lance")


def build_frame_skill_labels_pyarrow_schema() -> Any:
    """Return the frame-to-skill materialized label table schema."""

    return _build_pyarrow_schema(FRAME_SKILL_LABELS_COLUMNS, "frame_skill_labels.lance")


def build_raw_frames_pyarrow_schema() -> Any:
    """Return the canonical raw `frames.lance` schema."""

    return _build_pyarrow_schema(RAW_FRAMES_COLUMNS, "frames.lance")


def build_frames_pyarrow_schema() -> Any:
    """Alias for the canonical raw `frames.lance` schema."""

    return build_raw_frames_pyarrow_schema()


def build_raw_videos_pyarrow_schema() -> Any:
    """Return the canonical raw `videos.lance` schema."""

    return _build_pyarrow_schema(RAW_VIDEOS_COLUMNS, "videos.lance")


def build_media_pyarrow_schema() -> Any:
    """Return the canonical `media.lance` schema."""

    return _build_pyarrow_schema(MEDIA_COLUMNS, "media.lance")


def build_cameras_pyarrow_schema() -> Any:
    """Return the canonical `cameras.lance` schema."""

    return _build_pyarrow_schema(CAMERAS_COLUMNS, "cameras.lance")


def build_tasks_pyarrow_schema() -> Any:
    """Return the canonical `tasks.lance` schema."""

    return _build_pyarrow_schema(TASKS_COLUMNS, "tasks.lance")


def build_splits_pyarrow_schema() -> Any:
    """Return the canonical `splits.lance` schema."""

    return _build_pyarrow_schema(SPLITS_COLUMNS, "splits.lance")


def _build_pyarrow_schema(columns: tuple[ColumnSpec, ...], table_name: str) -> Any:
    try:
        import pyarrow as pa
    except ImportError as exc:
        raise RuntimeError(f"pyarrow is required to build the {table_name} schema") from exc

    metadata = {
        column.name: column.description
        for column in columns
        if column.description is not None
    }
    return pa.schema(
        [
            _build_pyarrow_field(pa, column)
            for column in columns
        ],
        metadata={key.encode(): value.encode() for key, value in metadata.items()},
    )


def _pyarrow_type(pa: Any, dtype: str) -> Any:
    if dtype == "string":
        return pa.string()
    if dtype == "int64":
        return pa.int64()
    if dtype == "float64":
        return pa.float64()
    if dtype == "float32":
        return pa.float32()
    if dtype == "bool":
        return pa.bool_()
    if dtype == "list_float32":
        return pa.list_(pa.float32())
    if dtype == "list_float64":
        return pa.list_(pa.float64())
    if dtype == "list_list_float32":
        return pa.list_(pa.list_(pa.float32()))
    if dtype == "large_binary":
        return pa.large_binary()
    if dtype == "timestamp_us_utc":
        return pa.timestamp("us", tz="UTC")
    raise ValueError(f"Unsupported dtype: {dtype}")


def _field_metadata(column: ColumnSpec) -> dict[bytes, bytes] | None:
    if column.name.endswith("_video_blob") or column.name == "video_blob":
        return {b"lance-encoding:blob": b"true"}
    return None


def _build_pyarrow_field(pa: Any, column: ColumnSpec) -> Any:
    field_type = _pyarrow_type(pa, column.dtype)
    metadata = _field_metadata(column)
    if metadata is None:
        return pa.field(column.name, field_type, nullable=column.nullable)
    try:
        return pa.field(
            column.name,
            field_type,
            nullable=column.nullable,
            metadata=metadata,
        )
    except TypeError:
        # Some test doubles and older PyArrow-like shims do not accept field
        # metadata. The real PyArrow path keeps blob metadata above.
        return pa.field(column.name, field_type, nullable=column.nullable)


def _raw_episodes_columns(
    camera_feature_keys: list[str] | None = None,
) -> tuple[ColumnSpec, ...]:
    columns = list(RAW_EPISODES_BASE_COLUMNS)
    for feature_key in camera_feature_keys or []:
        normalized = _normalize_feature_key(feature_key)
        columns.extend(
            [
                ColumnSpec(
                    f"{normalized}_video_blob",
                    "large_binary",
                    description="Browser-playable H.264 MP4 blob",
                ),
                ColumnSpec(f"{normalized}_from_timestamp", "float64"),
                ColumnSpec(f"{normalized}_to_timestamp", "float64"),
            ]
        )
    return tuple(columns)


def _train_skill_clip_columns(
    camera_feature_keys: list[str] | None = None,
) -> tuple[ColumnSpec, ...]:
    columns = list(TRAIN_SKILL_CLIP_COLUMNS)
    for feature_key in camera_feature_keys or []:
        normalized = _normalize_feature_key(feature_key)
        columns.extend(
            [
                ColumnSpec(
                    f"{normalized}_video_blob",
                    "large_binary",
                    description="Full source episode MP4 blob reused by the skill clip",
                ),
                ColumnSpec(f"{normalized}_from_timestamp", "float64"),
                ColumnSpec(f"{normalized}_to_timestamp", "float64"),
            ]
        )
    return tuple(columns)


def _normalize_feature_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", value)
