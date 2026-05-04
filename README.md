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
docs/         Phase 0 architecture, schema, API, and UI docs
workers/      Python worker entry points
packages/     Shared schema and prompts
data/         Local Lance data, cache, and exports
```

## MVP Scope

1. Open Lance LeRobot datasets.
2. List episodes and dataset summary.
3. Preview multi-camera video and state/action metadata.
4. Edit episode-level and segment-level annotations.
5. Store annotations in Lance-compatible tables.
6. Embed Rerun Web Viewer for deeper replay.
7. Run basic filters.
8. Export selected episodes.

The first implementation pass in this repository defines the architecture,
schemas, API contracts, and minimal app skeleton needed to start Phase 1.
