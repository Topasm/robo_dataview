from __future__ import annotations

import re
from pathlib import Path

from apps.api.schemas.datasets import DatasetOpenRequest, DatasetRecord, DatasetSummary
from apps.api.schemas.episodes import EpisodeDetail, EpisodeListItem, StateActionSummary
from apps.api.schemas.search import FilterSearchRequest, SearchResult, SemanticSearchRequest


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "dataset"


class LanceDatasetStore:
    """Thin service boundary for Lance-backed dataset access.

    The current implementation keeps a small in-memory fixture so the API and
    web UI can be exercised before the Phase 1 Lance reader is connected.
    """

    def __init__(self) -> None:
        self._datasets: dict[str, DatasetRecord] = {}
        self._summaries: dict[str, DatasetSummary] = {}
        self._episodes: dict[str, list[EpisodeDetail]] = {}
        self._seed_demo_dataset()

    def _seed_demo_dataset(self) -> None:
        dataset_id = "sample-xvla-soft-fold"
        record = DatasetRecord(
            dataset_id=dataset_id,
            name="sample-xvla-soft-fold",
            uri="sample://xvla-soft-fold",
            status="sample",
        )
        episodes = [
            EpisodeDetail(
                dataset_id=dataset_id,
                episode_index=idx,
                task_index=3,
                length=180 + idx * 12,
                success_label=idx % 2 == 0,
                quality_score=0.72 + idx * 0.05,
                review_status="pending" if idx == 1 else "accepted",
                caption="Soft cloth folding trajectory",
                has_vlm_label=idx != 0,
                has_human_label=idx == 2,
                split="train",
                fps=20.0,
                camera_names=["cam_high", "cam_left_wrist", "cam_right_wrist"],
                duration_seconds=(180 + idx * 12) / 20.0,
                language_instruction="Fold the soft cloth neatly.",
            )
            for idx in range(3)
        ]
        self._datasets[dataset_id] = record
        self._episodes[dataset_id] = episodes
        self._summaries[dataset_id] = DatasetSummary(
            dataset_id=dataset_id,
            name=record.name,
            uri=record.uri,
            status=record.status,
            episode_count=len(episodes),
            frame_count=sum(episode.length or 0 for episode in episodes),
            fps=20.0,
            camera_names=["cam_high", "cam_left_wrist", "cam_right_wrist"],
            reviewed_count=2,
            accepted_count=2,
            rejected_count=0,
        )

    def list_datasets(self) -> list[DatasetRecord]:
        return list(self._datasets.values())

    def open_dataset(self, payload: DatasetOpenRequest) -> DatasetRecord:
        name = payload.name or Path(payload.uri).name or payload.uri
        dataset_id = _slug(name)
        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            uri=payload.uri,
            status="registered",
        )
        self._datasets[dataset_id] = record
        self._episodes.setdefault(dataset_id, [])
        self._summaries[dataset_id] = DatasetSummary(
            dataset_id=dataset_id,
            name=name,
            uri=payload.uri,
            status=record.status,
            episode_count=0,
            frame_count=0,
            fps=None,
            camera_names=[],
        )
        return record

    def get_summary(self, dataset_id: str) -> DatasetSummary | None:
        return self._summaries.get(dataset_id)

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[EpisodeListItem]:
        episodes = self._episodes.get(dataset_id, [])
        return [EpisodeListItem(**episode.dict()) for episode in episodes[offset : offset + limit]]

    def get_episode(self, dataset_id: str, episode_index: int) -> EpisodeDetail | None:
        for episode in self._episodes.get(dataset_id, []):
            if episode.episode_index == episode_index:
                return episode
        return None

    def get_state_action_summary(
        self,
        dataset_id: str,
        episode_index: int,
    ) -> StateActionSummary | None:
        episode = self.get_episode(dataset_id, episode_index)
        if episode is None:
            return None
        return StateActionSummary(
            dataset_id=dataset_id,
            episode_index=episode_index,
            frame_count=episode.length or 0,
            state_dim=14,
            action_dim=14,
            state_norm_min=0.0,
            state_norm_max=1.0,
            action_norm_min=0.0,
            action_norm_max=1.0,
        )

    def filter_search(self, payload: FilterSearchRequest) -> list[SearchResult]:
        episodes = self._episodes.get(payload.dataset_id, [])[: payload.limit]
        return [
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=None,
                match_type="filter_stub",
                label=payload.query,
            )
            for episode in episodes
        ]

    def semantic_search(self, payload: SemanticSearchRequest) -> list[SearchResult]:
        episodes = self._episodes.get(payload.dataset_id, [])[: payload.limit]
        return [
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=0.5,
                match_type="semantic_stub",
                label=payload.text,
            )
            for episode in episodes
        ]


store = LanceDatasetStore()
