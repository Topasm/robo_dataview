from __future__ import annotations

from typing import Any


def run_queued_job(job_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    from apps.api.services.job_service import jobs
    from apps.api.services.pydantic_compat import model_dump

    record = jobs.run(job_id, kind, payload)
    return model_dump(record)
