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
  In-memory service registries for datasets and exports; persisted job and
  Rerun session records under `data/app`
  SQLite-backed job metadata registry for restart-safe job lookups
  JSONL-backed annotation, embedding, version, and VLM response stores
  Optional Lance mirroring when pyarrow/lance are installed

packages/robot_schema
  Lance table column definitions for annotations, embeddings, versions
  PyArrow schema builders for those local curation tables

workers
  Heuristic VLM proposal generator, optional OpenAI-compatible provider, and
  provider interface
  Optional RQ entry point for queued VLM, visual embedding, export, and Rerun
  session jobs

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
- Selected-frame web metadata panel backed by the frame API.
- Annotation-backed selected-frame exact-label mutation.
- Annotation CRUD with range validation, persisted JSONL, web edit actions, and
  midpoint split scaffolding.
- Episode-level label overlay updates for caption, success/failure, failure
  reason, quality, split, and review status, with optional
  `episode_labels.lance` mirroring.
- Optional `annotations.lance`, `episode_labels.lance`, `embeddings.lance`, and
  `versions.lance` mirroring.
- Text-embedding semantic search with deterministic fallback, optional
  OpenAI-compatible text inference, and optional LanceDB table mirror/query when
  `lancedb` is installed.
- Visual keyframe embedding generation with deterministic fallback, optional
  Transformers CLIP/SigLIP/DINO-style provider, and camera/source/hash metadata
  in the shared embedding table.
- Semantic search modality/source-model filters for stored visual rows.
- Optional CLIP/SigLIP text embedding provider for compatible text-to-image
  vector search against stored visual rows.
- Full-text search over episode metadata and annotation text.
- VLM provider routing with heuristic fallback and optional OpenAI-compatible
  HTTP inference.
- Generated-label review queue for pending VLM/heuristic proposals.
- SQLite job metadata store under `data/app/metadata.sqlite3`.
- Optional API-key auth and request-header user identities for review audit
  trails.
- Annotation assignment through `assigned_to` and history actors for multi-user
  review coordination.
- Optional Redis/RQ queue backend for VLM labeling, visual embedding, export,
  and Rerun session jobs.
- Server-sent job progress events at `/api/jobs/{job_id}/events`.
- Web-side streaming of VLM, export, and Rerun job progress with
  API-key-compatible `fetch` event parsing.
- Rerun `.rrd` cache generation for state/action scalar timelines, optional
  camera video assets, deterministic cache keys, and web viewer embedding
  through `@rerun-io/web-viewer-react`.
- LeRobot v3 export manifest, validation report, frame JSONL, available MP4
  artifacts, JSONL-only per-frame video references, official-style tabular
  Parquet rows, and version lineage, including optional official
  LeRobotDataset loader validation.
- Lance subset export for selected episodes when optional `pyarrow` and `lance`
  dependencies are installed.
- JSONL caption export and VLA-style JSONL trajectory export.
- Optional export artifact publishing to local or `fsspec` destinations.
- Optional Rerun cache artifact publishing to local or `fsspec`
  destinations.
- Export scope controls for selected episode or current train/val/test split.
- Queue-backed export and Rerun session jobs using the shared job progress
  event stream.
- Deployment notes for split web/API/Redis/RQ services and shared storage.
- Web UI orchestration via `useStudioData`.

Not implemented yet:

- Durable external database for app settings.
- Local VLM/video-model inference.
- Larger strict real-dataset LeRobot Parquet/MP4 smoke runs with video
  materialization.
- Keyframe and preview cache artifact publishing beyond Rerun `.rrd`
  recordings.

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
