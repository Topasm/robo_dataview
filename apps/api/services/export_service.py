from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import urlparse
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
        record = self._with_hub_defaults(self._write_manifest(record, payload, manifest_path))
        self._records[export_id] = record
        return record

    def get(self, export_id: str) -> ExportRecord:
        record = self._records.get(export_id)
        if record is None:
            record = self._record_from_manifest(EXPORT_ROOT / export_id / "manifest.json")
        if record is None:
            raise HTTPException(status_code=404, detail="Export not found")
        record = self._with_hub_defaults(record)
        self._records[export_id] = record
        return record

    def list(self, *, dataset_id: str | None = None) -> list[ExportRecord]:
        records = [self._with_hub_defaults(record) for record in self._records.values()]
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
                    "Hugging Face repo is not configured. "
                    "한국어 안내: 업로드할 HF repo를 찾지 못했습니다. "
                    "원본 HF dataset을 열었으면 repo id 입력칸에 owner/name을 넣거나, "
                    "API 실행 환경에 RLLAB_HF_REPO_ID=owner/name 또는 "
                    "RLLAB_HF_NAMESPACE=owner를 설정하세요."
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
                delete_patterns=["*"],
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
        self._prune_previous_exports(record)
        self._compact_uploaded_annotations(record)
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
            record = ExportRecord(
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
                hub_repo_id=_string_or_none(
                    (manifest.get("hub_upload") or {}).get("default_repo_id")
                    if isinstance(manifest.get("hub_upload"), dict)
                    else None
                ),
                hub_repo_source=_string_or_none(
                    (manifest.get("hub_upload") or {}).get("repo_source")
                    if isinstance(manifest.get("hub_upload"), dict)
                    else None
                ),
            )
            return self._with_hub_defaults(record)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _with_hub_defaults(record: ExportRecord) -> ExportRecord:
        repo_id, repo_source = ExportStore._hub_repo_target(record)
        if repo_source and repo_source.startswith("env:"):
            default_repo_id = repo_id
            default_repo_source = repo_source
        else:
            default_repo_id = record.hub_repo_id or repo_id
            default_repo_source = record.hub_repo_source or repo_source
        return model_copy(
            record,
            update={
                "hub_repo_id": default_repo_id,
                "hub_repo_source": default_repo_source,
            },
        )

    @staticmethod
    def _hub_upload_path(record: ExportRecord) -> Path:
        artifacts = record.artifacts or {}
        published_artifact = artifacts.get("published_lance")
        if isinstance(published_artifact, dict):
            root = published_artifact.get("root")
            if isinstance(root, str) and Path(root).exists():
                return Path(root)
        lance_artifact = artifacts.get("lance_subset")
        if isinstance(lance_artifact, dict):
            published_lance = lance_artifact.get("published_lance")
            if isinstance(published_lance, dict):
                root = published_lance.get("root")
                if isinstance(root, str) and Path(root).exists():
                    return Path(root)
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
        repo_id, _source = ExportStore._hub_repo_target(record)
        return repo_id

    @staticmethod
    def _hub_repo_target(record: ExportRecord) -> tuple[str | None, str | None]:
        explicit = os.getenv("RLLAB_HF_REPO_ID")
        if explicit:
            return explicit, "env:RLLAB_HF_REPO_ID"
        source_repo = _source_hub_repo_id(record.dataset_id)
        if source_repo:
            return source_repo, "source_dataset"
        namespace = os.getenv("RLLAB_HF_NAMESPACE")
        if not namespace:
            return None, None
        # The HF dataset repo is keyed by dataset_id; each curated export becomes
        # a new commit (and optionally a tag via RLLAB_HF_REVISION) on the same
        # repo, not a separate <id>-curated-<hash> repo. Set
        # RLLAB_HF_CURATED_REPO_PER_EXPORT=1 to fall back to the legacy naming.
        if _truthy_env("RLLAB_HF_CURATED_REPO_PER_EXPORT"):
            name = _hub_repo_name(f"{record.dataset_id}-curated-{record.export_id[:8]}")
            return f"{namespace.rstrip('/')}/{name}", "env:RLLAB_HF_NAMESPACE"
        return (
            f"{namespace.rstrip('/')}/{_hub_repo_name(record.dataset_id)}",
            "env:RLLAB_HF_NAMESPACE",
        )

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

    def _prune_previous_exports(self, keep: ExportRecord) -> None:
        pruned: list[str] = []
        for manifest_path in sorted(EXPORT_ROOT.glob("*/manifest.json")):
            if manifest_path.parent.name == keep.export_id:
                continue
            other = self._record_from_manifest(manifest_path)
            if other is None or other.dataset_id != keep.dataset_id:
                continue
            try:
                shutil.rmtree(manifest_path.parent)
            except OSError:
                logger.warning("Failed to prune previous export %s", manifest_path.parent)
                continue
            pruned.append(other.export_id)
            self._records.pop(other.export_id, None)
        if pruned and keep.output_uri:
            manifest_path = Path(keep.output_uri)
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    hub_upload = dict(manifest.get("hub_upload") or {})
                    hub_upload["pruned_export_ids"] = pruned
                    manifest["hub_upload"] = hub_upload
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2, default=str),
                        encoding="utf-8",
                    )
                except (OSError, json.JSONDecodeError, TypeError):
                    logger.warning("Failed to persist pruned export ids for %s", keep.export_id)

    def _compact_uploaded_annotations(self, record: ExportRecord) -> None:
        try:
            summary = annotation_store.compact_dataset(
                record.dataset_id,
                keep_history=False,
            )
        except Exception as exc:  # noqa: BLE001 - upload already succeeded; record cleanup failure.
            logger.warning(
                "Failed to compact annotations after Hub upload for %s: %s",
                record.dataset_id,
                exc,
            )
            summary = {
                "dataset_id": record.dataset_id,
                "metadata_ok": False,
                "error": str(exc),
            }
        if not record.output_uri:
            return
        manifest_path = Path(record.output_uri)
        if not manifest_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            hub_upload = dict(manifest.get("hub_upload") or {})
            hub_upload["annotation_compaction"] = summary
            manifest["hub_upload"] = hub_upload
            manifest_path.write_text(
                json.dumps(manifest, indent=2, default=str),
                encoding="utf-8",
            )
        except (OSError, json.JSONDecodeError, TypeError):
            logger.warning("Failed to persist annotation compaction for %s", record.export_id)

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
                published_lance = artifacts["lance_subset"].get("published_lance")
                if isinstance(published_lance, dict):
                    artifacts["published_lance"] = published_lance
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

        selected_episode_indices = [int(episode["episode_index"]) for episode in episodes]
        materialized_episode_indices = selected_episode_indices
        materialized_episodes = episodes
        materialized_num_episodes = len(episodes)
        materialized_num_frames = sum(int(episode["length"] or 0) for episode in episodes)
        if payload.format == ExportFormat.lance:
            lance_validation = artifacts.get("lance_subset", {}).get("validation", {})
            if isinstance(lance_validation, dict):
                lance_metadata = artifacts.get("lance_subset", {})
                excluded: set[int] = set()
                metadata_path = (lance_metadata.get("files") or {}).get("metadata")
                if isinstance(metadata_path, str) and Path(metadata_path).exists():
                    try:
                        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
                        excluded = {
                            int(index)
                            for index in metadata.get("excluded_episode_indices", [])
                        }
                    except (OSError, TypeError, ValueError, json.JSONDecodeError):
                        excluded = set()
                materialized_episodes = [
                    episode
                    for episode in episodes
                    if int(episode["episode_index"]) not in excluded
                ]
                materialized_episode_indices = [
                    int(episode["episode_index"]) for episode in materialized_episodes
                ]
                materialized_num_episodes = int(
                    lance_validation.get("episode_count") or len(materialized_episodes)
                )
                materialized_num_frames = int(
                    lance_validation.get("frame_count")
                    or sum(int(episode["length"] or 0) for episode in materialized_episodes)
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
            "num_episodes": materialized_num_episodes,
            "episode_indices": materialized_episode_indices,
            "requested_episode_indices": selected_episode_indices,
            "missing_episode_indices": missing_episodes,
            "clip_export": clip_export,
            "artifacts": artifacts,
            "episodes": materialized_episodes,
        }
        hub_repo_id, hub_repo_source = self._hub_repo_target(record)
        if hub_repo_id:
            manifest["hub_upload"] = {
                "default_repo_id": hub_repo_id,
                "repo_source": hub_repo_source,
                "hint_ko": (
                    "HF 업로드는 이 repo에 새 commit으로 올라갑니다. "
                    "다른 repo로 올리려면 UI의 repo id 입력칸을 바꾸세요."
                ),
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
                    num_episodes=materialized_num_episodes,
                    num_frames=materialized_num_frames,
                    export_format=str(record.format.value),
                    export_uri=str(manifest_path),
                )
            )
        message = f"Exported {materialized_num_episodes} episode manifest."
        if missing_episodes:
            message = f"{message} Missing episodes skipped: {missing_episodes}."
        if materialized_num_episodes != len(episodes):
            message = (
                f"{message} Excluded {len(episodes) - materialized_num_episodes} "
                "deleted episode(s)."
            )
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
                "episode_indices": materialized_episode_indices,
                "message": message,
                "artifacts": artifacts,
                "num_episodes": materialized_num_episodes,
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


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _source_hub_repo_id(dataset_id: str) -> str | None:
    try:
        summary = store.get_summary(dataset_id)
    except Exception:  # noqa: BLE001 - repo inference is best-effort only
        return None
    if summary is None:
        return None
    return _infer_hub_repo_id(summary.uri)


def _infer_hub_repo_id(uri: str | None) -> str | None:
    if not uri:
        return None
    direct = _repo_id_from_text(uri)
    if direct:
        return direct

    path = _local_path_from_uri(uri)
    if path is None or not path.exists():
        return None

    for manifest_path in (path / "manifest.json", path / "metadata.json"):
        if not manifest_path.exists():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        repo_id = _repo_id_from_manifest(payload)
        if repo_id:
            return repo_id

    for text_path in (path / "README.md", path / ".git" / "config"):
        if not text_path.exists():
            continue
        try:
            repo_id = _repo_id_from_text(text_path.read_text(encoding="utf-8"))
        except OSError:
            repo_id = None
        if repo_id:
            return repo_id
    return None


def _local_path_from_uri(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return Path(parsed.path).expanduser()
    if parsed.scheme and parsed.scheme != "":
        return None
    return Path(uri).expanduser()


def _repo_id_from_manifest(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in (
        "repo_id",
        "hf_repo_id",
        "source_repo_id",
        "source_dataset",
        "source_dataset_url",
        "dataset_url",
    ):
        value = payload.get(key)
        if isinstance(value, str):
            repo_id = _repo_id_from_text(value)
            if repo_id:
                return repo_id
            if _looks_like_repo_id(value):
                return value.strip().removesuffix(".git")
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        hub = artifacts.get("huggingface_hub")
        if isinstance(hub, dict):
            return _repo_id_from_manifest(hub)
    return None


def _repo_id_from_text(text: str) -> str | None:
    patterns = (
        r"hf://datasets/([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)",
        r"(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/datasets/([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)",
        r"git@(?:huggingface\.co|hf\.co):datasets/([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)(?:\.git)?",
        r"(?m)^#\s+([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).removesuffix(".git")
    stripped = text.strip().removesuffix(".git")
    if _looks_like_repo_id(stripped):
        return stripped
    return None


def _looks_like_repo_id(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*",
            value.strip(),
        )
    )


def _clip_export_options(payload: ExportCreateRequest) -> dict[str, Any]:
    return {
        "clip_label_type": payload.clip_label_type,
        "accepted_clips_only": payload.accepted_clips_only,
        "materialize_skill_clips": payload.materialize_skill_clips,
        "jitter_offsets": payload.jitter_offsets,
        "copies_per_clip": payload.copies_per_clip,
    }


exports = ExportStore()
