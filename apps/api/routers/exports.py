from fastapi import APIRouter

from apps.api.schemas.exports import (
    ExportCreateRequest,
    ExportHubUploadRequest,
    ExportHubUploadResponse,
    ExportRecord,
)
from apps.api.services.export_service import exports


router = APIRouter(tags=["exports"])


@router.post("/exports", response_model=ExportRecord)
def create_export(payload: ExportCreateRequest) -> ExportRecord:
    return exports.create(payload)


@router.get("/exports", response_model=list[ExportRecord])
def list_exports(dataset_id: str | None = None) -> list[ExportRecord]:
    return exports.list(dataset_id=dataset_id)


@router.get("/exports/{export_id}", response_model=ExportRecord)
def get_export(export_id: str) -> ExportRecord:
    return exports.get(export_id)


@router.post("/exports/{export_id}/upload-hub", response_model=ExportHubUploadResponse)
def upload_export_to_hub(
    export_id: str,
    payload: ExportHubUploadRequest | None = None,
) -> ExportHubUploadResponse:
    return exports.upload_to_hub(export_id, payload or ExportHubUploadRequest())
