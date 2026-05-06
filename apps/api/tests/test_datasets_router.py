from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from apps.api.routers import datasets
from apps.api.schemas.datasets import DatasetHealth, DatasetOpenRequest, DatasetRecord


class FakeDatasetStore:
    def __init__(self) -> None:
        self.open_payload: DatasetOpenRequest | None = None

    def list_datasets(self) -> list[DatasetRecord]:
        return [
            DatasetRecord(
                dataset_id="dataset-a",
                name="Dataset A",
                uri="/datasets/a",
                status="indexed",
            )
        ]

    def open_dataset(self, payload: DatasetOpenRequest) -> DatasetRecord:
        self.open_payload = payload
        return DatasetRecord(
            dataset_id="dataset-b",
            name=payload.name or "dataset-b",
            uri=payload.uri,
            status="indexed",
        )

    def reload_dataset(self, dataset_id: str) -> DatasetRecord | None:
        if dataset_id != "dataset-a":
            return None
        return DatasetRecord(
            dataset_id="dataset-a",
            name="Dataset A",
            uri="/datasets/a",
            status="indexed",
        )

    def close_dataset(self, dataset_id: str) -> DatasetRecord | None:
        if dataset_id != "dataset-a":
            return None
        return DatasetRecord(
            dataset_id="dataset-a",
            name="Dataset A",
            uri="/datasets/a",
            status="indexed",
        )

    def get_health(self, dataset_id: str, *, level: str = "shallow") -> DatasetHealth | None:
        if dataset_id != "dataset-a":
            return None
        return DatasetHealth(
            dataset_id="dataset-a",
            ok=True,
            status="indexed",
            storage_model="lance",
            level=level,
        )


class DatasetRouterTest(unittest.TestCase):
    def test_open_reload_and_close_routes_delegate_to_store(self) -> None:
        fake_store = FakeDatasetStore()

        with patch.object(datasets, "store", fake_store):
            opened = datasets.open_dataset(DatasetOpenRequest(uri="/datasets/b", name="Dataset B"))
            reloaded = datasets.reload_dataset("dataset-a")
            closed = datasets.close_dataset("dataset-a")

        self.assertEqual(opened.dataset_id, "dataset-b")
        self.assertEqual(fake_store.open_payload.name, "Dataset B")
        self.assertEqual(reloaded.dataset_id, "dataset-a")
        self.assertEqual(closed.dataset_id, "dataset-a")

    def test_reload_and_close_routes_return_404_for_missing_dataset(self) -> None:
        with patch.object(datasets, "store", FakeDatasetStore()):
            with self.assertRaises(HTTPException) as reload_context:
                datasets.reload_dataset("missing")
            with self.assertRaises(HTTPException) as close_context:
                datasets.close_dataset("missing")

        self.assertEqual(reload_context.exception.status_code, 404)
        self.assertEqual(close_context.exception.status_code, 404)

    def test_health_route_delegates_to_store(self) -> None:
        with patch.object(datasets, "store", FakeDatasetStore()):
            health = datasets.dataset_health("dataset-a")

        self.assertTrue(health.ok)
        self.assertEqual(health.storage_model, "lance")
        self.assertEqual(health.level, "shallow")

    def test_health_route_returns_404_for_missing_dataset(self) -> None:
        with patch.object(datasets, "store", FakeDatasetStore()):
            with self.assertRaises(HTTPException) as context:
                datasets.dataset_health("missing")

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
