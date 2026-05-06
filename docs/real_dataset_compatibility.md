# Real Dataset Compatibility

Robot Data Studio should treat real-dataset compatibility as a release gate.
Run the matrix below before claiming a dataset path is production-safe.

## Smoke Command

```bash
./.venv/bin/python scripts/check_dataset_compat.py \
  /path/to/local_lance_dataset \
  hf://datasets/lance-format/lerobot-xvla-soft-fold/data
```

Use `--require-video` when the dataset is expected to expose readable video
blobs or paths:

```bash
./.venv/bin/python scripts/check_dataset_compat.py --require-video /path/to/dataset
```

The script checks:

- dataset open/index
- summary counts and camera names
- paginated episode detail reads
- state/action timeseries availability
- frame API fallback or frame rows
- video source discovery for each listed camera

## Matrix

Dataset layouts:

- LeRobot v2.1 local metadata
- LeRobot v3 local metadata
- Lance-native converted bundle
- `hf://` remote Lance bundle
- metadata-only snapshot
- video-backed snapshot
- no-video snapshot

Video layouts:

- embedded Lance `*_video_blob`
- local MP4 path
- `hf://` path
- HTTP range-readable path
- fsspec object-store path

Structure edge cases:

- contiguous episode indices
- non-contiguous episode indices
- more than 1000 episodes
- multi-camera episodes
- missing/optional camera episodes
- variable FPS or timestamp drift
- metadata-only state/action dimensions

Required workflow per case:

```text
open -> summary -> episode page -> episode detail -> frames/timeseries
-> video source -> annotation edit -> VLM proposal -> export
-> LeRobot snapshot validation
```

Passing this smoke does not prove model quality. It proves the dataset can move
through Robot Data Studio without silently dropping episodes or losing the
training/export contract.
