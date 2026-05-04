from fastapi import APIRouter, Query

from apps.api.schemas.versions import VersionRecordResponse
from apps.api.services.version_service import version_store


router = APIRouter(tags=["versions"])


@router.get("/versions", response_model=list[VersionRecordResponse])
def list_versions(dataset_id: str | None = Query(default=None)) -> list[VersionRecordResponse]:
    return [
        VersionRecordResponse(**record.__dict__)
        for record in version_store.list(dataset_id=dataset_id)
    ]
