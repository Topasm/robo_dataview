# Roadmap

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
- Clicking an episode shows camera preview placeholders and state/action summary.

## Phase 2: Basic Web Viewer

Goal:

- Enable review without Rerun dependency.

Features:

- Video playback
- Frame scrubber
- State/action plots
- Metadata panel
- Episode label editing

## Phase 3: Rerun Web Viewer

Goal:

- Add deeper replay and debugging.

Implementation order:

1. iframe-based `.rrd` or Rerun serve URL.
2. JavaScript package integration.
3. React wrapper.
4. gRPC streaming.

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

## Phase 5: VLM Auto-Labeling

Goal:

- Generate annotation proposals.

Initial approach:

- Extract 8 to 16 keyframes per episode.
- Ask a VLM for episode caption, phase ranges, success/failure, objects, and
  important frames.
- Store all output as pending annotations.

## Phase 6: Search and Filtering

Goal:

- Build training subsets quickly.

Features:

- SQL-like filters
- Full-text search
- Embedding search
- Combined search
- Saved filter presets

## Phase 7: Export and Versioning

Goal:

- Produce training-ready datasets.

Targets:

- LeRobotDataset
- Hugging Face Dataset
- Lance subset
- JSONL captions
- VLA training format
