# Deployment

Robot Data Studio can run as a single local workstation app or as separate web,
API, Redis, and worker services. The default local mode keeps jobs inline in the
API process. Production-style mode should enable Redis/RQ for expensive VLM,
visual embedding, export, and Rerun session jobs.

## Services

```text
Next.js web
  serves the React UI

FastAPI API
  serves dataset, annotation, search, Rerun, job, and export endpoints

Redis
  brokers queued jobs when ROBOT_DATA_STUDIO_JOB_QUEUE=rq

RQ worker
  imports workers.job_runner.run_queued_job and executes queued jobs

Shared storage
  data/lance, data/cache, data/exports, and data/app
  must be visible to both API and worker processes for queued Rerun recordings
  and exported artifacts
```

## Python Environments

Base API:

```bash
python3 -m pip install -e ".[dev]"
```

Optional production extras:

```bash
python3 -m pip install -e ".[lance,rerun,video,export,queue]"
```

Use `.[export]` on machines that must write optional LeRobot Parquet/MP4
artifacts and run official loader validation. Use `.[queue]` on API and worker
machines that enqueue or execute Redis/RQ jobs.

The manual GitHub Actions workflow `Official export dependencies` installs
`.[export,video,dev]` and runs opt-in export checks with real optional
dependencies, including native Hugging Face Dataset round-trip plus no-video
and video-backed LeRobotDataset loader validation. The same check can be run
locally with:

```bash
RUN_OFFICIAL_EXPORT_TESTS=1 python3 -m pytest apps/api/tests/test_official_export_dependencies.py -q
```

The manual GitHub Actions workflow `Real dataset export smoke` installs
`.[lance,export,video,dev]`, opens a real Lance dataset URI, exports the first
N episodes to a LeRobot snapshot, and verifies the artifact with the official
loader. It defaults to `hf://datasets/lance-format/lerobot-xvla-soft-fold/data`
with one episode and no video materialization. The same check can be run
locally with:

```bash
RUN_REAL_DATASET_EXPORT_SMOKE=1 \
REAL_DATASET_URI=hf://datasets/lance-format/lerobot-xvla-soft-fold/data \
REAL_DATASET_EPISODE_LIMIT=1 \
REAL_DATASET_EXPORT_VIDEOS=0 \
python3 -m pytest apps/api/tests/test_real_dataset_export_smoke.py -q
```

Set `REAL_DATASET_EXPORT_VIDEOS=1` only when the runner has enough bandwidth,
disk, and time to fetch and validate the selected episodes' MP4 payloads. For
`hf://` datasets, provide an `HF_TOKEN` secret or local environment variable;
unauthenticated video materialization can hit Hugging Face API rate limits and
will be skipped by the smoke test.

## Environment

Minimum web environment:

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.example.com/api
NEXT_PUBLIC_RERUN_IFRAME_URL=
NEXT_PUBLIC_VLM_MODEL=heuristic-vlm-fallback
NEXT_PUBLIC_VLM_PROMPT_TEMPLATE=episode_autolabel_v1
NEXT_PUBLIC_ROBOT_DATA_STUDIO_API_KEY=
NEXT_PUBLIC_ROBOT_DATA_STUDIO_USER=local
```

Minimum API environment:

```bash
ROBOT_DATA_STUDIO_API_KEY=
ROBOT_DATA_STUDIO_JOB_QUEUE=rq
ROBOT_DATA_STUDIO_REDIS_URL=redis://redis:6379/0
ROBOT_DATA_STUDIO_RQ_QUEUE=robot-data-studio
ROBOT_DATA_STUDIO_JOB_TIMEOUT_SECONDS=3600
```

If `ROBOT_DATA_STUDIO_API_KEY` is non-empty, clients must send
`X-Robot-Data-Studio-API-Key`. Review actions may also send
`X-Robot-Data-Studio-User`; otherwise audit history uses `local`.

Optional providers:

```bash
ROBOT_DATA_STUDIO_VLM_PROVIDER=openai-compatible
ROBOT_DATA_STUDIO_VLM_BASE_URL=https://api.openai.com/v1
ROBOT_DATA_STUDIO_VLM_API_KEY=
ROBOT_DATA_STUDIO_EMBEDDING_PROVIDER=openai-compatible
ROBOT_DATA_STUDIO_EMBEDDING_BASE_URL=https://api.openai.com/v1
ROBOT_DATA_STUDIO_EMBEDDING_API_KEY=
ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_PROVIDER=transformers
ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_MODEL=openai/clip-vit-base-patch32
```

## Start Commands

API:

```bash
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

Worker:

```bash
rq worker robot-data-studio --url "$ROBOT_DATA_STUDIO_REDIS_URL"
```

Web:

```bash
npm --workspace apps/web run build
npm --workspace apps/web run start -- --hostname 0.0.0.0 --port 3000
```

## Storage Contract

Mount these paths on persistent shared storage for API and worker services:

```text
data/lance/      annotation, embedding, version, and optional Lance mirror data
data/cache/      Rerun recordings, keyframes, previews
data/exports/    export manifests and materialized artifacts
data/app/        SQLite app metadata, including job records
```

Workers must see the same `data/` tree as the API, because queued jobs load
datasets, write annotations, update embeddings, and save export/cache artifacts
through those paths.

## Health And Operations

- API health: `GET /health`
- Job status: `GET /api/jobs/{job_id}`
- Job events: `GET /api/jobs/{job_id}/events`
- Rerun cache artifacts: `data/cache/rerun/`
- Export artifacts: `data/exports/`

Keep `ROBOT_DATA_STUDIO_JOB_QUEUE` unset for simple single-process local use.
Set it to `rq` only when Redis and at least one worker process are running.
