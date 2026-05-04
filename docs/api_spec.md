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
GET /episodes/{episode_index}/video/{camera}?dataset_id=...
GET /episodes/{episode_index}/state-action?dataset_id=...
```

`GET /episodes` supports `limit` and `offset` query params.

`GET /episodes/{episode_index}/video/{camera}` streams an MP4 blob when the
episode table has a matching video blob column.

## Frames

```text
GET /frames?dataset_id=...&episode_index=...&limit=...
```

Current status: placeholder. The endpoint returns an empty `items` array and
`status = "not_implemented"`.

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

`POST /search/semantic` currently uses deterministic text-hash embeddings over
episode text and annotations. It is a local development substitute for future
LanceDB vector search.

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
recording currently logs scalar timeline data for timestamps, state norm, and
action norm.

## Jobs

```text
POST /jobs/vlm-label
GET  /jobs/{job_id}
```

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
root and file paths.

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
