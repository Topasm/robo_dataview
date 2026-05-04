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
   bad-frame flags, and show/edit selected-frame labels in the web metadata
   panel.
4. Store human and generated annotations as JSONL and mirror them to Lance when
   optional Lance dependencies are installed.
5. Generate Rerun `.rrd` cache files for state/action timeline inspection and
   load them through the Rerun React web viewer.
6. Run basic filter search through a typed builder with saved presets, plus
   full-text search and text-embedding semantic search with deterministic
   fallback, optional OpenAI-compatible embedding inference, and optional
   LanceDB vector table persistence/query when `lancedb` is installed.
7. Create VLM-style annotation proposals for review, including
   deterministic keyframe index sampling, versioned prompt tracking, and a
   provider interface with heuristic fallback, optional OpenAI-compatible model
   routing, raw-response/keyframe artifact persistence, and a generated-label
   review queue.
8. Export selected episodes as a LeRobot v3-oriented snapshot with metadata,
   frame JSONL, optional Parquet, available camera MP4 artifacts, validation,
   and version lineage, or as a Lance subset when optional `pyarrow` and
   `lance` dependencies are installed. Lightweight JSONL caption and VLA-style
   trajectory exports are also available, and exports can target the selected
   episode or the current train/val/test split.
9. Render the main web operations UI with dataset, episode, video viewer,
   annotation editing, search, Rerun, and export panels.

Known MVP gaps:

- General frame-table editing is not implemented yet; selected-frame exact
  labels such as bad-frame, important-frame, occlusion, and gripper-contact
  markers are available through annotation-backed frame mutation.
- Rerun is embedded and records scalar timelines plus camera video assets when
  MP4 blobs are available; generation is still synchronous and workerless.
- VLM labeling defaults to heuristic/local scaffolding; OpenAI-compatible model
  inference is available only when configured with environment variables.
- Semantic search is still text-only. OpenAI-compatible text embeddings and
  LanceDB persistence/query are optional; real visual/video model embeddings are
  not implemented yet.
- LeRobot export writes frame JSONL and available MP4 artifacts; training-ready
  Parquet shards still require optional `pyarrow`/LeRobot dependencies. When
  `lerobot` is installed, validation records the official loader result.
- Lance subset export requires optional `pyarrow` and `lance` dependencies and
  fails clearly when they are missing.

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
