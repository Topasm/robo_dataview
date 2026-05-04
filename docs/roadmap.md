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
Phase 7  Export and Versioning        done
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
- Add object-storage publishing for thumbnail and keyframe preview cache
  artifacts.

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
- Deterministic cache keys reuse `.rrd` files for the same dataset
  fingerprint, episode, mode, and visualization config.

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
- Optional local Ollama-compatible provider path selected by model prefix or
  environment configuration.
- Generated-label review queue with accept/reject actions.

Next:

- Move job execution to RQ/Celery.
- Add direct in-process local VLM provider implementations beyond Ollama.
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
- Semantic search modality/source-model filters for stored visual rows.
- Optional CLIP/SigLIP text encoder route for compatible text-to-image search.

Next:

- Run a real CLIP/SigLIP text-to-image search smoke with generated visual
  embeddings.
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

Current status: done for the local MVP path; larger production dataset
validation remains a hardening task.

Implemented:

- Selected episode export manifest.
- LeRobot v3 snapshot with metadata, frame JSONL readability copy, Parquet data
  shard, task/episode metadata shards, and available MP4 artifacts.
- Frame JSONL and available camera MP4 artifact materialization.
- Data Parquet writing uses Hugging Face Dataset feature conversion when
  optional `datasets` is installed, excluding video feature columns from the
  tabular shard.
- Video feature metadata records `[height, width, channel]` shape and
  `video_info`, with MP4 `tkhd` dimensions captured when available.
- Validation records optional OpenCV video decode metadata for exported MP4
  artifacts.
- Export validation report.
- Optional official LeRobotDataset loader validation.
- Lance subset export for selected episodes when optional Lance dependencies are
  installed.
- JSONL caption export and VLA-style JSONL trajectory export.
- Native `hf_dataset` export writes a frame-level Hugging Face
  `Dataset.save_to_disk()` artifact when optional `datasets` dependencies are
  installed.
- Export scope controls for selected episode or current train/val/test split.
- Web export strip can launch LeRobot, Lance, JSONL, VLA, and HF Dataset
  exports.
- Manual official-dependency workflow can verify native HF Dataset export with
  real `datasets.save_to_disk()` / `load_from_disk()`.
- Manual official-dependency workflow can verify a no-video LeRobot snapshot
  with `LeRobotDataset(repo_id, root=...)`.
- Manual official-dependency workflow can generate a tiny MP4 and verify a
  video-backed LeRobot snapshot with the official loader when optional video
  dependencies are installed.
- Latest manual official-dependency workflow passed against commit `e0c476d`.
- Opt-in real-dataset export smoke workflow can open a configured `hf://` Lance
  URI, export up to 64 episodes from a selected offset, optionally materialize
  videos, require all selected cameras, and validate the snapshot with the
  official loader.
- Queue-backed export jobs through the shared job progress event stream.
- Queue-backed Rerun session jobs with persisted session records.
- Optional export artifact publishing to local or `fsspec` destinations through
  `publish_uri` or `ROBOT_DATA_STUDIO_EXPORT_PUBLISH_URI`.
- Optional Rerun cache artifact publishing to local or `fsspec`
  destinations through `publish_uri`,
  `ROBOT_DATA_STUDIO_RERUN_CACHE_PUBLISH_URI`, or
  `ROBOT_DATA_STUDIO_CACHE_PUBLISH_URI`.
- Optional keyframe and preview cache artifact publishing to local or
  `fsspec` destinations through cache publish environment variables.
- Manual visual-model smoke workflow can verify a real Transformers
  CLIP/SigLIP-compatible model through matching text and image embedding
  providers.
- Manual artifact-publish smoke workflow can verify local publish paths for
  keyframes, previews, Rerun recordings, and exports.
- Accepted annotations only.
- Version lineage JSONL plus optional Lance mirror.

Next:

- Run the real-dataset export smoke workflow with video materialization and on
  larger representative multi-camera subsets.
- Run the manual visual-model smoke workflow with the target CLIP/SigLIP model.
