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

data/lance/vlm_responses/<dataset>/<job_id>.jsonl
data/lance/filter_presets/filter_presets.jsonl

data/app/metadata.sqlite3

data/cache/keyframes/<dataset>/episode_<index>/<prompt>_<version>/*.jpg
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

Current status: `GET /frames` can read frame rows from `frames.lance` when
available and falls back to episode-level state/action time series. It returns
state/action vectors, computed norms, overlapping annotation labels, and
bad-frame flags. `PATCH /frames/{frame_index}` can add, accept, or reject
annotation-backed exact-frame labels such as `bad_frame`, `important_frame`,
`occlusion`, and `gripper_contact`. Full raw-frame mutation and durable
raw-frame schema helpers are not implemented yet.

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

Current status: playback prefers per-episode video blob columns from
`episodes.lance`, including `observation_images_<camera>_video_blob` layouts.
If those are absent, the API can fall back to `videos.lance` rows when they
carry an `episode_index` plus camera column, or when episode metadata contains
LeRobot-style `videos/<video_key>/chunk_index` and
`videos/<video_key>/file_index` shard references. The fallback reads
materialized `video_blob` values first, then local path provenance such as
`relative_path` or `video_file` when the referenced MP4 exists under the local
dataset root. SHA256 validation is not wired yet.

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

Every create, update, and delete also appends an immutable event to
`history.jsonl` in the same dataset directory. History events include the
annotation id, episode index, action, actor, timestamp, and before/after
annotation snapshots so review changes can be audited without mutating raw Lance
tables.

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
camera: string
source_uri: string
content_hash: string
```

The source-of-truth code definition lives in
`packages/robot_schema/lance_tables.py` as `EMBEDDINGS_COLUMNS`. In an
environment with PyArrow installed, `build_embeddings_pyarrow_schema()` returns
the schema used to create `embeddings.lance`.

The API writes text embeddings under
`data/lance/embeddings/<dataset>/embeddings.jsonl` for local search. The default
provider is a deterministic 64-dimensional text-hash fallback. When
`ROBOT_DATA_STUDIO_EMBEDDING_PROVIDER=openai-compatible` is configured, the
same table stores model-backed text vectors from an OpenAI-compatible
`/embeddings` endpoint. When `pyarrow` and `lance` are installed, these rows
are mirrored to `embeddings.lance`. When `lancedb` is installed, rows are also
mirrored to `data/lance/embeddings/<dataset>/lancedb` and semantic search tries
that vector table before falling back to the in-memory cosine scorer.

Visual embedding jobs append image records generated from sampled keyframe JPEGs.
The default visual provider is deterministic for local testing. Set
`ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_PROVIDER=transformers`, or use a job model
prefix such as `clip:openai/clip-vit-base-patch32`,
`siglip:<model-name>`, `dino:<model-name>`, or `transformers:<model-name>`, to
route keyframes through an optional Transformers vision model. Visual rows store
`camera`, `source_uri`, and `content_hash` so multi-camera frame embeddings are
traceable.

Current status: text semantic search and visual image embedding generation are
implemented as separate paths. Cross-modal text-to-image search should only rank
visual rows when the query and image vectors come from a compatible model family.

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

`format=lerobot` exports currently write a LeRobot v3-oriented snapshot:

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
├─ data/chunk-000/
│  ├─ file-000.parquet           # when pyarrow is installed
│  ├─ file-000.jsonl             # fallback/readability copy
│  └─ file-000.index.jsonl
├─ videos/
│  ├─ video_index.jsonl
│  └─ <camera>/chunk-000/file-<index>.mp4
├─ annotations/annotations.jsonl
└─ validation.json
```

The snapshot follows the LeRobot v3 directory contract for selected episodes and
accepted annotations. It writes frame JSONL and available camera MP4 blobs, and
also writes Parquet shards when `pyarrow` is installed. For materialized frame
exports, `meta/info.json` derives concrete `observation.state` and `action`
feature dimensions from exported rows, and `meta/stats.json` contains
mean/std/min/max statistics for exported numeric frame features. Frame rows
include LeRobot's global `index` column in addition to compact local
`episode_index`, `frame_index`, `timestamp`, compact local `task_index`,
`source_episode_index`, `source_task_index`, `observation.state`, and `action`.
When camera MP4 artifacts are present, each frame row also includes a LeRobot
video-frame reference under the exported video feature key:

```json
{
  "cam_high": {
    "path": "videos/cam_high/chunk-000/file-000.mp4",
    "timestamp": 0.05
  }
}
```

Episode metadata includes `meta/episodes/chunk_index`,
`meta/episodes/file_index`, `tasks`, `dataset_from_index`, `dataset_to_index`,
`data/chunk_index`, `data/file_index`, and per-camera
`videos/<video_key>/chunk_index`, `videos/<video_key>/file_index`,
`videos/<video_key>/from_timestamp`, and `videos/<video_key>/to_timestamp`
entries so the official `data_path` and `video_path` templates can resolve
copied artifacts.
`validation.json` contains both the local loadability heuristic and an
`official_loader` result. The local heuristic requires Parquet task, episode,
and frame data plus LeRobot offset metadata, video timestamp metadata, and
valid per-frame video references when video artifacts are present. When the
optional `lerobot` package is installed, validation attempts
`LeRobotDataset(repo_id, root=<export_root>)` and records success, dataset
length, or the exact exception.

## Lance subset export

`format=lance` exports write a selected subset when optional `pyarrow` and
`lance` dependencies are installed:

```text
lance_subset/
├─ metadata.json
├─ episodes.lance
├─ frames.lance
├─ annotations.lance
└─ validation.json
```

The subset includes selected episode metadata, frame-level state/action samples
from `frames.lance` or the episode time-series fallback, and accepted
annotations only. Missing optional Lance dependencies fail the export explicitly
so callers do not mistake a manifest-only export for a usable Lance dataset.

## JSONL and VLA exports

`format=jsonl` writes lightweight curation files:

```text
jsonl_export/
├─ metadata.json
├─ episodes.jsonl
├─ captions.jsonl
└─ annotations.jsonl
```

`format=vla` writes one training-oriented JSONL row per selected episode:

```text
vla_export/
├─ metadata.json
└─ examples.jsonl
```

VLA rows include instruction/caption text, review labels, state/action
time-series arrays when available, and accepted annotations. This is not a
replacement for full LeRobot Parquet/MP4 training export, but it provides a
simple interop target for experiments and caption/action pipelines.
