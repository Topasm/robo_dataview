from __future__ import annotations

from typing import Any


def list_all_episodes(dataset_store: Any, dataset_id: str, *, batch_size: int = 1000) -> list[Any]:
    """Return every episode from a paginated dataset store."""
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    episodes: list[Any] = []
    offset = 0
    while True:
        batch = dataset_store.list_episodes(dataset_id, limit=batch_size, offset=offset)
        if not batch:
            break
        episodes.extend(batch)
        if len(batch) < batch_size:
            break
        offset += len(batch)
    return episodes
