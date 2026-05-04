# Architecture

Robot Data Studio is structured as a web app plus a Python backend and worker
pool. Lance is the source of truth. Rerun is treated as a viewer, not as the
durable annotation store.

```text
Web Frontend
  Dataset browser
  Episode viewer
  Rerun panel
  Annotation editor
  Filter builder
  Job dashboard
  Export manager

FastAPI Backend
  Dataset API
  Episode/frame API
  Annotation API
  Search API
  Rerun session API
  Job API
  Export API

Lance / LanceDB
  frames.lance
  episodes.lance
  videos.lance
  annotations.lance
  embeddings.lance
  versions.lance

Python Workers
  VLM auto-labeling
  Embedding generation
  Phase segmentation
  Thumbnail generation
  Validation
  LeRobot/HF export
```

## Current Implementation Snapshot

The current codebase implements the MVP as a local-first monorepo:

```text
apps/web
  Next.js app router UI
  Dataset browser
  Episode list
  Episode viewer shell
  Timeline panel
  Annotation editor
  Search/filter bar
  Rerun panel
  Export strip

apps/api
  FastAPI app
  In-memory service registries for datasets, jobs, exports, Rerun sessions
  JSONL-backed annotation, embedding, version, and VLM response stores
  Optional Lance mirroring when pyarrow/lance are installed

packages/robot_schema
  Lance table column definitions for annotations, embeddings, versions
  PyArrow schema builders for those local curation tables

workers
  Heuristic VLM proposal generator and provider interface
  Future async worker entry points are added when queue-backed jobs are real

data
  Local annotations, embeddings, versions, keyframe cache, Rerun cache, and
  export artifacts
```

Implemented now:

- Lance dataset open/index for `frames.lance`, `episodes.lance`, and
  `videos.lance` style roots.
- LeRobot v3 metadata snapshot import/export helpers, including optional
  metadata parquet writes when `pyarrow` is installed.
- Dataset summary, schema, episode list/detail, state/action summary, and video
  blob endpoints, including HTTP Range support for browser video playback.
- Frame listing API backed by `frames.lance` when present, with episode
  time-series fallback, annotation overlays, and bad-frame flags.
- Annotation CRUD with range validation, persisted JSONL, web edit actions, and
  midpoint split scaffolding.
- Episode-level label overlay updates for caption, success/failure, failure
  reason, quality, split, and review status.
- Optional `annotations.lance`, `embeddings.lance`, and `versions.lance`
  mirroring.
- Deterministic text-embedding semantic search for local development.
- Rerun `.rrd` cache generation for state/action scalar timelines, optional
  camera video assets, deterministic cache keys, and web viewer embedding
  through `@rerun-io/web-viewer-react`.
- Metadata-oriented LeRobot v3 export manifest, validation report, and version
  lineage.
- Web UI orchestration via `useStudioData`.

Not implemented yet:

- Durable external database for jobs, sessions, users, and app settings.
- Real worker queue such as RQ/Celery plus Redis.
- Real VLM/video-model inference.
- LanceDB vector index search.
- Full frame table browser UI and frame-level mutation workflow.
- Full LeRobot Parquet/MP4 materialization.
- Direct byte-range reads from Lance blobs. The API currently loads the full
  episode-table video blob and slices HTTP ranges in process.
- `videos.lance` provenance lookup in the video endpoint. Video playback reads
  episode video blob columns today.
- Production auth, multi-user review assignment, and audit history.

## Design Principles

1. Lance owns durable data: raw episodes, annotations, embeddings, versions, and
   export records.
2. Rerun is a visualization engine. It should be regenerated or streamed from
   Lance-backed state.
3. VLM outputs are proposals. They should be stored with `source = "vlm"` and
   `review_status = "pending"` until reviewed by a human.
4. LeRobot compatibility is a first-class constraint, so curated subsets must
   be exportable for training pipelines.

## Service Boundaries

```text
Frontend state
  Owns transient UI state, selection, open panels, optimistic interactions.

FastAPI services
  Own dataset indexing, validation, API contracts, local persistence, and
  synchronous MVP job execution.

Lance-compatible stores
  Own annotation, embedding, and version records. JSONL is the mandatory local
  fallback; Lance mirroring is optional.

Workers
  Will own expensive or asynchronous compute. The current VLM path is executed
  synchronously through `JobStore` as a development scaffold.

Rerun
  Owns replay visualization artifacts only. Annotation source of truth stays in
  the annotation store. Current recordings are regenerated per session and log
  timestamp, state norm, and action norm scalars only.
```

## Runtime Flow

```text
Open dataset
  -> backend scans Lance metadata
  -> web shows summary and episode list

Open episode
  -> backend loads episode row and annotations
  -> web renders previews and metadata
  -> optional Rerun session is generated or loaded from cache

Edit annotation
  -> web sends annotation mutation
  -> backend validates frame ranges and label payload
  -> annotation is stored in annotations.lance

Export subset
  -> filter query resolves selected episodes
  -> accepted annotations are applied
  -> worker creates LeRobot/Lance/HF-compatible output
  -> versions.lance records lineage
```

## Deployment Direction

Local MVP:

```text
Next.js dev server
FastAPI + Uvicorn
Local filesystem data/
Optional local Lance dependencies
```

Team/server mode:

```text
Next.js frontend
FastAPI API service
Redis + RQ or Celery workers
Lance/LanceDB on local NVMe, S3, MinIO, or HF Hub cache
SQLite/Postgres for app metadata
Rerun recording cache on shared object storage
```
