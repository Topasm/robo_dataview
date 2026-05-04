# Robot Data Studio

Robot Data Studio is a web-based operating tool for Lance-native LeRobot
datasets. Its goal is not only to preview robot data, but to help curate
high-quality datasets for VLA and robot policy training.

## Product Direction

- **Web GUI**: dataset browsing, annotation editing, filtering, review queues,
  export management.
- **Rerun Web Viewer**: episode replay, multi-camera inspection, timelines, 3D
  visualization.
- **Lance / LanceDB**: source of truth for raw data, annotations, embeddings,
  versions, and searchable subsets.
- **Python Workers**: VLM auto-labeling, embedding generation, thumbnails,
  validation, Rerun cache generation, export jobs.

## Target Stack

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Pydantic
- Data: Lance and LanceDB
- Viewer: Rerun Web Viewer
- Workers: Python with RQ or Celery
- Interop: LeRobotDataset and Hugging Face datasets

## Repository Layout

```text
apps/
  api/        FastAPI backend
  web/        Next.js frontend
docs/         Architecture, schema, API, UI, roadmap, and execution plan
workers/      Python worker entry points
packages/     Shared schema and prompts
data/         Local Lance data, cache, and exports
```

## Current Implementation State

The repository has moved past a pure skeleton. The current MVP path can:

1. Open and index the `lance-format/lerobot-xvla-soft-fold` Lance dataset.
2. Serve dataset summaries, episode lists, episode details, state/action
   summaries, and MP4 blobs when available.
3. Store human and generated annotations as JSONL and mirror them to Lance when
   optional Lance dependencies are installed.
4. Generate Rerun `.rrd` cache files for state/action timeline inspection.
5. Run basic filter search and deterministic text-embedding semantic search.
6. Create heuristic VLM-style annotation proposals for review.
7. Export selected episodes as a metadata-oriented LeRobot v3 snapshot and
   record version lineage.
8. Render the main web operations UI with dataset, episode, viewer, annotation,
   search, Rerun, and export panels.

Known MVP gaps:

- The frame API is still a placeholder.
- Multi-camera video playback needs stronger browser UX and seek behavior.
- Rerun is generated as `.rrd` cache, but the embedded viewer integration is
  still early.
- VLM labeling is heuristic/local scaffolding, not real model inference.
- Semantic search uses deterministic text hashing, not LanceDB vector indexes.
- LeRobot export is metadata-oriented and does not yet materialize full
  Parquet/MP4 training artifacts.

## MVP Scope

1. Open Lance LeRobot datasets.
2. List episodes and dataset summary.
3. Preview multi-camera video and state/action metadata.
4. Edit episode-level and segment-level annotations.
5. Store annotations in Lance-compatible tables.
6. Embed Rerun Web Viewer for deeper replay.
7. Run basic filters.
8. Export selected episodes.

See `docs/plan.md` for the current implementation plan and todo list.
