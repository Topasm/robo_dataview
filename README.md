# Robot Data Studio

Robot Data Studio is a web-based operating tool for Lance-native LeRobot
datasets. Its goal is not only to preview robot data, but to help curate
high-quality datasets for VLA and robot policy training.

## Product Direction

- **Web GUI**: dataset browsing, annotation editing, filtering, review queues,
  export management.
- **Rerun Web Viewer**: episode replay, multi-camera inspection, timelines, 3D
  visualization.
- **Lance / LanceDB**: source of truth for raw data, annotations, embeddings,
  versions, and searchable subsets.
- **Python Workers**: VLM auto-labeling, embedding generation, thumbnails,
  validation, Rerun cache generation, export jobs.

## Target Stack

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Pydantic
- Data: Lance and LanceDB
- Viewer: Rerun Web Viewer
- Workers: Python with RQ or Celery
- Interop: LeRobotDataset and Hugging Face datasets

## Repository Layout

```text
apps/
  api/        FastAPI backend
  web/        Next.js frontend
docs/         Architecture, schema, API, UI, roadmap, deployment, and plan
workers/      Python worker helpers
packages/     Shared schema and prompts
data/         Local Lance data, cache, and exports
```

## Local Development

Robot Data Studio expects you to manage the Python virtual environment
explicitly. The repo scripts use the active shell environment; they do not
create or mutate `.venv`.

Base setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
npm install
cp .env.example .env
```

Optional Python extras:

```bash
python3 -m pip install -e ".[lance]"      # Lance/LanceDB + PyArrow mirrors
python3 -m pip install -e ".[rerun]"      # Rerun .rrd generation
python3 -m pip install -e ".[video]"      # OpenCV keyframe/preview extraction
python3 -m pip install -e ".[storage]"    # remote HF/object-store video paths
python3 -m pip install -e ".[lerobot]"    # official LeRobotDataset validation
python3 -m pip install -e ".[export]"     # optional LeRobot Parquet/MP4 materialization
python3 -m pip install -e ".[queue]"      # Redis/RQ background job queue
python3 -m pip install -e ".[ml]"         # Transformers CLIP/SigLIP smoke checks
```

Run API and web together:

```bash
npm run dev
```

Optional RQ worker mode:

```bash
export ROBOT_DATA_STUDIO_JOB_QUEUE=rq
export ROBOT_DATA_STUDIO_REDIS_URL=redis://127.0.0.1:6379/0
rq worker robot-data-studio --url "$ROBOT_DATA_STUDIO_REDIS_URL"
```

With `ROBOT_DATA_STUDIO_JOB_QUEUE` unset, jobs run inline in the API process for
local development.

Set `ROBOT_DATA_STUDIO_API_KEY` to require `X-Robot-Data-Studio-API-Key` on
`/api/*` requests. Review actions can pass `X-Robot-Data-Studio-User` to record
the actor in annotation history.

Deployment notes are in [docs/deployment.md](docs/deployment.md).

The script starts FastAPI on `http://127.0.0.1:8000` and Next.js on
`http://127.0.0.1:3000` by default. Override `API_HOST`, `API_PORT`,
`WEB_HOST`, or `WEB_PORT` in `.env` or the shell.

## Current Implementation State

The repository has moved past a pure skeleton. The current MVP path can:

1. Open and index the `lance-format/lerobot-xvla-soft-fold` Lance dataset.
2. Serve dataset summaries, episode lists, episode details, state/action
   summaries, and MP4 blobs with HTTP Range support when available, including
   local files, HTTP(S), `hf://`, and optional `fsspec` path-backed video rows.
3. Serve frame-level samples through `GET /frames`, preferring `frames.lance`
   and falling back to episode time-series arrays with annotation labels and
   bad-frame flags, and show/edit selected-frame labels in the web metadata
   panel.
4. Store human and generated annotations as JSONL and mirror them to Lance when
   optional Lance dependencies are installed.
5. Generate Rerun `.rrd` cache files for state/action timeline inspection and
   load them through the Rerun React web viewer.
6. Run basic filter search through a typed builder with saved presets, plus
   full-text search and text-embedding semantic search with deterministic
   fallback, optional OpenAI-compatible embedding inference, and optional
   LanceDB vector table persistence/query when `lancedb` is installed.
7. Generate keyframe image embeddings through a visual embedding job with a
   deterministic fallback provider, optional Transformers CLIP/SigLIP/DINO-style
   model route, cached JPEG keyframes, and Lance-compatible embedding metadata.
8. Create VLM-style annotation proposals for review, including
   deterministic keyframe index sampling, versioned prompt tracking, and a
   provider interface with heuristic fallback, optional OpenAI-compatible model
   routing, optional local Ollama-compatible model routing,
   raw-response/keyframe artifact persistence, optional keyframe cache
   artifact publishing, and a generated-label review queue.
9. Export selected episodes as a LeRobot v3-oriented snapshot with metadata,
   frame JSONL, optional Parquet, available camera MP4 artifacts, validation,
   and version lineage, or as a Lance subset when optional `pyarrow` and
   `lance` dependencies are installed. Lightweight JSONL caption and VLA-style
   trajectory exports are also available. `format=hf_dataset` writes a
   frame-level Hugging Face `Dataset.save_to_disk()` artifact when optional
   export dependencies are installed. `publish_uri` can copy the finished export
   directory to a local or `fsspec` destination. The manual official-dependency workflow
   verifies native HF Dataset round-tripping plus no-video and video-backed
   LeRobot snapshots with the real official loaders. An opt-in real-dataset
   export smoke workflow also opens the default `xvla-soft-fold` `hf://` Lance
   URI and validates a one-episode exported subset with the official loader.
   Exports can target the selected episode or the current train/val/test split.
   Rerun, preview, and keyframe cache artifacts can also publish to local or
   `fsspec` destinations through cache publish environment variables.
10. Render the main web operations UI with dataset, episode, video viewer,
   annotation editing, search, Rerun, and export panels.

Known MVP gaps:

- VLM labeling defaults to heuristic/local scaffolding; OpenAI-compatible and
  local Ollama-compatible model inference are available only when configured
  with environment variables.
- Cross-modal text-to-image search requires configuring the text embedding
  provider and visual embedding worker with the same compatible CLIP/SigLIP
  model. A manual visual-model smoke workflow can run a real Transformers model
  through both providers when optional `.[ml]` dependencies are installed.
- LeRobot export writes frame JSONL, available MP4 artifacts, and optional
  Parquet shards. Per-frame video references stay in the JSONL readability copy;
  Parquet rows omit video feature columns so video resolution follows LeRobot
  episode metadata. When `lerobot` is installed, validation records the official
  loader result; GitHub's manual official-dependency workflow currently passes
  the tiny no-video and video-backed loader fixtures.
- Native Hugging Face Dataset export is frame-level and optional-dependency
  gated; large real-dataset training compatibility still needs dedicated
  end-to-end smoke runs with video materialization and larger subsets. The
  real-dataset smoke workflow can run in strict video mode with
  `require_videos=true` once the repository has an `HF_TOKEN` secret.
- Lance subset export requires optional `pyarrow` and `lance` dependencies and
  fails clearly when they are missing.

## MVP Scope

1. Open Lance LeRobot datasets.
2. List episodes and dataset summary.
3. Preview multi-camera video and state/action metadata.
4. Edit episode-level and segment-level annotations.
5. Store annotations in Lance-compatible tables.
6. Embed Rerun Web Viewer for deeper replay.
7. Run basic filters.
8. Export selected episodes.

See `docs/plan.md` for the current implementation plan and todo list.
