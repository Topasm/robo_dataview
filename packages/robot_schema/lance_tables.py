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


def annotations_column_names() -> list[str]:
    return [column.name for column in ANNOTATIONS_COLUMNS]


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


def _pyarrow_type(pa: Any, dtype: str) -> Any:
    if dtype == "string":
        return pa.string()
    if dtype == "int64":
        return pa.int64()
    if dtype == "float32":
        return pa.float32()
    if dtype == "timestamp_us_utc":
        return pa.timestamp("us", tz="UTC")
    raise ValueError(f"Unsupported dtype: {dtype}")
