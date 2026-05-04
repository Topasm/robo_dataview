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

## Design Principles

1. Lance owns durable data: raw episodes, annotations, embeddings, versions, and
   export records.
2. Rerun is a visualization engine. It should be regenerated or streamed from
   Lance-backed state.
3. VLM outputs are proposals. They should be stored with `source = "vlm"` and
   `review_status = "pending"` until reviewed by a human.
4. LeRobot compatibility is a first-class constraint, so curated subsets must
   be exportable for training pipelines.

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
