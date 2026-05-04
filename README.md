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
workers/      Python worker helpers
packages/     Shared schema and prompts
data/         Local Lance data, cache, and exports
```

## Current Implementation State

The repository has moved past a pure skeleton. The current MVP path can:

1. Open and index the `lance-format/lerobot-xvla-soft-fold` Lance dataset.
2. Serve dataset summaries, episode lists, episode details, state/action
   summaries, and MP4 blobs with HTTP Range support when available.
3. Serve frame-level samples through `GET /frames`, preferring `frames.lance`
   and falling back to episode time-series arrays with annotation labels and
   bad-frame flags.
4. Store human and generated annotations as JSONL and mirror them to Lance when
   optional Lance dependencies are installed.
5. Generate Rerun `.rrd` cache files for state/action timeline inspection and
   load them through the Rerun React web viewer.
6. Run basic filter search through a typed builder with saved presets, plus
   deterministic text-embedding semantic search.
7. Create heuristic VLM-style annotation proposals for review, including
   deterministic keyframe index sampling, versioned prompt tracking, and a
   provider interface plus raw-response/keyframe artifact persistence for
   future model integrations.
8. Export selected episodes as a metadata-oriented LeRobot v3 snapshot with
   validation and version lineage.
9. Render the main web operations UI with dataset, episode, video viewer,
   annotation editing, search, Rerun, and export panels.

Known MVP gaps:

- Frame mutation and the selected-frame metadata panel are not implemented yet.
- Rerun is embedded and records scalar timelines plus camera video assets when
  MP4 blobs are available; generation is still synchronous and workerless.
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
