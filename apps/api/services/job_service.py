from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.common import JobStatus
from apps.api.schemas.jobs import JobCreateRequest, JobRecord
from apps.api.services.annotation_service import annotation_store
from apps.api.services.lance_store import store
from apps.api.services.pydantic_compat import model_copy
from packages.prompts import UnknownPromptTemplateError, get_prompt_template
from workers.vlm_autolabel import AutoLabelConfig
from workers.vlm_provider import get_vlm_provider


class JobStore:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}

    def create(self, kind: str, payload: JobCreateRequest) -> JobRecord:
        job_id = str(uuid4())
        prompt = None
        if kind == "vlm_label":
            try:
                prompt = get_prompt_template(payload.prompt_template)
            except UnknownPromptTemplateError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        record = JobRecord(
            job_id=job_id,
            kind=kind,
            status=JobStatus.running,
            dataset_id=payload.dataset_id,
            episode_indices=payload.episode_indices,
            progress=0.0,
            model=payload.model,
            prompt_template=payload.prompt_template,
            prompt_version=prompt.version if prompt is not None else None,
        )
        if kind == "vlm_label":
            record = self._run_vlm_label_job(record, payload, prompt_version=prompt.version)
        else:
            record = model_copy(
                record,
                update={
                    "status": JobStatus.queued,
                    "message": "Worker queue integration is not configured for this job type.",
                }
            )
        self._records[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord:
        record = self._records.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return record

    def _run_vlm_label_job(
        self,
        record: JobRecord,
        payload: JobCreateRequest,
        *,
        prompt_version: str,
    ) -> JobRecord:
        episode_indices = payload.episode_indices
        if not episode_indices:
            episode_indices = [
                episode.episode_index
                for episode in store.list_episodes(payload.dataset_id, limit=1000, offset=0)
            ]
        if not episode_indices:
            return model_copy(
                record,
                update={
                    "status": JobStatus.failed,
                    "progress": 1.0,
                    "message": "No episodes matched the VLM auto-label request.",
                }
            )

        config = AutoLabelConfig(
            model=payload.model,
            prompt_template=payload.prompt_template,
            prompt_version=prompt_version,
        )
        provider = get_vlm_provider(payload.model)
        created_annotation_ids: list[str] = []
        missing_episodes: list[int] = []
        for episode_index in episode_indices:
            episode = store.get_episode(payload.dataset_id, episode_index)
            if episode is None:
                missing_episodes.append(episode_index)
                continue
            result = provider.propose(
                dataset_id=payload.dataset_id,
                episode=episode,
                config=config,
            )
            created_annotation_ids.extend(
                annotation_store.create(proposal).annotation_id for proposal in result.proposals
            )

        status = JobStatus.succeeded if created_annotation_ids else JobStatus.failed
        message = (
            f"Generated {len(created_annotation_ids)} pending VLM annotation proposals."
            if created_annotation_ids
            else "No VLM annotation proposals were generated."
        )
        if missing_episodes:
            message = f"{message} Missing episodes: {missing_episodes}."
        return model_copy(
            record,
            update={
                "status": status,
                "episode_indices": episode_indices,
                "progress": 1.0,
                "message": message,
                "created_annotation_ids": created_annotation_ids,
                "provider": provider.name,
            }
        )


jobs = JobStore()
