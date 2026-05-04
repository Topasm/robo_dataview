from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.api.routers import annotations as annotations_router
from apps.api.routers import users as users_router
from apps.api.schemas.annotations import AnnotationAssignmentUpdate, AnnotationCreate
from apps.api.services.annotation_service import AnnotationStore
from apps.api.services.auth import enforce_api_key
from apps.api.services.user_context import normalize_user_id


class UsersAndAuthTest(unittest.TestCase):
    def test_normalize_user_id_returns_safe_identity(self) -> None:
        self.assertEqual(normalize_user_id(" Alice Smith "), "Alice_Smith")
        self.assertEqual(normalize_user_id(""), "local")
        self.assertEqual(normalize_user_id("reviewer@example.com"), "reviewer@example.com")

    def test_users_me_uses_identity_header(self) -> None:
        response = users_router.get_current_user(user_id="alice")

        self.assertEqual(response.user_id, "alice")

    def test_api_key_middleware_allows_local_mode_without_key(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_API_KEY": ""}, clear=False):
            response = _run_middleware(headers={})

        self.assertEqual(response.status_code, 204)

    def test_api_key_middleware_rejects_missing_key_when_configured(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_API_KEY": "secret"}, clear=False):
            response = _run_middleware(headers={})

        self.assertEqual(response.status_code, 401)

    def test_api_key_middleware_accepts_configured_key_and_user_header(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_API_KEY": "secret"}, clear=False):
            response = _run_middleware(
                headers={
                    "X-Robot-Data-Studio-API-Key": "secret",
                },
            )

        self.assertEqual(response.status_code, 204)

    def test_api_key_middleware_allows_cors_preflight(self) -> None:
        with patch.dict(os.environ, {"ROBOT_DATA_STUDIO_API_KEY": "secret"}, clear=False):
            response = _run_middleware(headers={}, method="OPTIONS")

        self.assertEqual(response.status_code, 204)

    def test_annotation_router_applies_current_user_and_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AnnotationStore(storage_root=Path(tmpdir), mirror_lance=False)
            payload = AnnotationCreate(
                dataset_id="dataset-a",
                episode_index=1,
                start_frame=0,
                end_frame=5,
                label_type="phase",
                label_value="approach",
            )

            with patch.object(annotations_router, "annotation_store", store):
                created = annotations_router.create_annotation(payload, user_id="alice")
                assigned = annotations_router.assign_annotation(
                    created.annotation_id,
                    AnnotationAssignmentUpdate(assigned_to="bob"),
                    user_id="lead",
                )
                annotations_router.delete_annotation(created.annotation_id, user_id="alice")

            history = store.list_history("dataset-a", annotation_id=created.annotation_id)

        self.assertEqual(created.created_by, "alice")
        self.assertEqual(assigned.assigned_to, "bob")
        self.assertEqual([event.action for event in history], ["create", "update", "delete"])
        self.assertEqual([event.actor for event in history], ["alice", "lead", "alice"])
        self.assertEqual(history[1].after["assigned_to"], "bob")

def _run_middleware(headers: dict[str, str], method: str = "GET"):
    import asyncio

    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/users/me"),
        headers=headers,
        method=method,
    )

    async def call_next(_request):
        return SimpleNamespace(status_code=204)

    return asyncio.run(enforce_api_key(request, call_next))


if __name__ == "__main__":
    unittest.main()
