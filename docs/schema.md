# Data Schema

This schema targets Lance-native LeRobot datasets with separate tables for
frame-level sampling, episode-level replay, raw videos, annotations, embeddings,
and curated versions.

## Current Storage Contract

The target source of truth is Lance-compatible storage. The current local MVP
uses JSONL as the mandatory durable fallback and mirrors to `.lance` datasets
when optional `pyarrow` and `lance` packages are available.

```text
data/lance/annotations/<dataset>/annotations.jsonl
data/lance/annotations/<dataset>/annotations.lance

data/lance/embeddings/<dataset>/embeddings.jsonl
data/lance/embeddings/<dataset>/embeddings.lance

data/lance/versions/versions.jsonl
data/lance/versions/versions.lance
```

The imported `xvla-soft-fold` dataset currently exposes camera names like:

```text
observation_images_cam_high
observation_images_cam_left_wrist
observation_images_cam_right_wrist
```

The target examples below use shorter camera names for readability. Loader code
should keep supporting generic camera columns instead of hard-coding names.

The shared `packages/robot_schema` package currently defines local curation
schemas for `annotations.lance`, `embeddings.lance`, and `versions.lance`. It
does not yet define the full raw `frames.lance`, `episodes.lance`, or
`videos.lance` schemas as code.

## frames.lance

Purpose:

- Training sample access
- Frame-level filtering
- State/action statistics
- Bad-frame detection

Columns:

```text
episode_index: int64
frame_index: int64
timestamp: float64
task_index: int64
observation_state: fixed/list<float32>
action: fixed/list<float32>
is_bad_frame: bool
state_norm: float32
action_norm: float32
phase_label: string
vlm_step_caption: string
human_step_caption: string
review_status: string
```

Current status: frame schema is documented but the frame API is still a
placeholder. Frame-level sampling, bad-frame labels, and frame mutation are not
implemented yet.

## episodes.lance

Purpose:

- Episode replay
- Sequential trajectory loading
- Multi-camera sync
- Episode-level labels

Columns:

```text
episode_index: int64
task_index: int64
fps: float32
timestamps: list<float64>
actions: list<fixed/list<float32>>
observation_state: list<fixed/list<float32>>
cam_high_video_blob: binary
cam_left_wrist_video_blob: binary
cam_right_wrist_video_blob: binary
language_instruction: string
episode_caption: string
success_label: bool
failure_reason: string
quality_score: float32
review_status: string
train_val_test_split: string
```

## videos.lance

Purpose:

- Original video provenance
- Integrity checking
- Raw MP4 access
- Custom decoding

Columns:

```text
camera_angle: string
relative_path: string
filename: string
file_size_bytes: int64
sha256: string
video_blob: binary
```

Current status: `videos.lance` is part of the target architecture, but the
current playback path reads video blobs directly from `episodes.lance` columns.
Provenance lookup and SHA256 validation through `videos.lance` are not wired.

## annotations.lance

Purpose:

- Durable human and machine labels
- Review workflow
- Segment/frame/episode-level curation

Columns:

```text
annotation_id: string
dataset_id: string
episode_index: int64
start_frame: int64
end_frame: int64
label_type: string
label_value: string
source: string
confidence: float32
review_status: string
created_by: string
created_at: timestamp
updated_at: timestamp
```

The source-of-truth code definition lives in
`packages/robot_schema/lance_tables.py` as `ANNOTATIONS_COLUMNS`. In an
environment with PyArrow installed, `build_annotations_pyarrow_schema()` returns
the schema used to create `annotations.lance`.

The API stores annotations under `data/lance/annotations/<dataset>/`. It always
writes `annotations.jsonl` for restart-safe local development. When `pyarrow`
and `lance` are installed, the same records are mirrored to
`annotations.lance` with the schema above.

Allowed `source` values:

```text
human
vlm
heuristic
import
```

Allowed `review_status` values:

```text
pending
accepted
rejected
edited
```

## embeddings.lance

Purpose:

- Semantic search
- Multimodal retrieval
- VLM output indexing

Columns:

```text
embedding_id: string
episode_index: int64
frame_index: int64
clip_start_frame: int64
clip_end_frame: int64
modality: string
embedding: fixed/list<float32>
text: string
source_model: string
created_at: timestamp
```

The source-of-truth code definition lives in
`packages/robot_schema/lance_tables.py` as `EMBEDDINGS_COLUMNS`. In an
environment with PyArrow installed, `build_embeddings_pyarrow_schema()` returns
the schema used to create `embeddings.lance`.

The API writes deterministic text embeddings under
`data/lance/embeddings/<dataset>/embeddings.jsonl` for local search. When
`pyarrow` and `lance` are installed, these rows are mirrored to
`embeddings.lance`.

Current status: embeddings are deterministic 64-dimensional text-hash vectors.
They are intended as a no-model local development path, not the final visual or
video embedding system.

## versions.lance

Purpose:

- Dataset lineage
- Export records
- Reproducible filtered subsets

Columns:

```text
version_id: string
parent_version_id: string
dataset_id: string
description: string
filter_query: string
num_episodes: int64
num_frames: int64
export_format: string
created_at: timestamp
created_by: string
```

The API appends version rows to `data/lance/versions/versions.jsonl` whenever an
export succeeds. With `pyarrow` and `lance` installed, rows are mirrored to
`versions.lance`.

Note: `export_uri` is also part of the current code schema so export manifests
can be resolved from version rows.

## LeRobot v3 export snapshot

`format=lerobot` exports currently write a metadata-only v3-oriented snapshot:

```text
lerobot_v3/
├─ meta/
│  ├─ info.json
│  ├─ stats.json
│  ├─ tasks.parquet              # when pyarrow is installed
│  ├─ tasks.jsonl                # fallback/readability copy
│  └─ episodes/chunk-000/
│     ├─ file-000.parquet        # when pyarrow is installed
│     └─ file-000.jsonl          # fallback/readability copy
├─ data/chunk-000/file-000.index.jsonl
├─ videos/
├─ annotations/annotations.jsonl
└─ validation.json
```

The snapshot follows the LeRobot v3 directory contract for selected episodes and
accepted annotations. It now writes official metadata parquet files when
`pyarrow` is installed, but it is still not a full Parquet/MP4 materialization:
`data/chunk-*/file-*.parquet` and `videos/<camera>/chunk-*/file-*.mp4` are not
materialized yet. Full materialization needs the optional `lerobot`, `pyarrow`,
and video encoding dependencies.
