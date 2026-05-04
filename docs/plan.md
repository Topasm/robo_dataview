# Plan

This document is the working plan for moving Robot Data Studio from the current
local MVP scaffold to a useful robot dataset operations tool.

## Product Target

Robot Data Studio should be a Lance-native web platform for exploring,
auto-labeling, reviewing, filtering, editing, and exporting LeRobot datasets for
VLA and robot policy training.

Architecture target:

```text
React / Next.js web app
  -> FastAPI backend
  -> Lance / LanceDB source of truth
  -> Python worker queue for expensive jobs
  -> Rerun Web Viewer for replay/debug visualization
```

Core principle:

```text
Lance = durable data
Web = operations UI
Rerun = visualization
VLM = proposal generator
Human = final reviewer
```

## Current Baseline

Working:

- Lance dataset open/index path.
- `xvla-soft-fold` summary and episode list through API.
- Dataset schema endpoint.
- Episode detail, video blob, and state/action summary endpoints.
- MP4 video blob serving with `HEAD` and byte-range support.
- `videos.lance` fallback for episode-indexed video blobs, LeRobot-style video
  shard references, local files, HTTP(S), `hf://`, and optional `fsspec`
  object-store paths.
- Annotation CRUD with JSONL persistence and optional Lance mirroring.
- Segment edit and midpoint split actions in the web UI.
- Search filter endpoint.
- Full-text search endpoint and web action.
- Typed filter builder UI for common episode fields.
- Text-embedding semantic search endpoint with deterministic fallback, optional
  OpenAI-compatible embedding provider, and optional LanceDB vector table
  persistence/query.
- Visual embedding job endpoint with deterministic local fallback,
  optional Transformers CLIP/SigLIP/DINO-style provider, keyframe JPEG
  extraction, and image embedding persistence.
- VLM-label job endpoint with heuristic pending annotation proposals and
  optional OpenAI-compatible provider routing.
- Generated-label review queue in the annotation panel.
- Deterministic keyframe index sampling for VLM prompt inputs.
- Rerun session endpoint that generates `.rrd` cache files.
- Rerun React viewer embed for ready `.rrd` sessions.
- Frame listing endpoint with `frames.lance` preference, episode time-series
  fallback, state/action samples, annotation labels, and bad-frame flags.
- Selected-frame metadata panel backed by `GET /frames`.
- Frame browser panel backed by `GET /frames` for the selected episode window.
- Annotation-backed selected-frame exact-label mutation.
- Export endpoint that writes a manifest and LeRobot v3-oriented snapshot with
  metadata, frame JSONL, optional Parquet, available MP4 artifacts, and
  JSONL-only per-frame video references.
- LeRobot v3 export metadata includes official-style compact episode/task
  indices, global frame `index`, episode `dataset_from_index` /
  `dataset_to_index`, `tasks`, source-index provenance, and per-camera video
  timestamp fields for loader compatibility.
- Version lineage JSONL and optional Lance mirror.
- Main Next.js UI with dataset, episode, viewer, timeline, annotation, search,
  Rerun, and export areas.

Verified recently:

```text
python3 -m pytest -q
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run build
```

Known limits:

- VLM, visual embedding, export, and Rerun session jobs can run through the
  optional RQ backend.
- Some app settings are still in-memory.
- VLM labeling defaults to heuristic scaffolding unless an OpenAI-compatible
  provider is configured.
- Semantic search can target stored visual embedding rows by modality and source
  model. Meaningful cross-modal text-to-image ranking requires configuring the
  text embedding provider and visual embedding worker with the same compatible
  CLIP/SigLIP model.
- Export writes frame JSONL, available MP4 artifacts, and optional Parquet
  shards. JSONL keeps internal per-frame video references; Parquet omits video
  feature columns and relies on LeRobot episode video metadata.
- The manual official-dependency workflow has verified native Hugging Face
  Dataset export and tiny no-video/video-backed LeRobot snapshots against the
  real `datasets` and `lerobot` loaders.
- A separate opt-in real-dataset export smoke workflow has opened the default
  `xvla-soft-fold` `hf://` Lance URI, exported one episode, and verified the
  result with the official LeRobot loader.
- File-backed video ranges stream directly from disk. Embedded Lance video blobs
  stream byte ranges directly when Lance exposes a seekable `take_blobs` reader;
  non-seekable blob fallbacks still materialize the MP4 before serving it.
- Exported LeRobot video indexes include SHA256 digests, and validation rejects
  materialized MP4 artifacts whose digest does not match the index.
- Remote path-backed video rows stream byte ranges for HTTP(S), `hf://` through
  `huggingface_hub`, and object stores through optional `fsspec`.
- Full frame-table browser UX exists for local frame review, but raw
  `frames.lance` table mutation remains annotation-backed rather than rewriting
  source rows.

## Next Milestone

Milestone name:

```text
M1: Reviewable Episode Viewer
```

Goal:

```text
A user can open xvla-soft-fold, select an episode, play or inspect camera video,
scrub the timeline, add/edit phase annotations, generate a Rerun replay, and
export the selected reviewed episode.
```

Definition of done:

- A selectable active camera video pane renders for available episode videos.
- Synchronized multi-camera playback can be inspected or is clearly planned.
- Episode selection loads metadata, annotations, and state/action summary.
- Timeline can create and update phase segments.
- Rerun panel opens the generated `.rrd` in an embedded viewer path.
- Export includes accepted annotations and produces a validation summary.
- The full path is covered by API tests plus web typecheck/build.

## Todo List

### P0: Stabilize Local Development

- [x] Ignore local virtualenv and Python packaging artifacts.
- [x] Replace deprecated `next lint` script with ESLint CLI.
- [x] Split web data orchestration from `page.tsx` into `useStudioData`.
- [x] Add a one-command local dev script for API + web.
- [x] Add `.env.example` with `NEXT_PUBLIC_API_BASE_URL` and Rerun settings.
- [x] Document dependency installation for base, Lance, Rerun, and dev extras.
- [x] Decide whether `.venv` should be recreated by script or left manual.

### P1: Dataset and Episode Explorer

- [x] Open Lance dataset roots.
- [x] Open LeRobot v3 metadata snapshots.
- [x] Show dataset summary.
- [x] List episodes.
- [x] Load state/action summary.
- [x] Add server-side pagination metadata.
- [x] Add sort/filter query params for episode list.
- [x] Add dataset reload/close endpoint.
- [x] Persist opened dataset registry across API restarts.

### P2: Basic Viewer

- [x] Render selectable active camera video pane from API video blob URLs.
- [x] Add loading/error state per camera.
- [x] Add backend `HEAD`/Range support for browser video playback.
- [x] Add range-aware streaming for file-backed videos and seekable Lance blob
  readers.
- [x] Add true remote object-store/HF path byte-range reads.
- [x] Add synchronized N-camera playback layout.
- [x] Wire playback controls: play, pause, seek, and frame jumps.
- [x] Add frame/time scrubber.
- [x] Add state/action summary cards.
- [x] Add state/action time-series chart.
- [x] Add selected-frame metadata panel.
- [x] Add thumbnail or keyframe preview cache.

### P3: Annotation Workflow

- [x] Segment annotation create/update/delete.
- [x] Review status updates.
- [x] JSONL persistence.
- [x] Optional Lance mirroring.
- [x] Segment edit form.
- [x] Midpoint split action.
- [x] Add episode-level label update endpoint.
- [x] Add quality score, success/failure, failure reason editing.
- [x] Add label type choices for bad range, important frame, and failure event.
- [x] Add frame-aware bad range authoring from the timeline.
- [x] Add timeline drag/split/merge controls.
- [x] Add annotation history.
- [x] Add optimistic UI rollback on mutation failure.

### P4: Rerun Integration

- [x] Generate `.rrd` cache files from episode time series.
- [x] Serve `.rrd` files through API.
- [x] Embed Rerun Web Viewer in the web panel.
- [x] Add external-open fallback link for generated recordings.
- [x] Log camera video or synchronized image frames to Rerun.
- [x] Add cache key by dataset version, episode index, and visualization config.
- [x] Move `.rrd` generation into a worker.

### P4.5: Frame API

- [x] Add `GET /frames` with episode/range/limit query params.
- [x] Prefer `frames.lance` rows when present.
- [x] Fall back to episode time-series arrays for Lance datasets without frame
  rows.
- [x] Return state/action vectors and norms.
- [x] Overlay annotation labels and derive bad-frame flags.
- [x] Add frame metadata panel in the web UI.
- [x] Add selected-episode frame browser panel.
- [x] Add selected-frame bad-frame mutation endpoint.
- [x] Add selected-frame exact-label mutation endpoint.
- [x] Add full frame-table browser and raw frame mutation workflow.

### P5: Search and Filtering

- [x] Basic `AND` filter parser.
- [x] Text-hash semantic search scaffold.
- [x] Add filter builder UI with typed fields.
- [x] Add saved filter presets.
- [x] Add optional LanceDB vector table mirror/query path.
- [x] Add optional OpenAI-compatible text embedding provider.
- [x] Add full-text search.
- [x] Combine structured filters with semantic ranking.
- [x] Add CLIP, SigLIP, DINOv2, or video-VLM embeddings.

### P6: VLM Auto-Labeling

- [x] Job endpoint.
- [x] Heuristic annotation proposal generator.
- [x] Pending review annotations.
- [x] Add deterministic keyframe index sampling.
- [x] Add prompt registry/versioning.
- [x] Add VLM provider abstraction with heuristic fallback provider.
- [x] Store raw VLM provider responses as JSONL.
- [x] Add decoded keyframe image extraction from video blobs.
- [x] Add optional OpenAI-compatible model/API integration.
- [x] Store raw response and model metadata.
- [x] Add review queue for generated labels.

### P7: Export and Versioning

- [x] Export selected episodes.
- [x] Include accepted annotations only.
- [x] Write export manifest.
- [x] Write LeRobot v3-oriented snapshot.
- [x] Materialize frame JSONL and available camera MP4 artifacts.
- [x] Add export validation report.
- [x] Add optional official LeRobotDataset loader validation.
- [x] Append version lineage.
- [x] Add Lance subset export.
- [x] Add JSONL captions and VLA training format export.
- [x] Add train/val/test split controls.
- [x] Materialize official-loader-validated LeRobot Parquet/MP4 export path.

### P8: Production Shape

- [x] Add SQLite/Postgres app metadata store.
- [x] Add Redis + RQ/Celery worker queue.
- [x] Add background job progress events.
- [x] Wire web VLM, export, and Rerun job progress streaming.
- [x] Add queue-backed export job endpoint.
- [x] Add queue-backed Rerun session job endpoint.
- [x] Add auth and user identities.
- [x] Add multi-user review assignment.
- [x] Add object storage publishing for export artifacts.
- [ ] Add object storage publishing for cache artifacts.
- [x] Add deployment docs.

## Recommended Immediate Order

1. Run the opt-in real-dataset export smoke workflow with video materialization
   and larger representative downloaded or `hf://` Lance subsets.
2. Run a real CLIP/SigLIP text-to-image search smoke with generated visual
   embeddings.
3. Add object storage publishing for cache artifacts.

## Validation Checklist

Run before considering a milestone complete:

```text
python3 -m pytest -q
python3 -m compileall -q apps packages workers
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run build
curl -sS http://127.0.0.1:8000/health
```

Manual checks:

- Open web UI.
- Confirm dataset summary loads from API.
- Select first real episode.
- Confirm annotations load and can be edited.
- Generate Rerun session.
- Export selected episode.
- Confirm output manifest and version record exist.
