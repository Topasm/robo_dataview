"""Visual embedding worker utilities.

This module keeps image/video embedding generation explicit and batch-oriented.
Semantic text search can rebuild text vectors cheaply, but visual embeddings
require video decode and optional model weights, so they should run through a
job path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import re
from typing import Protocol

from apps.api.schemas.episodes import EpisodeDetail
from apps.api.services.embedding_service import (
    EMBEDDING_DIM,
    EmbeddingRecord,
    create_embedding_id,
)
from apps.api.services.lance_store import LanceDatasetStore, VideoSource
from workers.keyframe_extractor import (
    KeyframeArtifact,
    KeyframeExtractionUnavailable,
    extract_keyframes_from_blob,
    extract_keyframes_from_path,
)
from workers.vlm_autolabel import select_keyframes


VISUAL_EMBEDDING_CACHE_ROOT = Path("data/cache/visual_embeddings")


@dataclass(frozen=True)
class VisualEmbeddingConfig:
    model: str = "deterministic-visual"
    camera_names: tuple[str, ...] = ()
    min_keyframes: int = 8
    max_keyframes: int = 16


@dataclass(frozen=True)
class VisualEmbeddingResult:
    records: list[EmbeddingRecord]
    artifact_count: int
    skipped: list[str]
    provider: str


class VisualEmbeddingProvider(Protocol):
    source_model: str

    def embed_images(self, image_paths: list[Path]) -> list[list[float]]:
        ...


class DeterministicVisualEmbeddingProvider:
    source_model = "deterministic-image-hash-v1"

    def embed_images(self, image_paths: list[Path]) -> list[list[float]]:
        return [_hash_image_embedding(path) for path in image_paths]


class TransformersVisionEmbeddingProvider:
    """Optional CLIP/SigLIP/DINO-style image embedding provider.

    This path is intentionally optional. It is selected explicitly via
    `clip:<model>`, `siglip:<model>`, `dino:<model>`, `transformers:<model>`,
    or `ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_PROVIDER=transformers`.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.source_model = f"transformers-vision:{model_name}"
        try:
            import torch
            from PIL import Image
            from transformers import AutoModel, AutoProcessor
        except ImportError as exc:
            raise RuntimeError(
                "transformers, torch, and pillow are required for visual model embeddings."
            ) from exc
        self._torch = torch
        self._image = Image
        self._processor = AutoProcessor.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name)
        self._model.eval()

    def embed_images(self, image_paths: list[Path]) -> list[list[float]]:
        if not image_paths:
            return []
        images = [self._image.open(path).convert("RGB") for path in image_paths]
        try:
            inputs = self._processor(images=images, return_tensors="pt")
            with self._torch.no_grad():
                if hasattr(self._model, "get_image_features"):
                    outputs = self._model.get_image_features(**inputs)
                    rows = outputs.tolist()
                else:
                    outputs = self._model(**inputs)
                    rows = _rows_from_transformers_output(outputs)
        finally:
            for image in images:
                image.close()
        return [_normalize(row) for row in rows]


def build_visual_embedding_records(
    *,
    dataset_store: LanceDatasetStore,
    dataset_id: str,
    episode_indices: list[int],
    config: VisualEmbeddingConfig,
    provider: VisualEmbeddingProvider | None = None,
    cache_root: Path = VISUAL_EMBEDDING_CACHE_ROOT,
) -> VisualEmbeddingResult:
    provider = provider or get_visual_embedding_provider(config.model)
    episodes = _target_episodes(dataset_store, dataset_id, episode_indices)
    records: list[EmbeddingRecord] = []
    artifact_count = 0
    skipped: list[str] = []
    now = datetime.now(timezone.utc)

    for episode in episodes:
        keyframes = select_keyframes(
            episode.length or 0,
            min_keyframes=config.min_keyframes,
            max_keyframes=config.max_keyframes,
        )
        if not keyframes:
            skipped.append(f"episode {episode.episode_index}: no keyframes selected")
            continue
        cameras = config.camera_names or tuple(episode.camera_names)
        if not cameras:
            skipped.append(f"episode {episode.episode_index}: no cameras available")
            continue
        for camera in cameras:
            source = dataset_store.get_video_source(dataset_id, episode.episode_index, camera)
            if source is None:
                skipped.append(f"episode {episode.episode_index} {camera}: video missing")
                continue
            try:
                artifacts = _extract_artifacts(
                    source=source,
                    dataset_id=dataset_id,
                    episode=episode,
                    camera=camera,
                    keyframes=keyframes,
                    config=config,
                    cache_root=cache_root,
                )
            except KeyframeExtractionUnavailable as exc:
                skipped.append(f"episode {episode.episode_index} {camera}: {exc}")
                continue
            if not artifacts:
                skipped.append(f"episode {episode.episode_index} {camera}: no images decoded")
                continue
            image_paths = [Path(artifact.uri) for artifact in artifacts]
            embeddings = provider.embed_images(image_paths)
            if len(embeddings) != len(artifacts):
                raise ValueError("Visual embedding provider returned the wrong number of vectors")
            artifact_count += len(artifacts)
            records.extend(
                _record_from_artifact(
                    dataset_id=dataset_id,
                    episode_index=episode.episode_index,
                    artifact=artifact,
                    embedding=embedding,
                    provider=provider,
                    created_at=now,
                )
                for artifact, embedding in zip(artifacts, embeddings)
            )

    return VisualEmbeddingResult(
        records=records,
        artifact_count=artifact_count,
        skipped=skipped,
        provider=provider.source_model,
    )


def get_visual_embedding_provider(model: str | None = None) -> VisualEmbeddingProvider:
    provider_name = os.getenv("ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_PROVIDER", "").lower()
    model_name = _visual_model_name(model)
    if provider_name == "transformers" or _is_transformers_model(model or ""):
        return TransformersVisionEmbeddingProvider(model_name)
    return DeterministicVisualEmbeddingProvider()


def _target_episodes(
    dataset_store: LanceDatasetStore,
    dataset_id: str,
    episode_indices: list[int],
) -> list[EpisodeDetail]:
    if not episode_indices:
        episode_indices = [
            episode.episode_index
            for episode in dataset_store.list_episodes(dataset_id, limit=1000, offset=0)
        ]
    episodes: list[EpisodeDetail] = []
    for episode_index in episode_indices:
        episode = dataset_store.get_episode(dataset_id, episode_index)
        if episode is not None:
            episodes.append(episode)
    return episodes


def _extract_artifacts(
    *,
    source: VideoSource,
    dataset_id: str,
    episode: EpisodeDetail,
    camera: str,
    keyframes: list[int],
    config: VisualEmbeddingConfig,
    cache_root: Path,
) -> list[KeyframeArtifact]:
    output_dir = (
        cache_root
        / _safe_name(dataset_id)
        / f"episode_{episode.episode_index:06d}"
        / _safe_name(config.model)
        / _safe_name(camera)
    )
    if source.path is not None:
        return extract_keyframes_from_path(
            path=source.path,
            camera=camera,
            frame_indices=keyframes,
            output_dir=output_dir,
        )
    blob = source.read_all()
    if blob is None:
        return []
    return extract_keyframes_from_blob(
        blob=blob,
        camera=camera,
        frame_indices=keyframes,
        output_dir=output_dir,
    )


def _record_from_artifact(
    *,
    dataset_id: str,
    episode_index: int,
    artifact: KeyframeArtifact,
    embedding: list[float],
    provider: VisualEmbeddingProvider,
    created_at: datetime,
) -> EmbeddingRecord:
    source_uri = artifact.uri
    content_hash = _file_sha1(Path(source_uri))
    text = f"{artifact.camera} frame {artifact.frame_index} visual keyframe"
    scope = f"visual:{provider.source_model}:{artifact.camera}:{artifact.frame_index}:{content_hash}"
    return EmbeddingRecord(
        embedding_id=create_embedding_id(dataset_id, scope=scope, text=text),
        episode_index=episode_index,
        frame_index=artifact.frame_index,
        clip_start_frame=artifact.frame_index,
        clip_end_frame=artifact.frame_index,
        modality="image",
        embedding=_normalize(embedding),
        text=text,
        source_model=provider.source_model,
        created_at=created_at,
        camera=artifact.camera,
        source_uri=source_uri,
        content_hash=content_hash,
    )


def _file_sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _hash_image_embedding(path: Path) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).digest()
    for index, byte in enumerate(digest):
        bucket = index % EMBEDDING_DIM
        vector[bucket] += (byte / 255.0) - 0.5
    return _normalize(vector)


def _rows_from_transformers_output(outputs: object) -> list[list[float]]:
    pooler = getattr(outputs, "pooler_output", None)
    if pooler is not None:
        return pooler.tolist()
    hidden = getattr(outputs, "last_hidden_state", None)
    if hidden is not None:
        return hidden.mean(dim=1).tolist()
    raise ValueError("Visual model output does not include image embeddings")


def _normalize(value: object) -> list[float]:
    if not isinstance(value, list):
        raise ValueError("Embedding vector must be a list")
    vector = [float(item) for item in value]
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector
    return [item / norm for item in vector]


def _visual_model_name(model: str | None) -> str:
    configured = os.getenv("ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_MODEL")
    if configured:
        return configured
    if model:
        for prefix in ("clip:", "siglip:", "dino:", "transformers:"):
            if model.lower().startswith(prefix):
                return model.split(":", 1)[1]
    return "openai/clip-vit-base-patch32"


def _is_transformers_model(model: str) -> bool:
    lower = model.lower()
    return lower.startswith(("clip:", "siglip:", "dino:", "transformers:"))


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("_") or "value"
