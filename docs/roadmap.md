# Roadmap

Status legend:

```text
done       implemented and verified in the local MVP path
partial    usable scaffold exists, but important behavior is missing
planned    not implemented yet
```

## Current Phase Status

```text
Phase 0  Specification               done
Phase 1  Lance Dataset Explorer       done
Phase 2  Basic Web Viewer             done
Phase 3  Rerun Web Viewer             partial
Phase 4  Annotation System            done
Phase 5  VLM Auto-Labeling            partial
Phase 6  Search and Filtering         partial
Phase 7  Export and Versioning        partial
```

Current verified baseline:

- Python tests pass.
- Web lint, typecheck, and production build pass.
- `xvla-soft-fold` is indexed through the API.
- Dataset summary reports 1,542 episodes, 2,852,512 frames, 20 FPS, and three
  camera streams.
- Browser video endpoint supports MP4 byte ranges by slicing loaded episode
  blobs.
- Basic viewer playback includes multi-camera sync, frame scrubber, and
  state/action norm plots.
- Rerun `.rrd` generation and React web viewer embedding work for scalar
  timelines and available camera MP4 references.

## Phase 0: Specification

Deliverables:

- `docs/architecture.md`
- `docs/schema.md`
- `docs/api_spec.md`
- `docs/ui_wireframe.md`

## Phase 1: Lance Dataset Explorer

Goal:

- Open a Lance-native LeRobot dataset.
- Show dataset summary and episode list.
- Load one episode's metadata, state/action arrays, and video preview handles.

Completion criteria:

- The web UI displays an episode table.
- Clicking an episode shows the multi-camera viewer and state/action summary.

Current status: done.

Remaining hardening:

- Add pagination/sorting for large episode lists.
- Add better error messages for missing optional Lance dependencies.
- Add dataset close/reload controls.

## Phase 2: Basic Web Viewer

Goal:

- Enable review without Rerun dependency.

Features:

- Video playback
- Frame scrubber
- State/action plots
- Metadata panel
- Episode label editing

Current status: MVP complete, still needs performance hardening.

Implemented:

- Active/selectable camera `<video>` pane.
- Synchronized multi-camera focus/grid layout.
- Frame scrubber and frame jump controls.
- State/action norm plots with current-frame marker.
- Loading/error states for video metadata.
- Browser-compatible MP4 byte-range serving.
- State/action summary cards.
- Selected-frame metadata panel backed by the frame API.
- Annotation-backed selected-frame exact-label mutation.

Next:

- Add thumbnail or keyframe preview cache.
- Replace in-process range slicing with direct blob/object-store range reads.

## Phase 3: Rerun Web Viewer

Goal:

- Add deeper replay and debugging.

Implementation order:

1. iframe-based `.rrd` or Rerun serve URL.
2. JavaScript package integration.
3. React wrapper.
4. gRPC streaming.

Current status: partial.

Implemented:

- Backend creates `.rrd` cache files for state/action scalar timelines.
- API serves generated recordings.
- Web embeds ready `.rrd` recordings through `@rerun-io/web-viewer-react`.
- Camera MP4 blobs are logged as Rerun `AssetVideo` entities when available,
  with per-frame `VideoFrameReference` entries on the frame timeline.
- Deterministic cache keys reuse `.rrd` files for the same dataset, episode,
  mode, and visualization config.

Next:

- Add gRPC streaming and deeper viewer control for long interactive replay.

## Phase 4: Annotation System

Goal:

- Human-in-the-loop curation.

Features:

- Episode caption editing
- Success/failure flag
- Phase segment CRUD
- Bad frame/range marking
- Review status
- Annotation history

Current status: done for the local MVP path.

Implemented:

- Segment annotation CRUD.
- JSONL persistence.
- Optional Lance mirror.
- Review status updates.
- Immutable annotation history API and JSONL audit trail.
- Segment edit form and midpoint split action in the web UI.
- Episode-level label editing for caption, success/failure, failure reason,
  quality, split, and review status.
- Timeline click-to-marker, bad-range authoring, boundary drag, split, merge,
  and delete controls.

Next:

- Add a dedicated history browser and richer reviewer workflow UI.

## Phase 5: VLM Auto-Labeling

Goal:

- Generate annotation proposals.

Initial approach:

- Extract 8 to 16 keyframes per episode.
- Ask a VLM for episode caption, phase ranges, success/failure, objects, and
  important frames.
- Store all output as pending annotations.

Current status: partial.

Implemented:

- Synchronous job API.
- Heuristic proposal generator.
- Pending annotations are created for review.
- Deterministic 8 to 16 frame index sampling for prompt inputs.
- Versioned prompt registry and prompt validation.
- VLM provider interface with heuristic fallback provider.
- Raw provider responses persisted to job-scoped JSONL.
- Optional OpenCV keyframe image extraction from available episode video blobs.
- Optional OpenAI-compatible provider path selected by model prefix or
  environment configuration.
- Generated-label review queue with accept/reject actions.

Next:

- Move job execution to RQ/Celery.
- Add local VLM provider implementations.
- Add confidence rationale fields to real provider responses.

## Phase 6: Search and Filtering

Goal:

- Build training subsets quickly.

Features:

- SQL-like filters
- Full-text search
- Embedding search
- Combined search
- Saved filter presets

Current status: partial.

Implemented:

- Basic `AND` filter syntax.
- Typed web filter builder for common episode fields.
- Saved filter presets.
- Full-text search over episode metadata and annotations.
- Deterministic text-embedding semantic search over episode text and
  annotations.
- Optional LanceDB vector table mirror/query path for deterministic embeddings.
- Optional OpenAI-compatible text embedding provider.
- Visual keyframe embedding jobs with deterministic fallback and optional
  Transformers CLIP/SigLIP/DINO-style image model route.

Next:

- Add cross-modal visual search over compatible CLIP/SigLIP records.
- Move embedding jobs to a queue-backed worker process.

## Phase 7: Export and Versioning

Goal:

- Produce training-ready datasets.

Targets:

- LeRobotDataset
- Hugging Face Dataset
- Lance subset
- JSONL captions
- VLA training format

Current status: partial.

Implemented:

- Selected episode export manifest.
- Metadata-oriented LeRobot v3 snapshot.
- Frame JSONL and available camera MP4 artifact materialization.
- Export validation report.
- Optional official LeRobotDataset loader validation.
- Lance subset export for selected episodes when optional Lance dependencies are
  installed.
- JSONL caption export and VLA-style JSONL trajectory export.
- `hf_dataset` export requests fail explicitly until a native Hugging Face
  Dataset artifact is implemented.
- Export scope controls for selected episode or current train/val/test split.
- Queue-backed export jobs through the shared job progress event stream.
- Queue-backed Rerun session jobs with persisted session records.
- Accepted annotations only.
- Version lineage JSONL plus optional Lance mirror.

Next:

- Materialize fully LeRobot-loadable Parquet/MP4 artifacts.
- Implement native Hugging Face Dataset export or remove that public format.
