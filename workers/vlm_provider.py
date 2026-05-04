from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Protocol

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.episodes import EpisodeDetail
from workers.keyframe_extractor import KeyframeArtifact, extract_keyframes_from_blob
from workers.vlm_autolabel import AutoLabelConfig, build_vlm_annotation_proposals, select_keyframes

KEYFRAME_CACHE_ROOT = Path("data/cache/keyframes")


@dataclass(frozen=True)
class VlmProviderResult:
    provider: str
    raw_response: dict[str, object]
    proposals: list[AnnotationCreate]


class VlmProvider(Protocol):
    name: str

    def propose(
        self,
        *,
        dataset_id: str,
        episode: EpisodeDetail,
        config: AutoLabelConfig,
        video_blobs: dict[str, bytes] | None = None,
    ) -> VlmProviderResult:
        ...


class HeuristicVlmProvider:
    name = "heuristic-fallback"

    def propose(
        self,
        *,
        dataset_id: str,
        episode: EpisodeDetail,
        config: AutoLabelConfig,
        video_blobs: dict[str, bytes] | None = None,
    ) -> VlmProviderResult:
        proposals = build_vlm_annotation_proposals(dataset_id, episode, config)
        keyframes = select_keyframes(
            max(1, episode.length or 1),
            min_keyframes=config.min_keyframes,
            max_keyframes=config.max_keyframes,
        )
        artifacts = _extract_keyframe_artifacts(
            dataset_id=dataset_id,
            episode=episode,
            config=config,
            keyframes=keyframes,
            video_blobs=video_blobs or {},
        )
        return VlmProviderResult(
            provider=self.name,
            raw_response={
                "provider": self.name,
                "model": config.model,
                "prompt_template": config.prompt_template,
                "prompt_version": config.prompt_version,
                "episode_index": episode.episode_index,
                "keyframes": keyframes,
                "keyframe_images": [_artifact_payload(artifact) for artifact in artifacts],
                "keyframe_image_count": len(artifacts),
                "proposal_count": len(proposals),
            },
            proposals=proposals,
        )


def get_vlm_provider(model: str) -> VlmProvider:
    # The MVP only has a deterministic provider. The model string is preserved
    # in the job record and raw response so future providers can route on it.
    return HeuristicVlmProvider()


def _extract_keyframe_artifacts(
    *,
    dataset_id: str,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
    keyframes: list[int],
    video_blobs: dict[str, bytes],
) -> list[KeyframeArtifact]:
    if not video_blobs or not keyframes:
        return []

    output_dir = (
        KEYFRAME_CACHE_ROOT
        / _dataset_cache_dir(dataset_id)
        / f"episode_{episode.episode_index:06d}"
        / f"{config.prompt_template}_{config.prompt_version}"
    )
    artifacts: list[KeyframeArtifact] = []
    for camera, blob in sorted(video_blobs.items()):
        artifacts.extend(
            extract_keyframes_from_blob(
                blob=blob,
                camera=camera,
                frame_indices=keyframes,
                output_dir=output_dir,
            )
        )
    return artifacts


def _artifact_payload(artifact: KeyframeArtifact) -> dict[str, object]:
    return {
        "camera": artifact.camera,
        "frame_index": artifact.frame_index,
        "uri": artifact.uri,
        "width": artifact.width,
        "height": artifact.height,
        "content_type": artifact.content_type,
    }


def _dataset_cache_dir(dataset_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_id).strip("._-")
    digest = hashlib.sha1(dataset_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:80] or 'dataset'}-{digest}"
