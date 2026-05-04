from __future__ import annotations

from collections import Counter

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import FullTextSearchRequest, SearchResult
from apps.api.services.embedding_service import tokenize


def full_text_search(
    payload: FullTextSearchRequest,
    *,
    episodes: list[EpisodeListItem],
    annotations: list[AnnotationRecord],
) -> list[SearchResult]:
    query_tokens = tokenize(payload.text)
    if not query_tokens:
        return []
    results: list[SearchResult] = []

    for episode in episodes:
        text = _episode_text(episode)
        score = _text_score(text, query_tokens)
        if score <= 0:
            continue
        results.append(
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=episode.episode_index,
                score=score,
                match_type="full_text_episode",
                label=_snippet(text, query_tokens),
            )
        )

    for annotation in annotations:
        text = _annotation_text(annotation)
        score = _text_score(text, query_tokens)
        if score <= 0:
            continue
        results.append(
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=annotation.episode_index,
                frame_index=(
                    annotation.start_frame
                    if annotation.start_frame == annotation.end_frame
                    else None
                ),
                score=score,
                match_type="full_text_annotation",
                label=_snippet(text, query_tokens),
            )
        )

    results.sort(
        key=lambda result: (
            -(result.score or 0.0),
            result.episode_index,
            result.frame_index if result.frame_index is not None else -1,
        )
    )
    return results[: payload.limit]


def _episode_text(episode: EpisodeListItem) -> str:
    parts = [
        f"episode {episode.episode_index}",
        f"task {episode.task_index}" if episode.task_index is not None else "",
        episode.caption or "",
        f"success {episode.success_label}" if episode.success_label is not None else "",
        f"review {episode.review_status}",
        f"split {episode.split}" if episode.split else "",
    ]
    return " ".join(part for part in parts if part)


def _annotation_text(annotation: AnnotationRecord) -> str:
    return " ".join(
        [
            annotation.label_type,
            annotation.label_value,
            annotation.source.value,
            annotation.review_status.value,
            f"frames {annotation.start_frame} {annotation.end_frame}",
        ]
    )


def _text_score(text: str, query_tokens: list[str]) -> float:
    counts = Counter(tokenize(text))
    if not counts:
        return 0.0
    matched = sum(counts[token] for token in query_tokens)
    coverage = len({token for token in query_tokens if counts[token] > 0}) / len(set(query_tokens))
    return float(matched) + coverage


def _snippet(text: str, query_tokens: list[str]) -> str:
    lowered = text.lower()
    first_index = min(
        (lowered.find(token) for token in query_tokens if token in lowered),
        default=0,
    )
    start = max(0, first_index - 36)
    end = min(len(text), first_index + 96)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"
