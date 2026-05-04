# Data Schema

This schema targets Lance-native LeRobot datasets with separate tables for
frame-level sampling, episode-level replay, raw videos, annotations, embeddings,
and curated versions.

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
