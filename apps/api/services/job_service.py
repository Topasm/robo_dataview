from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.common import JobStatus
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.exports import ExportCreateRequest
from apps.api.schemas.jobs import JobCreateRequest, JobRecord, VisualEmbeddingJobCreateRequest
from apps.api.schemas.rerun import RerunSessionCreate
from apps.api.services.annotation_service import annotation_store
from apps.api.services.embedding_service import embedding_index
from apps.api.services.export_service import exports
from apps.api.services.job_queue import (
    JobQueueBackend,
    JobQueueUnavailableError,
    build_job_queue_from_env,
)
from apps.api.services.lance_store import store
from apps.api.services.pydantic_compat import model_copy, model_dump
from apps.api.services.rerun_service import rerun_sessions
from apps.api.services.vlm_response_service import vlm_response_store
from packages.prompts import UnknownPromptTemplateError, get_prompt_template
from workers.vlm_autolabel import AutoLabelConfig
from workers.vlm_provider import get_vlm_provider
from workers.visual_embedding_worker import (
    VisualEmbeddingConfig,
    build_visual_embedding_records,
)


APP_METADATA_DB_PATH = Path("data/app/metadata.sqlite3")
JobPayload = (
    JobCreateRequest | VisualEmbeddingJobCreateRequest | ExportCreateRequest | RerunSessionCreate
)
QueuedJobPayload = JobPayload | dict[str, object]


class SQLiteJobRecordStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(self, record: JobRecord) -> None:
        payload = json.dumps(model_dump(record), default=str, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (job_id, payload_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(job_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (record.job_id, payload),
            )

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return JobRecord(**json.loads(str(row[0])))

    def list(self) -> list[JobRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM jobs ORDER BY updated_at, job_id",
            ).fetchall()
        return [JobRecord(**json.loads(str(row[0]))) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


class JobStore:
    def __init__(
        self,
        sqlite_path: Path | None = None,
        queue_backend: JobQueueBackend | None = None,
    ) -> None:
        self._records: dict[str, JobRecord] = {}
        self._sqlite = SQLiteJobRecordStore(sqlite_path) if sqlite_path is not None else None
        self._queue_backend = queue_backend
        if self._sqlite is not None:
            self._records.update({record.job_id: record for record in self._sqlite.list()})

    def create(
        self,
        kind: str,
        payload: JobPayload,
    ) -> JobRecord:
        job_id = str(uuid4())
        prompt = self._prompt_for(kind, payload)
        status = JobStatus.queued if self._queue_backend is not None else JobStatus.running
        record = JobRecord(
            job_id=job_id,
            kind=kind,
            status=status,
            dataset_id=payload.dataset_id,
            episode_indices=_episode_indices_for_payload(payload),
            progress=0.0,
            model=getattr(payload, "model", None),
            prompt_template=getattr(payload, "prompt_template", None),
            prompt_version=prompt.version if prompt is not None else None,
            export_format=getattr(payload, "format", None),
        )
        self._save(record)

        if self._queue_backend is not None:
            try:
                queue_job_id = self._queue_backend.enqueue(job_id, kind, model_dump(payload))
            except JobQueueUnavailableError as exc:
                record = model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "progress": 1.0,
                        "message": str(exc),
                    },
                )
            else:
                record = model_copy(
                    record,
                    update={
                        "queue_job_id": queue_job_id,
                        "message": "Queued for background worker.",
                    },
                )
            self._save(record)
            return record

        return self.run(job_id, kind, payload)

    def run(
        self,
        job_id: str,
        kind: str,
        payload: QueuedJobPayload,
    ) -> JobRecord:
        payload = self._coerce_payload(kind, payload)
        record = self.get(job_id)
        record = model_copy(
            record,
            update={
                "status": JobStatus.running,
                "progress": max(record.progress, 0.01),
                "message": "Running job.",
            },
        )
        self._save(record)

        prompt = self._prompt_for(kind, payload)
        if kind == "vlm_label":
            record = self._run_vlm_label_job(
                record,
                payload,
                prompt_body=prompt.body,
                prompt_version=prompt.version,
            )
        elif kind == "visual_embedding":
            record = self._run_visual_embedding_job(record, payload)
        elif kind == "export":
            record = self._run_export_job(record, payload)
        elif kind == "rerun_session":
            record = self._run_rerun_session_job(record, payload)
        else:
            record = model_copy(
                record,
                update={
                    "status": JobStatus.queued,
                    "message": "Worker queue integration is not configured for this job type.",
                }
            )
        self._save(record)
        return record

    def get(self, job_id: str) -> JobRecord:
        if self._sqlite is not None:
            record = self._sqlite.get(job_id)
            if record is not None:
                self._records[job_id] = record
                return record
        record = self._records.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return record

    def _save(self, record: JobRecord) -> None:
        self._records[record.job_id] = record
        if self._sqlite is not None:
            self._sqlite.save(record)

    @staticmethod
    def _prompt_for(
        kind: str,
        payload: JobPayload,
    ):
        if kind != "vlm_label":
            return None
        try:
            return get_prompt_template(payload.prompt_template)
        except UnknownPromptTemplateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @staticmethod
    def _coerce_payload(
        kind: str,
        payload: QueuedJobPayload,
    ) -> JobPayload:
        if isinstance(
            payload,
            (JobCreateRequest, VisualEmbeddingJobCreateRequest, ExportCreateRequest, RerunSessionCreate),
        ):
            return payload
        if kind == "visual_embedding":
            return VisualEmbeddingJobCreateRequest(**payload)
        if kind == "export":
            return ExportCreateRequest(**payload)
        if kind == "rerun_session":
            return RerunSessionCreate(**payload)
        return JobCreateRequest(**payload)

    def _run_vlm_label_job(
        self,
        record: JobRecord,
        payload: JobCreateRequest | VisualEmbeddingJobCreateRequest,
        *,
        prompt_body: str,
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
            prompt_body=prompt_body,
            min_keyframes=payload.min_keyframes,
            max_keyframes=payload.max_keyframes,
        )
        provider = get_vlm_provider(payload.model)
        created_annotation_ids: list[str] = []
        raw_response_ids: list[str] = []
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
                video_blobs=self._video_blobs(payload.dataset_id, episode),
            )
            raw_response_ids.append(
                vlm_response_store.append(
                    dataset_id=payload.dataset_id,
                    job_id=record.job_id,
                    episode_index=episode_index,
                    provider=result.provider,
                    raw_response=result.raw_response,
                )
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
                "raw_response_ids": raw_response_ids,
                "raw_response_uri": vlm_response_store.job_uri(
                    dataset_id=payload.dataset_id,
                    job_id=record.job_id,
                )
                if raw_response_ids
                else None,
            }
        )

    def _run_visual_embedding_job(
        self,
        record: JobRecord,
        payload: JobCreateRequest | VisualEmbeddingJobCreateRequest,
    ) -> JobRecord:
        if not isinstance(payload, VisualEmbeddingJobCreateRequest):
            payload = VisualEmbeddingJobCreateRequest(
                dataset_id=payload.dataset_id,
                episode_indices=payload.episode_indices,
                model=payload.model,
            )
        config = VisualEmbeddingConfig(
            model=payload.model,
            camera_names=tuple(payload.camera_names),
            min_keyframes=payload.min_keyframes,
            max_keyframes=payload.max_keyframes,
        )
        try:
            result = build_visual_embedding_records(
                dataset_store=store,
                dataset_id=payload.dataset_id,
                episode_indices=payload.episode_indices,
                config=config,
            )
        except (RuntimeError, ValueError) as exc:
            return model_copy(
                record,
                update={
                    "status": JobStatus.failed,
                    "progress": 1.0,
                    "message": str(exc),
                }
            )

        if result.records:
            embedding_index.upsert_records(payload.dataset_id, result.records)
        status = JobStatus.succeeded if result.records else JobStatus.failed
        message = (
            f"Generated {len(result.records)} visual embedding records from "
            f"{result.artifact_count} keyframe images."
            if result.records
            else "No visual embedding records were generated."
        )
        if result.skipped:
            message = f"{message} Skipped: {result.skipped[:5]}."
        return model_copy(
            record,
            update={
                "status": status,
                "progress": 1.0,
                "message": message,
                "provider": result.provider,
                "created_embedding_ids": [item.embedding_id for item in result.records],
                "artifact_count": result.artifact_count,
            }
        )

    @staticmethod
    def _run_export_job(
        record: JobRecord,
        payload: JobPayload,
    ) -> JobRecord:
        if not isinstance(payload, ExportCreateRequest):
            payload = ExportCreateRequest(
                dataset_id=payload.dataset_id,
                episode_indices=payload.episode_indices,
            )
        export_record = exports.create(payload)
        message = export_record.message
        if message is None:
            message = (
                f"Created {export_record.format.value} export with "
                f"{len(export_record.episode_indices)} episodes."
            )
        return model_copy(
            record,
            update={
                "status": export_record.status,
                "episode_indices": export_record.episode_indices,
                "progress": 1.0,
                "message": message,
                "created_export_id": export_record.export_id,
                "export_format": export_record.format,
                "export_uri": export_record.output_uri,
            },
        )

    @staticmethod
    def _run_rerun_session_job(
        record: JobRecord,
        payload: JobPayload,
    ) -> JobRecord:
        if not isinstance(payload, RerunSessionCreate):
            episode_indices = _episode_indices_for_payload(payload)
            payload = RerunSessionCreate(
                dataset_id=payload.dataset_id,
                episode_index=episode_indices[0] if episode_indices else 0,
            )
        session = rerun_sessions.create(payload)
        status = JobStatus.succeeded if session.status == "ready" else JobStatus.failed
        message = session.message or f"Rerun session {session.status}."
        return model_copy(
            record,
            update={
                "status": status,
                "episode_indices": [session.episode_index],
                "progress": 1.0,
                "message": message,
                "created_rerun_session_id": session.session_id,
                "rerun_rrd_url": session.rrd_url,
                "rerun_rrd_path": session.rrd_path,
                "rerun_published_uri": session.published_uri,
                "rerun_viewer_url": session.viewer_url,
                "artifact_count": 1 if status == JobStatus.succeeded and session.rrd_path else 0,
            },
        )

    @staticmethod
    def _video_blobs(dataset_id: str, episode: EpisodeDetail) -> dict[str, bytes]:
        blobs: dict[str, bytes] = {}
        for camera in episode.camera_names:
            blob = store.get_video_blob(dataset_id, episode.episode_index, camera)
            if blob is not None:
                blobs[camera] = blob
        return blobs


def _episode_indices_for_payload(payload: JobPayload) -> list[int]:
    episode_indices = getattr(payload, "episode_indices", None)
    if episode_indices is not None:
        return list(episode_indices)
    episode_index = getattr(payload, "episode_index", None)
    if episode_index is None:
        return []
    return [int(episode_index)]


jobs = JobStore(sqlite_path=APP_METADATA_DB_PATH, queue_backend=build_job_queue_from_env())
