from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from apps.api.schemas.common import ExportFormat, JobStatus, ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail
from apps.api.schemas.exports import ExportCreateRequest, ExportRecord
from apps.api.schemas.frames import FrameRecord
from apps.api.services.annotation_service import annotation_store
from apps.api.services.lance_export import LanceExportDependencyError, write_lance_subset
from apps.api.services.lance_store import store
from apps.api.services.lerobot_io import write_lerobot_v3_snapshot
from apps.api.services.pydantic_compat import model_copy, model_dump
from apps.api.services.training_export import write_jsonl_export, write_vla_jsonl_export
from apps.api.services.version_service import (
    VersionStore,
    create_export_version_record,
    version_store,
)


EXPORT_ROOT = Path("data/exports")


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
            return ExportRecord(
                export_id=manifest["export_id"],
                dataset_id=manifest["dataset_id"],
                episode_indices=list(manifest.get("episode_indices", [])),
                format=manifest["format"],
                status=JobStatus.succeeded,
                output_uri=str(manifest_path),
                message=f"Loaded export manifest with {manifest.get('num_episodes', 0)} episodes.",
                artifacts=manifest.get("artifacts"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

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
        for episode_index in record.episode_indices:
            episode = store.get_episode(record.dataset_id, episode_index)
            if episode is None:
                missing_episodes.append(episode_index)
                continue
            accepted_annotations = [
                annotation
                for annotation in annotation_store.list(record.dataset_id, episode_index=episode_index)
                if annotation.review_status == ReviewStatus.accepted
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
                    version_description=payload.version_description,
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
            return model_copy(
                record,
                update={
                    "status": JobStatus.failed,
                    "output_uri": None,
                    "message": (
                        "Hugging Face Dataset export is not implemented yet. "
                        "Use format=lerobot for LeRobot/HF-compatible snapshot artifacts "
                        "or format=jsonl for portable caption exports."
                    ),
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

        manifest = {
            "export_id": record.export_id,
            "dataset_id": record.dataset_id,
            "format": record.format,
            "splits": payload.splits,
            "version_description": payload.version_description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "num_episodes": len(episodes),
            "episode_indices": [episode["episode_index"] for episode in episodes],
            "missing_episode_indices": missing_episodes,
            "artifacts": artifacts,
            "episodes": episodes,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
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
        return model_copy(
            record,
            update={
                "status": JobStatus.succeeded,
                "episode_indices": [episode["episode_index"] for episode in episodes],
                "message": message,
                "artifacts": artifacts,
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
        episodes = store.list_episodes(payload.dataset_id, limit=1000, offset=0)
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
