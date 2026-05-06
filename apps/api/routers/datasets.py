from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.schemas.datasets import (
    DatasetHealth,
    DatasetOpenRequest,
    DatasetRecord,
    DatasetSummary,
)
from apps.api.services.lance_store import store

try:
    from lerobot2lance import convert_lerobot_to_lance
except ImportError:  # pragma: no cover - exercised only when extra missing
    convert_lerobot_to_lance = None  # type: ignore[assignment]


router = APIRouter(tags=["datasets"])


class LerobotConversionRequest(BaseModel):
    source: str
    target: str
    overwrite: bool = False
    limit: int | None = None
    include_frames: bool = True
    include_video_blobs: bool = True
    open_after: bool = True
    name: str | None = None


class LerobotConversionResponse(BaseModel):
    report: dict[str, Any]
    dataset: DatasetRecord | None = None


@router.get("/datasets", response_model=list[DatasetRecord])
def list_datasets() -> list[DatasetRecord]:
    return store.list_datasets()


@router.post("/datasets/open", response_model=DatasetRecord)
def open_dataset(payload: DatasetOpenRequest) -> DatasetRecord:
    return store.open_dataset(payload)


@router.post("/datasets/{dataset_id}/reload", response_model=DatasetRecord)
def reload_dataset(dataset_id: str) -> DatasetRecord:
    record = store.reload_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return record


@router.delete("/datasets/{dataset_id}", response_model=DatasetRecord)
def close_dataset(dataset_id: str) -> DatasetRecord:
    record = store.close_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return record


@router.get("/datasets/{dataset_id}/summary", response_model=DatasetSummary)
def dataset_summary(dataset_id: str) -> DatasetSummary:
    summary = store.get_summary(dataset_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return summary


@router.get("/datasets/{dataset_id}/schema", response_model=dict[str, list[str]])
def dataset_schema(dataset_id: str) -> dict[str, list[str]]:
    schema = store.get_schema(dataset_id)
    if schema is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return schema


@router.get("/datasets/{dataset_id}/health", response_model=DatasetHealth)
def dataset_health(dataset_id: str) -> DatasetHealth:
    health = store.get_health(dataset_id)
    if health is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return health


@router.post("/datasets/convert-lerobot", response_model=LerobotConversionResponse)
def convert_lerobot(payload: LerobotConversionRequest) -> LerobotConversionResponse:
    """Convert a LeRobot v2.1 or v3 dataset on disk into a Lance bundle and
    optionally open the result. Requires the optional ``lerobot2lance`` package
    (``pip install lerobot2lance``)."""

    if convert_lerobot_to_lance is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "lerobot2lance is not installed. "
                "Install it with `pip install lerobot2lance` "
                "(or `pip install -e .[convert]` for the bundled extras) "
                "to enable LeRobot→Lance conversion."
            ),
        )

    try:
        report = convert_lerobot_to_lance(
            Path(payload.source),
            Path(payload.target),
            overwrite=payload.overwrite,
            limit=payload.limit,
            include_frames=payload.include_frames,
            include_video_blobs=payload.include_video_blobs,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record: DatasetRecord | None = None
    if payload.open_after:
        record = store.open_dataset(
            DatasetOpenRequest(uri=payload.target, name=payload.name)
        )
    return LerobotConversionResponse(report=report, dataset=record)
