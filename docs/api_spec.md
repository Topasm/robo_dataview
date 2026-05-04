# API Spec

Base path: `/api`

## Datasets

```text
GET  /datasets
POST /datasets/open
GET  /datasets/{dataset_id}/summary
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

## Rerun

```text
POST /rerun/session
GET  /rerun/session/{session_id}
```

`POST /rerun/session`

```json
{
  "dataset_id": "xvla-soft-fold",
  "episode_index": 30,
  "mode": "rrd_cache"
}
```

## Jobs

```text
POST /jobs/vlm-label
GET  /jobs/{job_id}
```

## Exports

```text
POST /exports
GET  /exports/{export_id}
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
