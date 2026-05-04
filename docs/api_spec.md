# API Spec

Base path: `/api`

This spec reflects the current local MVP. Some endpoints are scaffolds and are
called out explicitly.

## Auth And User Identity

```text
GET /users/me
```

By default the API runs in local open mode. If `ROBOT_DATA_STUDIO_API_KEY` is
set, `/api/*` requests must include:

```text
X-Robot-Data-Studio-API-Key: <configured key>
```

Review/audit identity is supplied by:

```text
X-Robot-Data-Studio-User: alice
```

When the user header is omitted, the API records `local`.

## Datasets

```text
GET  /datasets
POST /datasets/open
POST /datasets/{dataset_id}/reload
DELETE /datasets/{dataset_id}
GET  /datasets/{dataset_id}/summary
GET  /datasets/{dataset_id}/schema
```

`POST /datasets/open`

```json
{
  "uri": "/data/lance/xvla-soft-fold",
  "name": "xvla-soft-fold"
}
```

Response:

```json
{
  "dataset_id": "xvla-soft-fold",
  "name": "xvla-soft-fold",
  "uri": "/data/lance/xvla-soft-fold",
  "status": "indexed"
}
```

Opened non-sample datasets are persisted in a local registry and re-opened when
the API process restarts. `POST /datasets/{dataset_id}/reload` re-indexes an
opened dataset from its stored URI and display name. `DELETE /datasets/{dataset_id}`
closes the dataset and removes it from the restart registry without deleting raw
data or local annotation overlays.

## Episodes

```text
GET /episodes?dataset_id=...
GET /episodes/page?dataset_id=...
GET /episodes/{episode_index}?dataset_id=...
PATCH /episodes/{episode_index}/labels?dataset_id=...
GET /episodes/{episode_index}/preview/{camera}?dataset_id=...&frame_index=...
GET /episodes/{episode_index}/video/{camera}?dataset_id=...
GET /episodes/{episode_index}/state-action?dataset_id=...
GET /episodes/{episode_index}/timeseries?dataset_id=...
```

`GET /episodes` supports `limit`, `offset`, `sort_by`, `sort_order`, and
`filter_query` query params while preserving the legacy array response.
`GET /episodes/page` accepts the same params and returns pagination metadata:

```json
{
  "dataset_id": "xvla-soft-fold",
  "items": [],
  "total": 1542,
  "limit": 100,
  "offset": 0,
  "next_offset": 100,
  "previous_offset": null,
  "sort_by": "episode_index",
  "sort_order": "asc",
  "filter_query": "review_status == \"accepted\""
}
```

`PATCH /episodes/{episode_index}/labels` stores curation labels as a local
overlay without mutating the raw Lance dataset. Supported fields:

```json
{
  "caption": "Reviewed folding attempt",
  "success_label": true,
  "failure_reason": null,
  "quality_score": 0.9,
  "split": "train",
  "review_status": "accepted"
}
```

`GET /episodes/{episode_index}/preview/{camera}` returns a cached JPEG preview
frame for browser posters and episode-list thumbnails. It uses OpenCV when
available, caches generated files under `data/cache/previews`, and returns `503`
when optional video decoding dependencies are missing.

`GET /episodes/{episode_index}/video/{camera}` streams an MP4 blob when the
episode table has a matching video blob column, including
`observation_images_<camera>_video_blob` layouts. If the episode table has no
matching blob, the store falls back to `videos.lance` rows that can be matched by
`episode_index` and camera or by LeRobot-style episode shard metadata. Fallback
rows may provide either a materialized `video_blob` or a local path such as
`relative_path`/`video_file`. It supports `GET` and `HEAD`, returns
`Accept-Ranges: bytes`, and handles single byte-range requests for browser video
playback.

Current implementation detail:

- The store reads the full episode-table video blob through `take_blobs` or a
  row fallback, then the API slices the requested byte range in process.
- Path-only `videos.lance` fallback is local-filesystem only. For local paths,
  the API streams the requested byte range directly from disk without reading the
  whole file first.
- Remote object storage/HF path streaming is not implemented yet.
- Suffix byte ranges such as `bytes=-500` are not supported.

## Frames

```text
GET /frames?dataset_id=...&episode_index=...&start_frame=...&end_frame=...&limit=...
PATCH /frames/{frame_index}?dataset_id=...&episode_index=...
```

Returns frame-level samples for one episode. The backend prefers `frames.lance`
when available and falls back to episode-level state/action time series. Each
frame includes timestamp, state/action vectors when present, computed norms,
overlapping annotation labels, and an `is_bad_frame` flag derived from raw frame
metadata or non-rejected `bad_frame`, `bad_range`, and `bad_episode`
annotations.

`PATCH /frames/{frame_index}` supports annotation-backed exact-frame labels. Use
`is_bad_frame` for the bad-frame shortcut, or send `label_type`, `label_value`,
and `label_enabled` to create/accept or reject a label whose `start_frame` and
`end_frame` both match the selected frame.

Response shape:

```json
{
  "dataset_id": "xvla-soft-fold",
  "episode_index": 30,
  "frame_count": 180,
  "start_frame": 40,
  "end_frame": 45,
  "limit": 100,
  "returned_count": 6,
  "items": [
    {
      "dataset_id": "xvla-soft-fold",
      "episode_index": 30,
      "frame_index": 40,
      "timestamp": 2.0,
      "task_index": 3,
      "observation_state": [0.12, 0.34],
      "action": [0.0, 0.2],
      "state_norm": 0.36,
      "action_norm": 0.2,
      "is_bad_frame": false,
      "labels": []
    }
  ]
}
```

## Annotations

```text
GET    /annotations?dataset_id=...&episode_index=...
GET    /annotations/history?dataset_id=...&episode_index=...&annotation_id=...
POST   /annotations
PATCH  /annotations/{annotation_id}
PATCH  /annotations/{annotation_id}/assignment
DELETE /annotations/{annotation_id}
```

`POST /annotations`

```json
{
  "dataset_id": "xvla-soft-fold",
  "episode_index": 30,
  "start_frame": 45,
  "end_frame": 88,
  "label_type": "phase",
  "label_value": "cloth_edge_grasp",
  "source": "human",
  "confidence": 1.0,
  "review_status": "accepted",
  "assigned_to": "reviewer-a"
}
```

`PATCH /annotations/{annotation_id}/assignment`

```json
{
  "assigned_to": "reviewer-b"
}
```

`GET /annotations/history` returns immutable audit events for annotation
creates, updates, and deletes. Each event includes `action`, `actor`, `before`,
`after`, and `created_at`. `episode_index` and `annotation_id` filters are
optional.

## Search

```text
POST /search/filter
POST /search/semantic
POST /search/full-text
GET  /search/filter-presets?dataset_id=...
POST /search/filter-presets
DELETE /search/filter-presets/{preset_id}
```

`POST /search/filter`

```json
{
  "dataset_id": "xvla-soft-fold",
  "query": "success_label = true AND quality_score > 0.8",
  "limit": 100
}
```

MVP filter syntax supports `AND` clauses with `=`, `==`, `!=`, `>`, `>=`, `<`,
`<=`, and `contains` over episode-list fields such as `episode_index`,
`task_index`, `success_label`, `quality_score`, `review_status`, `caption`, and
`split`.

`POST /search/semantic` currently uses text embeddings over episode text and
annotations. It also accepts an optional `filter_query` using the same structured
episode-filter syntax as `POST /search/filter`; when present, semantic ranking is
limited to matching episodes and their annotations. Filtered semantic searches
use a transient in-memory index so they do not overwrite the persisted full
dataset embedding mirror. The default provider is deterministic text hashing. Set
`ROBOT_DATA_STUDIO_EMBEDDING_PROVIDER=openai-compatible` to use an
OpenAI-compatible `/embeddings` endpoint, with
`ROBOT_DATA_STUDIO_EMBEDDING_BASE_URL`,
`ROBOT_DATA_STUDIO_EMBEDDING_API_KEY`,
`ROBOT_DATA_STUDIO_EMBEDDING_MODEL`, and
`ROBOT_DATA_STUDIO_EMBEDDING_TIMEOUT_SECONDS` as needed. When `lancedb` is
installed, rows are mirrored to a local LanceDB table and queried there first;
otherwise the API falls back to an in-memory cosine scorer.

`POST /search/full-text` tokenizes episode metadata and annotation text, then
returns ranked `full_text_episode` and `full_text_annotation` matches with
frame indices when the matching annotation is exact-frame.

Filter presets persist reusable structured filter queries to
`data/lance/filter_presets/filter_presets.jsonl`.

## Rerun

```text
POST /rerun/session
GET  /rerun/session/{session_id}
GET  /rerun/recordings/{session_id}.rrd
```

`POST /rerun/session`

```json
{
  "dataset_id": "xvla-soft-fold",
  "episode_index": 30,
  "mode": "rrd_cache"
}
```

`POST /rerun/session` invokes the local Rerun cache worker synchronously. Use
`POST /jobs/rerun-session` for queued generation. The Rerun recording logs
scalar timeline data for timestamps, state norm, and action norm. When episode
camera MP4 blobs are available, the recording also logs Rerun `AssetVideo`
entries and per-frame `VideoFrameReference` rows. Responses include `cache_key`,
`cache_hit`, and `camera_count`; the same dataset, episode, mode, and
visualization config reuses the existing `.rrd` file.

## Jobs

```text
GET  /jobs/vlm-prompts
POST /jobs/vlm-label
POST /jobs/visual-embeddings
POST /jobs/export
POST /jobs/rerun-session
GET  /jobs/{job_id}
GET  /jobs/{job_id}/events
```

`GET /jobs/vlm-prompts` returns registered VLM prompt templates and versions.
`POST /jobs/vlm-label` rejects unknown `prompt_template` values with `400`.
Job records include `model`, `provider`, `prompt_template`, and
`prompt_version` so generated annotation batches can be traced to the model
route and prompt contract used. VLM jobs also write raw provider responses to
JSONL and return `raw_response_ids` plus `raw_response_uri`. When camera MP4
blobs are available and optional video dependencies are installed, raw responses
include decoded keyframe JPEG artifact metadata.

The default model route uses the heuristic fallback provider. Set
`model = "openai-compatible:<model-name>"` or
`ROBOT_DATA_STUDIO_VLM_PROVIDER=openai-compatible` to use the optional
OpenAI-compatible `/chat/completions` provider. Configure
`ROBOT_DATA_STUDIO_VLM_BASE_URL`, `ROBOT_DATA_STUDIO_VLM_API_KEY`, and
`ROBOT_DATA_STUDIO_VLM_TIMEOUT_SECONDS` as needed. The web VLM button can be
pointed at this route with `NEXT_PUBLIC_VLM_MODEL`.

`POST /jobs/visual-embeddings`

```json
{
  "dataset_id": "xvla-soft-fold",
  "episode_indices": [1, 2, 3],
  "model": "clip:openai/clip-vit-base-patch32",
  "camera_names": ["cam_high"],
  "min_keyframes": 8,
  "max_keyframes": 16
}
```

This local worker path samples keyframes, decodes cached JPEGs, writes image
embedding rows to the shared embedding store, and returns
`created_embedding_ids`, `artifact_count`, and `provider`. The default model
uses deterministic image hashing for local development. Use
`ROBOT_DATA_STUDIO_VISUAL_EMBEDDING_PROVIDER=transformers` or a model prefix
such as `clip:`, `siglip:`, `dino:`, or `transformers:` to route images through
an optional Transformers vision model.

`POST /jobs/export` accepts the same payload as `POST /exports`, returns a
`JobRecord`, and runs through the configured job backend when
`ROBOT_DATA_STUDIO_JOB_QUEUE=rq`. The completed job records
`created_export_id`, `export_format`, and `export_uri`. `GET /jobs/{job_id}/events`
streams those fields with the existing job progress event so clients can track
long-running LeRobot, Lance, JSONL, or VLA exports without blocking the request.

`POST /jobs/rerun-session` accepts the same payload as `POST /rerun/session`,
returns a `JobRecord`, and runs `.rrd` generation through the configured job
backend. The completed job records `created_rerun_session_id`, `rerun_rrd_url`,
`rerun_rrd_path`, and `rerun_viewer_url`; clients should fetch
`GET /rerun/session/{session_id}` before opening the viewer. Rerun session
records are persisted under `data/app/rerun_sessions.jsonl` so API and worker
processes can share queued session results.

## Exports

```text
POST /exports
GET  /exports/{export_id}
GET  /versions?dataset_id=...
```

`POST /exports`

```json
{
  "dataset_id": "xvla-soft-fold",
  "episode_indices": [1, 2, 3],
  "splits": [],
  "format": "lerobot",
  "version_description": "accepted successful episodes"
}
```

`POST /exports` runs synchronously and returns the final export record. Use
`POST /jobs/export` with the same payload when the export should be queued and
tracked through `/jobs/{job_id}` or `/jobs/{job_id}/events`.

When `episode_indices` is empty, `splits` can select all episodes whose saved
split matches values such as `train`, `val`, or `test`.

For `format=lerobot`, the response `output_uri` points to the export manifest.
The manifest contains an `artifacts.lerobot_v3` object with the metadata snapshot
root, file paths, materialization status, and validation report. The API
response also includes the same `artifacts` object so the web UI can show export
provenance without reading the manifest file. The validation report includes a
local loadability heuristic and an `official_loader` object. The exported frame
rows include LeRobot's global `index` column and compact local episode/task
indices; original dataset indices are preserved as `source_episode_index` and
`source_task_index`. Episode metadata includes `tasks`, `dataset_from_index`,
`dataset_to_index`, data shard indices, and per-camera video shard/timestamp
fields. The JSONL readability copy keeps internal per-frame video references;
the optional Parquet data shard omits video feature columns and relies on
episode video metadata, matching the official LeRobot/Hugging Face feature
conversion path. When the optional `lerobot` package is installed, the official
loader result records success, dataset length, or the exact exception.
`lerobot_loadable=true` means the official loader was available and succeeded.
When the official loader is unavailable, `local_lerobot_loadable_heuristic` can
still describe whether the local artifact shape appears complete, and
`loadability_basis` records that this is not an official load result.
If the LeRobot validation report has `metadata_ok=false`, the export request
returns `status=failed` instead of writing a successful manifest.

For `format=lance`, the response contains `artifacts.lance_subset` when optional
`pyarrow` and `lance` dependencies are installed. The subset contains
`episodes.lance`, `frames.lance`, `videos.lance`, and `annotations.lance`
tables for selected episodes, available camera video blobs, and accepted
annotations only. If those optional dependencies are missing, the export fails
with a dependency message instead of returning an empty successful artifact. The
validation report opens each Lance table when possible and checks table row
counts against the export metadata; failed validation returns `status=failed`.

For `format=jsonl`, the response contains `artifacts.jsonl` with
`episodes.jsonl`, `captions.jsonl`, and accepted `annotations.jsonl`. For
`format=vla`, the response contains `artifacts.vla_jsonl` with one
`examples.jsonl` row per selected episode, including instruction/caption,
state/action time series when available, labels, and accepted annotations.

`format=hf_dataset` is reserved for a future native Hugging Face Dataset
artifact. Requests fail explicitly until that export path is implemented; use
`format=lerobot` for LeRobot/HF-compatible snapshot files or `format=jsonl` for
portable caption data.

Each successful export appends a version record to
`data/lance/versions/versions.jsonl`; with optional Lance dependencies installed,
the same records are mirrored to `versions.lance`.

## Implementation Notes

- Service registries are in-process for now. Restarting the API loses open
  dataset/session/job objects unless they are represented by persisted JSONL
  artifacts.
- Annotation, embedding, export, and version records are persisted under
  `data/`.
- VLM, visual embedding, export, and Rerun session jobs can run through the
  optional RQ backend.
