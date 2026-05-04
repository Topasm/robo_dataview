from __future__ import annotations

from dataclasses import dataclass
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
    ColumnSpec("created_by", "string", nullable=False),
    ColumnSpec("created_at", "timestamp_us_utc", nullable=False),
    ColumnSpec("updated_at", "timestamp_us_utc", nullable=False),
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


def annotations_column_names() -> list[str]:
    return [column.name for column in ANNOTATIONS_COLUMNS]


def embeddings_column_names() -> list[str]:
    return [column.name for column in EMBEDDINGS_COLUMNS]


def versions_column_names() -> list[str]:
    return [column.name for column in VERSIONS_COLUMNS]


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


def build_embeddings_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `embeddings.lance`."""

    return _build_pyarrow_schema(EMBEDDINGS_COLUMNS, "embeddings.lance")


def build_versions_pyarrow_schema() -> Any:
    """Return the PyArrow schema used to create `versions.lance`."""

    return _build_pyarrow_schema(VERSIONS_COLUMNS, "versions.lance")


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
            pa.field(column.name, _pyarrow_type(pa, column.dtype), nullable=column.nullable)
            for column in columns
        ],
        metadata={key.encode(): value.encode() for key, value in metadata.items()},
    )


def _pyarrow_type(pa: Any, dtype: str) -> Any:
    if dtype == "string":
        return pa.string()
    if dtype == "int64":
        return pa.int64()
    if dtype == "float32":
        return pa.float32()
    if dtype == "list_float32":
        return pa.list_(pa.float32())
    if dtype == "timestamp_us_utc":
        return pa.timestamp("us", tz="UTC")
    raise ValueError(f"Unsupported dtype: {dtype}")
