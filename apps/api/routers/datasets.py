from fastapi import APIRouter, HTTPException

from apps.api.schemas.datasets import DatasetOpenRequest, DatasetRecord, DatasetSummary
from apps.api.services.lance_store import store


router = APIRouter(tags=["datasets"])


@router.get("/datasets", response_model=list[DatasetRecord])
def list_datasets() -> list[DatasetRecord]:
    return store.list_datasets()


@router.post("/datasets/open", response_model=DatasetRecord)
def open_dataset(payload: DatasetOpenRequest) -> DatasetRecord:
    return store.open_dataset(payload)


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
