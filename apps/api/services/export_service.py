from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

from fastapi import HTTPException

from apps.api.schemas.common import ExportFormat, JobStatus, ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.exports import (
    ExportCreateRequest,
    ExportHubUploadRequest,
    ExportHubUploadResponse,
    ExportRecord,
)
from apps.api.schemas.frames import FrameRecord
from apps.api.services.annotation_service import annotation_store
from apps.api.services.artifact_storage import (
    ArtifactPublishDependencyError,
    ArtifactPublishError,
    configured_export_publish_uri,
    publish_directory,
    publish_file,
)
from apps.api.services.hf_dataset_export import (
    HFDatasetExportDependencyError,
    write_hf_dataset_export,
)
from apps.api.services.lance_export import LanceExportDependencyError, write_lance_subset
from apps.api.services.lance_store import store
from apps.api.services.lerobot_io import write_lerobot_v3_snapshot
from apps.api.services.pagination import list_all_episodes
from apps.api.services.pydantic_compat import model_copy, model_dump
from apps.api.services.training_export import write_jsonl_export, write_vla_jsonl_export
from apps.api.services.version_service import (
    VersionStore,
    create_export_version_record,
    version_store,
)


EXPORT_ROOT = Path(os.getenv("ROBOT_DATA_STUDIO_EXPORT_ROOT", "data/exports"))


class ExportStore:
    def __init__(self, versions: VersionStore | None = version_store) -> None:
        self._versions = versions
        self._records: dict[str, ExportRecord] = {}
        self._load_existing_exports()

    def create(self, payload: ExportCreateRequest) -> ExportRecord:
        export_id = str(uuid4())
        episode_indices = payload.episode_indices or self._episode_indices_for_splits(payload)
        export_dir = EXPORT_ROOT / export_id
        manifest_path = export_dir / "manifest.json"
        record = ExportRecord(
            export_id=export_id,
            dataset_id=payload.dataset_id,
            episode_indices=episode_indices,
            format=payload.format,
            status=JobStatus.running,
            output_uri=str(manifest_path),
            message=None,
        )
        record = self._write_manifest(record, payload, manifest_path)
        self._records[export_id] = record
        return record

    def get(self, export_id: str) -> ExportRecord:
        record = self._records.get(export_id)
        if record is None:
            record = self._record_from_manifest(EXPORT_ROOT / export_id / "manifest.json")
        if record is None:
            raise HTTPException(status_code=404, detail="Export not found")
        self._records[export_id] = record
        return record

    def list(self, *, dataset_id: str | None = None) -> list[ExportRecord]:
        records = list(self._records.values())
        if dataset_id is not None:
            records = [record for record in records if record.dataset_id == dataset_id]
        records.sort(
            key=lambda record: record.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return records

    def upload_to_hub(
        self,
        export_id: str,
        payload: ExportHubUploadRequest,
    ) -> ExportHubUploadResponse:
        record = self.get(export_id)
        if record.status != JobStatus.succeeded:
            raise HTTPException(status_code=400, detail="Only succeeded exports can be uploaded.")

        upload_path = self._hub_upload_path(record)
        repo_id = payload.repo_id or self._hub_repo_id(record)
        if not repo_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Hugging Face repo is not configured. Set RLLAB_HF_NAMESPACE or "
                    "RLLAB_HF_REPO_ID on the API process."
                ),
            )

        private = (
            payload.private
            if payload.private is not None
            else _truthy_env("RLLAB_HF_PRIVATE", True)
        )
        revision = payload.revision or os.getenv("RLLAB_HF_REVISION") or None
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise HTTPException(
                status_code=400,
                detail="huggingface_hub is not installed in the API environment.",
            ) from exc

        api = HfApi()
        try:
            api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)
            if revision:
                api.create_branch(
                    repo_id=repo_id,
                    repo_type="dataset",
                    branch=revision,
                    exist_ok=True,
                )
            result = api.upload_folder(
                repo_id=repo_id,
                repo_type="dataset",
                folder_path=str(upload_path),
                revision=revision,
                commit_message=f"Upload Robot Data Studio export {record.export_id}",
            )
        except Exception as exc:  # noqa: BLE001 - surface Hub auth/config errors cleanly
            raise HTTPException(
                status_code=400,
                detail=f"Hugging Face upload failed: {exc}",
            ) from exc

        repo_url = f"https://huggingface.co/datasets/{repo_id}"
        response = ExportHubUploadResponse(
            export_id=record.export_id,
            repo_id=repo_id,
            repo_url=repo_url,
            uploaded_path=str(upload_path),
            revision=revision,
            commit_url=getattr(result, "commit_url", None),
            message=f"Uploaded export {record.export_id} to {repo_id}.",
        )
        self._record_hub_upload(record, response)
        return response

    def _load_existing_exports(self) -> None:
        if not EXPORT_ROOT.exists():
            return
        for manifest_path in EXPORT_ROOT.glob("*/manifest.json"):
            record = self._record_from_manifest(manifest_path)
            if record is not None:
                self._records[record.export_id] = record

    def _record_from_manifest(self, manifest_path: Path) -> ExportRecord | None:
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created_at_raw = manifest.get("created_at")
            created_at: datetime | None = None
            if isinstance(created_at_raw, str):
                try:
                    created_at = datetime.fromisoformat(created_at_raw)
                except ValueError:
                    created_at = None
            return ExportRecord(
                export_id=manifest["export_id"],
                dataset_id=manifest["dataset_id"],
                episode_indices=list(manifest.get("episode_indices", [])),
                format=manifest["format"],
                status=JobStatus.succeeded,
                output_uri=str(manifest_path),
                message=f"Loaded export manifest with {manifest.get('num_episodes', 0)} episodes.",
                artifacts=manifest.get("artifacts"),
                num_episodes=int(manifest.get("num_episodes", 0)),
                created_at=created_at,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _hub_upload_path(record: ExportRecord) -> Path:
        artifacts = record.artifacts or {}
        lance_artifact = artifacts.get("lance_subset")
        if isinstance(lance_artifact, dict):
            root = lance_artifact.get("root")
            if isinstance(root, str) and Path(root).exists():
                return Path(root)
        if record.output_uri:
            export_dir = Path(record.output_uri).parent
            if export_dir.exists():
                return export_dir
        raise HTTPException(status_code=400, detail="Export artifact directory does not exist.")

    @staticmethod
    def _hub_repo_id(record: ExportRecord) -> str | None:
        explicit = os.getenv("RLLAB_HF_REPO_ID")
        if explicit:
            return explicit
        namespace = os.getenv("RLLAB_HF_NAMESPACE")
        if not namespace:
            return None
        # The HF dataset repo is keyed by dataset_id; each curated export becomes
        # a new commit (and optionally a tag via RLLAB_HF_REVISION) on the same
        # repo, not a separate <id>-curated-<hash> repo. Set
        # RLLAB_HF_CURATED_REPO_PER_EXPORT=1 to fall back to the legacy naming.
        if _truthy_env("RLLAB_HF_CURATED_REPO_PER_EXPORT"):
            name = _hub_repo_name(f"{record.dataset_id}-curated-{record.export_id[:8]}")
            return f"{namespace.rstrip('/')}/{name}"
        return f"{namespace.rstrip('/')}/{_hub_repo_name(record.dataset_id)}"

    def _record_hub_upload(
        self,
        record: ExportRecord,
        response: ExportHubUploadResponse,
    ) -> None:
        artifacts = dict(record.artifacts or {})
        artifacts["huggingface_hub"] = {
            "repo_id": response.repo_id,
            "repo_url": response.repo_url,
            "uploaded_path": response.uploaded_path,
            "revision": response.revision,
            "commit_url": response.commit_url,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        updated = model_copy(record, update={"artifacts": artifacts})
        if record.output_uri:
            manifest_path = Path(record.output_uri)
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["artifacts"] = artifacts
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2, default=str),
                        encoding="utf-8",
                    )
                except (OSError, json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Failed to persist Hugging Face upload metadata for %s",
                        record.export_id,
                    )
        self._records[record.export_id] = updated

    def _write_manifest(
        self,
        record: ExportRecord,
        payload: ExportCreateRequest,
        manifest_path: Path,
    ) -> ExportRecord:
        episodes = []
        episode_records = []
        annotations_by_episode = {}
        missing_episodes = []
        clip_export = _clip_export_options(payload)
        for episode_index in record.episode_indices:
            episode = store.get_episode(record.dataset_id, episode_index)
            if episode is None:
                missing_episodes.append(episode_index)
                continue
            accepted_annotations = [
                annotation
                for annotation in annotation_store.list(record.dataset_id, episode_index=episode_index)
                if annotation.review_status in {ReviewStatus.accepted, ReviewStatus.edited}
            ]
            episode_records.append(episode)
            annotations_by_episode[episode_index] = accepted_annotations
            episodes.append(
                {
                    "episode_index": episode.episode_index,
                    "task_index": episode.task_index,
                    "length": episode.length,
                    "success_label": episode.success_label,
                    "quality_score": episode.quality_score,
                    "review_status": episode.review_status,
                    "caption": episode.caption,
                    "split": episode.split,
                    "annotations": [model_dump(annotation) for annotation in accepted_annotations],
                }
            )

        if not episodes:
            return model_copy(
                record,
                update={
                    "status": JobStatus.failed,
                    "output_uri": None,
                    "message": f"No exportable episodes found. Missing episodes: {missing_episodes}.",
                }
            )

        artifacts = {}
        if payload.format == ExportFormat.lerobot:
            timeseries_by_episode = {
                episode.episode_index: timeseries
                for episode in episode_records
                if (timeseries := store.get_episode_timeseries(record.dataset_id, episode.episode_index))
                is not None
            }
            video_blobs_by_episode = {
                episode.episode_index: self._video_blobs(record.dataset_id, episode)
                for episode in episode_records
            }
            artifacts["lerobot_v3"] = write_lerobot_v3_snapshot(
                manifest_path.parent,
                dataset_id=record.dataset_id,
                episodes=episode_records,
                annotations_by_episode=annotations_by_episode,
                version_description=payload.version_description,
                timeseries_by_episode=timeseries_by_episode,
                video_blobs_by_episode=video_blobs_by_episode,
            )
            validation = artifacts["lerobot_v3"].get("validation", {})
            if not validation.get("metadata_ok", False):
                errors = validation.get("errors") or ["LeRobot export validation failed."]
                return model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "output_uri": None,
                        "message": f"LeRobot export validation failed: {errors[0]}",
                        "artifacts": artifacts,
                    },
                )
        elif payload.format == ExportFormat.lance:
            try:
                frames_by_episode = {
                    episode.episode_index: self._frame_records(record.dataset_id, episode)
                    for episode in episode_records
                }
                artifacts["lance_subset"] = write_lance_subset(
                    manifest_path.parent,
                    dataset_id=record.dataset_id,
                    episodes=episode_records,
                    annotations_by_episode=annotations_by_episode,
                    frames_by_episode=frames_by_episode,
                    video_blobs_by_episode={
                        episode.episode_index: self._video_blobs(record.dataset_id, episode)
                        for episode in episode_records
                    },
                    version_description=payload.version_description,
                    clip_export_options=clip_export,
                )
                validation = artifacts["lance_subset"].get("validation", {})
                if not validation.get("metadata_ok", False):
                    errors = validation.get("errors") or ["Lance subset export validation failed."]
                    return model_copy(
                        record,
                        update={
                            "status": JobStatus.failed,
                            "output_uri": None,
                            "message": f"Lance subset export validation failed: {errors[0]}",
                            "artifacts": artifacts,
                        },
                    )
            except LanceExportDependencyError as exc:
                return model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "output_uri": None,
                        "message": str(exc),
                    },
                )
            except (NotImplementedError, ValueError) as exc:
                return model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "output_uri": None,
                        "message": str(exc),
                    },
                )
        elif payload.format == ExportFormat.jsonl:
            artifacts["jsonl"] = write_jsonl_export(
                manifest_path.parent,
                dataset_id=record.dataset_id,
                episodes=episode_records,
                annotations_by_episode=annotations_by_episode,
                version_description=payload.version_description,
            )
        elif payload.format == ExportFormat.vla:
            timeseries_by_episode = {
                episode.episode_index: timeseries
                for episode in episode_records
                if (timeseries := store.get_episode_timeseries(record.dataset_id, episode.episode_index))
                is not None
            }
            artifacts["vla_jsonl"] = write_vla_jsonl_export(
                manifest_path.parent,
                dataset_id=record.dataset_id,
                episodes=episode_records,
                annotations_by_episode=annotations_by_episode,
                timeseries_by_episode=timeseries_by_episode,
                version_description=payload.version_description,
            )
        elif payload.format == ExportFormat.hf_dataset:
            timeseries_by_episode = {
                episode.episode_index: timeseries
                for episode in episode_records
                if (timeseries := store.get_episode_timeseries(record.dataset_id, episode.episode_index))
                is not None
            }
            try:
                artifacts["hf_dataset"] = write_hf_dataset_export(
                    manifest_path.parent,
                    dataset_id=record.dataset_id,
                    episodes=episode_records,
                    annotations_by_episode=annotations_by_episode,
                    timeseries_by_episode=timeseries_by_episode,
                    version_description=payload.version_description,
                )
            except HFDatasetExportDependencyError as exc:
                return model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "output_uri": None,
                        "message": str(exc),
                    },
                )
            validation = artifacts["hf_dataset"].get("validation", {})
            if not validation.get("metadata_ok", False):
                errors = validation.get("errors") or ["Hugging Face Dataset export validation failed."]
                return model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "output_uri": None,
                        "message": f"Hugging Face Dataset export validation failed: {errors[0]}",
                        "artifacts": artifacts,
                    },
                )
        else:
            return model_copy(
                record,
                update={
                    "status": JobStatus.failed,
                    "output_uri": None,
                    "message": f"Unsupported export format: {payload.format}",
                },
            )

        created_at = datetime.now(timezone.utc)
        manifest = {
            "export_id": record.export_id,
            "dataset_id": record.dataset_id,
            "format": record.format,
            "splits": payload.splits,
            "version_description": payload.version_description,
            "publish_uri": payload.publish_uri or configured_export_publish_uri(),
            "created_at": created_at.isoformat(),
            "num_episodes": len(episodes),
            "episode_indices": [episode["episode_index"] for episode in episodes],
            "missing_episode_indices": missing_episodes,
            "clip_export": clip_export,
            "artifacts": artifacts,
            "episodes": episodes,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        publish_uri = manifest.get("publish_uri")
        if publish_uri:
            try:
                publish_artifact = publish_directory(
                    manifest_path.parent,
                    str(publish_uri),
                    exclude_names={"manifest.json"},
                )
                publish_artifact["manifest_uri"] = f"{str(publish_uri).rstrip('/')}/manifest.json"
                artifacts["publish"] = publish_artifact
                manifest["artifacts"] = artifacts
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, default=str),
                    encoding="utf-8",
                )
                publish_file(manifest_path, str(publish_uri), relative_path="manifest.json")
            except (ArtifactPublishDependencyError, ArtifactPublishError) as exc:
                artifacts["publish"] = {
                    "destination_uri": str(publish_uri),
                    "metadata_ok": False,
                    "errors": [str(exc)],
                }
                manifest["artifacts"] = artifacts
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, default=str),
                    encoding="utf-8",
                )
                return model_copy(
                    record,
                    update={
                        "status": JobStatus.failed,
                        "output_uri": str(manifest_path),
                        "message": f"Export artifact publishing failed: {exc}",
                        "artifacts": artifacts,
                    },
                )
        if self._versions is not None:
            self._versions.append(
                create_export_version_record(
                    version_id=record.export_id,
                    dataset_id=record.dataset_id,
                    description=payload.version_description,
                    filter_query=f"episode_indices={manifest['episode_indices']}",
                    num_episodes=len(episodes),
                    num_frames=sum(int(episode["length"] or 0) for episode in episodes),
                    export_format=str(record.format.value),
                    export_uri=str(manifest_path),
                )
            )
        message = f"Exported {len(episodes)} episode manifest."
        if missing_episodes:
            message = f"{message} Missing episodes skipped: {missing_episodes}."
        applied_ids = [
            annotation.annotation_id
            for annotations in annotations_by_episode.values()
            for annotation in annotations
        ]
        if applied_ids:
            try:
                annotation_store.mark_applied(applied_ids, export_id=record.export_id)
            except Exception as exc:  # noqa: BLE001 — best-effort, must not fail the export
                logger.warning(
                    "Failed to mark %d annotations as applied for export %s: %s",
                    len(applied_ids),
                    record.export_id,
                    exc,
                )
        return model_copy(
            record,
            update={
                "status": JobStatus.succeeded,
                "episode_indices": [episode["episode_index"] for episode in episodes],
                "message": message,
                "artifacts": artifacts,
                "num_episodes": len(episodes),
                "created_at": created_at,
            }
        )

    @staticmethod
    def _video_blobs(dataset_id: str, episode: EpisodeDetail) -> dict[str, bytes]:
        blobs: dict[str, bytes] = {}
        for camera in episode.camera_names:
            blob = store.get_video_blob(dataset_id, episode.episode_index, camera)
            if blob is not None:
                blobs[camera] = blob
        return blobs

    @staticmethod
    def _episode_indices_for_splits(payload: ExportCreateRequest) -> list[int]:
        episodes = list_all_episodes(store, payload.dataset_id)
        if not payload.splits:
            return [episode.episode_index for episode in episodes]
        wanted = {split for split in payload.splits if split}
        return [
            episode.episode_index
            for episode in episodes
            if episode.split is not None and episode.split in wanted
        ]

    @staticmethod
    def _frame_records(dataset_id: str, episode: EpisodeDetail) -> list[FrameRecord]:
        frames = []
        start_frame = 0
        chunk_size = 1000
        end_frame = (episode.length - 1) if episode.length is not None and episode.length > 0 else None
        while True:
            batch = store.list_frames(
                dataset_id,
                episode.episode_index,
                start_frame=start_frame,
                end_frame=end_frame,
                limit=chunk_size,
            )
            if not batch:
                break
            frames.extend(batch)
            next_start = batch[-1].frame_index + 1
            if next_start <= start_frame:
                break
            start_frame = next_start
            if end_frame is not None and start_frame > end_frame:
                break
            if len(batch) < chunk_size and end_frame is None:
                break
        return frames


exports = ExportStore()


def _truthy_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _hub_repo_name(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip(".-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "robot-data-studio-export"
    return slug[:96].strip(".-") or "robot-data-studio-export"


def _clip_export_options(payload: ExportCreateRequest) -> dict[str, Any]:
    return {
        "clip_label_type": payload.clip_label_type,
        "accepted_clips_only": payload.accepted_clips_only,
        "materialize_skill_clips": payload.materialize_skill_clips,
        "jitter_offsets": payload.jitter_offsets,
        "copies_per_clip": payload.copies_per_clip,
    }
