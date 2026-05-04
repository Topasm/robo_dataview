from __future__ import annotations

import os
from typing import Any, Protocol


class JobQueueUnavailableError(RuntimeError):
    pass


class JobQueueBackend(Protocol):
    def enqueue(self, job_id: str, kind: str, payload: dict[str, Any]) -> str | None:
        pass


class RQJobQueueBackend:
    def __init__(
        self,
        *,
        redis_url: str,
        queue_name: str = "robot-data-studio",
        job_timeout_seconds: int = 3600,
    ) -> None:
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.job_timeout_seconds = job_timeout_seconds

    def enqueue(self, job_id: str, kind: str, payload: dict[str, Any]) -> str | None:
        try:
            import redis
            from rq import Queue
            from workers.job_runner import run_queued_job
        except ImportError as exc:
            raise JobQueueUnavailableError(
                "RQ queue backend requires optional dependencies: pip install -e '.[queue]'"
            ) from exc

        connection = redis.Redis.from_url(self.redis_url)
        queue = Queue(self.queue_name, connection=connection)
        try:
            queued_job = queue.enqueue(
                run_queued_job,
                job_id,
                kind,
                payload,
                job_timeout=self.job_timeout_seconds,
            )
        except Exception as exc:
            raise JobQueueUnavailableError(f"Failed to enqueue RQ job: {exc}") from exc
        return str(queued_job.id)


def build_job_queue_from_env() -> JobQueueBackend | None:
    backend = os.getenv("ROBOT_DATA_STUDIO_JOB_QUEUE", "sync").strip().lower()
    if backend in {"", "sync", "inline", "none"}:
        return None
    if backend not in {"rq", "redis", "rq-redis"}:
        raise JobQueueUnavailableError(f"Unsupported job queue backend: {backend}")

    redis_url = os.getenv("ROBOT_DATA_STUDIO_REDIS_URL", "redis://127.0.0.1:6379/0")
    queue_name = os.getenv("ROBOT_DATA_STUDIO_RQ_QUEUE", "robot-data-studio")
    try:
        timeout = int(os.getenv("ROBOT_DATA_STUDIO_JOB_TIMEOUT_SECONDS", "3600"))
    except ValueError as exc:
        raise JobQueueUnavailableError(
            "ROBOT_DATA_STUDIO_JOB_TIMEOUT_SECONDS must be an integer"
        ) from exc
    return RQJobQueueBackend(
        redis_url=redis_url,
        queue_name=queue_name,
        job_timeout_seconds=timeout,
    )
