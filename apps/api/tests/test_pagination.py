from __future__ import annotations

import unittest

from apps.api.services.pagination import list_all_episodes


class PaginationTest(unittest.TestCase):
    def test_list_all_episodes_reads_until_empty_page(self) -> None:
        store = _PagedStore(total=2501)

        episodes = list_all_episodes(store, "dataset-a", batch_size=1000)

        self.assertEqual(episodes, list(range(2501)))
        self.assertEqual(store.calls, [(1000, 0), (1000, 1000), (1000, 2000)])


class _PagedStore:
    def __init__(self, total: int) -> None:
        self.total = total
        self.calls: list[tuple[int, int]] = []

    def list_episodes(self, dataset_id: str, limit: int, offset: int) -> list[int]:
        self.assert_dataset(dataset_id)
        self.calls.append((limit, offset))
        return list(range(self.total))[offset : offset + limit]

    @staticmethod
    def assert_dataset(dataset_id: str) -> None:
        if dataset_id != "dataset-a":
            raise AssertionError(f"unexpected dataset_id: {dataset_id}")
