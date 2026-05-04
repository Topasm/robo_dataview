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
- Annotation CRUD with JSONL persistence and optional Lance mirroring.
- Search filter endpoint.
- Deterministic text-embedding semantic search endpoint.
- VLM-label job endpoint with heuristic pending annotation proposals.
- Rerun session endpoint that generates `.rrd` cache files.
- Export endpoint that writes a manifest and metadata-oriented LeRobot v3
  snapshot.
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

- `GET /frames` is a placeholder.
- Jobs run synchronously in-process.
- Open datasets and sessions are in-memory.
- Rerun cache generation logs state/action scalar timelines, not full
  synchronized camera video.
- VLM labeling is heuristic scaffolding.
- Semantic search is text-hash based, not LanceDB vector search.
- Export does not yet materialize full LeRobot Parquet/MP4 artifacts.

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

- Real camera video panes render for available episode videos.
- Episode selection loads metadata, annotations, and state/action summary.
- Timeline can create and update phase segments.
- Rerun panel opens the generated `.rrd` in an embedded or linked viewer path.
- Export includes accepted annotations and produces a validation summary.
- The full path is covered by API tests plus web typecheck/build.

## Todo List

### P0: Stabilize Local Development

- [x] Ignore local virtualenv and Python packaging artifacts.
- [x] Replace deprecated `next lint` script with ESLint CLI.
- [x] Split web data orchestration from `page.tsx` into `useStudioData`.
- [ ] Add a one-command local dev script for API + web.
- [ ] Add `.env.example` with `NEXT_PUBLIC_API_BASE_URL` and Rerun settings.
- [ ] Document dependency installation for base, Lance, Rerun, and dev extras.
- [ ] Decide whether `.venv` should be recreated by script or left manual.

### P1: Dataset and Episode Explorer

- [x] Open Lance dataset roots.
- [x] Open LeRobot v3 metadata snapshots.
- [x] Show dataset summary.
- [x] List episodes.
- [x] Load state/action summary.
- [ ] Add server-side pagination metadata.
- [ ] Add sort/filter query params for episode list.
- [ ] Add dataset reload/close endpoint.
- [ ] Persist opened dataset registry across API restarts.

### P2: Basic Viewer

- [ ] Render N-camera video panes from API video blob URLs.
- [ ] Add loading/error state per camera.
- [ ] Add playback controls: play, pause, rate, seek.
- [ ] Add frame/time scrubber.
- [ ] Add state/action chart.
- [ ] Add selected-frame metadata panel.
- [ ] Add thumbnail or keyframe preview cache.

### P3: Annotation Workflow

- [x] Segment annotation create/update/delete.
- [x] Review status updates.
- [x] JSONL persistence.
- [x] Optional Lance mirroring.
- [ ] Add episode-level label update endpoint.
- [ ] Add quality score, success/failure, failure reason editing.
- [ ] Add bad frame/range labels.
- [ ] Add timeline drag/split/merge controls.
- [ ] Add annotation history.
- [ ] Add optimistic UI rollback on mutation failure.

### P4: Rerun Integration

- [x] Generate `.rrd` cache files from episode time series.
- [x] Serve `.rrd` files through API.
- [ ] Embed Rerun Web Viewer in the web panel.
- [ ] Add external-open fallback link for generated recordings.
- [ ] Log camera video or synchronized image frames to Rerun.
- [ ] Add cache key by dataset version, episode index, and visualization config.
- [ ] Move `.rrd` generation into a worker.

### P5: Search and Filtering

- [x] Basic `AND` filter parser.
- [x] Text-hash semantic search scaffold.
- [ ] Add filter builder UI with typed fields.
- [ ] Add saved filter presets.
- [ ] Add full-text search.
- [ ] Add LanceDB vector index service.
- [ ] Add visual/video embeddings from CLIP, SigLIP, DINOv2, or video VLMs.
- [ ] Combine structured filters with semantic ranking.

### P6: VLM Auto-Labeling

- [x] Job endpoint.
- [x] Heuristic annotation proposal generator.
- [x] Pending review annotations.
- [ ] Add keyframe extraction.
- [ ] Add prompt registry/versioning.
- [ ] Add VLM provider abstraction.
- [ ] Add real model/API integration.
- [ ] Store raw response and model metadata.
- [ ] Add review queue for generated labels.

### P7: Export and Versioning

- [x] Export selected episodes.
- [x] Include accepted annotations only.
- [x] Write export manifest.
- [x] Write metadata-oriented LeRobot v3 snapshot.
- [x] Append version lineage.
- [ ] Add export validation report.
- [ ] Add train/val/test split controls.
- [ ] Materialize full LeRobot Parquet/MP4 export.
- [ ] Add Lance subset export.
- [ ] Add JSONL captions and VLA training format export.

### P8: Production Shape

- [ ] Add SQLite/Postgres app metadata store.
- [ ] Add Redis + RQ/Celery worker queue.
- [ ] Add background job progress events.
- [ ] Add auth and user identities.
- [ ] Add multi-user review assignment.
- [ ] Add object storage support for cache and exports.
- [ ] Add deployment docs.

## Recommended Immediate Order

1. Make the basic viewer real: camera panes, scrubber, state/action plot.
2. Add episode-level annotation editing.
3. Make Rerun panel open generated recordings.
4. Add export validation report.
5. Add keyframe extraction and replace heuristic VLM with a real provider path.
6. Replace deterministic semantic search with LanceDB vector search.

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
