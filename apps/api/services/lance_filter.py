from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.api.schemas.episodes import EpisodeListItem


class LanceFilterEngine:
    def __init__(
        self,
        owner: Any,
        *,
        parse_filter_query: Callable[[str], list[tuple[str, str, Any]]],
        lance_filter_expression: Callable[[list[tuple[str, str, Any]], list[str]], str | None],
        matches_filter: Callable[[Any, str, str, Any], bool],
        metadata_columns: Callable[[list[str]], list[str]],
        count_rows: Callable[[Any], int],
        rows_from_table: Callable[[Any], list[dict[str, Any]]],
    ) -> None:
        self.owner = owner
        self.parse_filter_query = parse_filter_query
        self.lance_filter_expression = lance_filter_expression
        self.matches_filter = matches_filter
        self.metadata_columns = metadata_columns
        self.count_rows = count_rows
        self.rows_from_table = rows_from_table

    def filter_episode_items(
        self,
        dataset_id: str,
        query: str,
        *,
        limit: int | None = None,
    ) -> list[EpisodeListItem]:
        try:
            filters = self.parse_filter_query(query)
        except ValueError:
            return []
        bundle = self.owner._bundles.get(dataset_id)
        if bundle is not None:
            pushed = self.filter_lance_episode_items(
                dataset_id,
                bundle,
                filters,
                limit=limit,
            )
            if pushed is not None:
                return pushed

        matched: list[EpisodeListItem] = []
        offset = 0
        batch_size = 1000
        while limit is None or len(matched) < limit:
            episodes = self.owner.list_episodes(dataset_id, limit=batch_size, offset=offset)
            if not episodes:
                break
            matched.extend(
                episode
                for episode in episodes
                if all(
                    self.matches_filter(episode, field, operator, expected)
                    for field, operator, expected in filters
                )
            )
            if len(episodes) < batch_size:
                break
            offset += len(episodes)
        return matched if limit is None else matched[:limit]

    def filter_lance_episode_items(
        self,
        dataset_id: str,
        bundle: Any,
        filters: list[tuple[str, str, Any]],
        *,
        limit: int | None,
    ) -> list[EpisodeListItem] | None:
        expression = self.lance_filter_expression(filters, bundle.schemas["episodes"])
        if expression is None:
            return None
        dataset = bundle.tables["episodes"]
        if not hasattr(dataset, "scanner"):
            return None
        columns = self.metadata_columns(bundle.schemas["episodes"])
        row_count = self.count_rows(dataset)
        scan_limit = row_count if limit is None else min(row_count, limit)
        try:
            scanner = dataset.scanner(
                columns=columns,
                filter=expression,
                limit=scan_limit,
            )
            rows = self.rows_from_table(scanner.to_table())
        except Exception:
            return None
        camera_names = self.owner._camera_names_for_bundle(bundle)
        items: list[EpisodeListItem] = []
        for row in rows:
            payload = self.owner._apply_episode_overrides(
                dataset_id,
                self.owner._episode_payload(dataset_id, row, bundle.schemas["episodes"]),
            )
            payload["camera_names"] = camera_names
            item = EpisodeListItem(**payload)
            if all(
                self.matches_filter(item, field, operator, expected)
                for field, operator, expected in filters
            ):
                items.append(item)
        return items if limit is None else items[:limit]
