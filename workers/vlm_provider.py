from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.episodes import EpisodeDetail
from workers.vlm_autolabel import AutoLabelConfig, build_vlm_annotation_proposals, select_keyframes


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
    ) -> VlmProviderResult:
        proposals = build_vlm_annotation_proposals(dataset_id, episode, config)
        keyframes = select_keyframes(
            max(1, episode.length or 1),
            min_keyframes=config.min_keyframes,
            max_keyframes=config.max_keyframes,
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
                "proposal_count": len(proposals),
            },
            proposals=proposals,
        )


def get_vlm_provider(model: str) -> VlmProvider:
    # The MVP only has a deterministic provider. The model string is preserved
    # in the job record and raw response so future providers can route on it.
    return HeuristicVlmProvider()
