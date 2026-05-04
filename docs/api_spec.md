# API Spec

Base path: `/api`

This spec reflects the current local MVP. Some endpoints are scaffolds and are
called out explicitly.

## Datasets

```text
GET  /datasets
POST /datasets/open
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

## Episodes

```text
GET /episodes?dataset_id=...
GET /episodes/{episode_index}?dataset_id=...
PATCH /episodes/{episode_index}/labels?dataset_id=...
GET /episodes/{episode_index}/video/{camera}?dataset_id=...
GET /episodes/{episode_index}/state-action?dataset_id=...
GET /episodes/{episode_index}/timeseries?dataset_id=...
```

`GET /episodes` supports `limit` and `offset` query params.

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

`GET /episodes/{episode_index}/video/{camera}` streams an MP4 blob when the
episode table has a matching video blob column. It supports `GET` and `HEAD`,
returns `Accept-Ranges: bytes`, and handles single byte-range requests for
browser video playback.

Current implementation detail:

- The store reads the full episode-table video blob through `take_blobs` or a
  row fallback, then the API slices the requested byte range in process.
- The endpoint does not use `videos.lance` provenance lookup yet.
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

`PATCH /frames/{frame_index}` currently supports the `is_bad_frame` mutation.
It writes through `annotations` by creating or accepting an exact-frame
`bad_frame` label, or rejecting that exact-frame label when clearing the flag.

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
POST   /annotations
PATCH  /annotations/{annotation_id}
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
  "review_status": "accepted"
}
```

## Search

```text
POST /search/filter
POST /search/semantic
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
annotations. The default provider is deterministic text hashing. Set
`ROBOT_DATA_STUDIO_EMBEDDING_PROVIDER=openai-compatible` to use an
OpenAI-compatible `/embeddings` endpoint, with
`ROBOT_DATA_STUDIO_EMBEDDING_BASE_URL`,
`ROBOT_DATA_STUDIO_EMBEDDING_API_KEY`,
`ROBOT_DATA_STUDIO_EMBEDDING_MODEL`, and
`ROBOT_DATA_STUDIO_EMBEDDING_TIMEOUT_SECONDS` as needed. When `lancedb` is
installed, rows are mirrored to a local LanceDB table and queried there first;
otherwise the API falls back to an in-memory cosine scorer.

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

Current implementation generates `.rrd` cache files synchronously. The Rerun
recording logs scalar timeline data for timestamps, state norm, and action norm.
When episode camera MP4 blobs are available, the recording also logs Rerun
`AssetVideo` entries and per-frame `VideoFrameReference` rows. Responses include
`cache_key`, `cache_hit`, and `camera_count`; the same dataset, episode, mode,
and visualization config reuses the existing `.rrd` file.

## Jobs

```text
GET  /jobs/vlm-prompts
POST /jobs/vlm-label
GET  /jobs/{job_id}
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
  "format": "lerobot",
  "version_description": "accepted successful episodes"
}
```

For `format=lerobot`, the response `output_uri` points to the export manifest.
The manifest contains an `artifacts.lerobot_v3` object with the metadata snapshot
root, file paths, materialization status, and validation report. The API
response also includes the same `artifacts` object so the web UI can show export
provenance without reading the manifest file.

Each successful export appends a version record to
`data/lance/versions/versions.jsonl`; with optional Lance dependencies installed,
the same records are mirrored to `versions.lance`.

## Implementation Notes

- Service registries are in-process for now. Restarting the API loses open
  dataset/session/job objects unless they are represented by persisted JSONL
  artifacts.
- Annotation, embedding, export, and version records are persisted under
  `data/`.
- Real queue-backed async jobs are planned but not wired yet.
