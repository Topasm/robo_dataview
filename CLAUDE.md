# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo Shape

Monorepo for **Robot Data Studio**, a web tool for curating Lance-native LeRobot datasets:

- `apps/api` — FastAPI backend (`apps.api.main:app`). Routers under `routers/`, business logic under `services/`, Pydantic models under `schemas/`.
- `apps/web` — Next.js 15 / React 19 / TypeScript app router frontend. Feature-sliced under `features/`, shared API client and orchestration in `lib/` (notably `lib/use-studio-data.ts`, which page.tsx delegates to).
- `workers/` — Python worker functions (VLM auto-label, visual embedding, Rerun cache, keyframe extractor). Same code runs inline in the API process or as RQ jobs.
- `packages/robot_schema` — PyArrow schema builders for the optional Lance mirror tables (`annotations.lance`, `embeddings.lance`, `versions.lance`, `episode_labels.lance`).
- `packages/prompts` — Versioned VLM prompt templates (`*.md`), loaded by name via the prompt registry.
- `data/` — Local artifacts: `data/lance/` (datasets), `data/cache/` (keyframes, Rerun .rrd), `data/exports/`, `data/app/metadata.sqlite3` (job metadata).
- `docs/` — `architecture.md`, `api_spec.md`, `schema.md`, `plan.md`, `roadmap.md`, `deployment.md`, `ui_wireframe.md`. `plan.md` is the live todo list.

## Common Commands

```bash
npm run dev                                       # API (uvicorn) + web (next) together via scripts/dev.sh
npm run dev:api                                   # API only (uvicorn --reload, port 8000)
npm run dev:web                                   # Next.js only (port 3000)

python3 -m pytest -q                              # all Python tests (pytest config in pyproject.toml; testpaths = apps/api/tests)
python3 -m pytest apps/api/tests/test_export_service.py -q                # one file
python3 -m pytest apps/api/tests/test_export_service.py::test_name -q     # one test

npm --workspace apps/web run lint                 # eslint
npm --workspace apps/web run typecheck            # next typegen + tsc --noEmit
npm --workspace apps/web run build                # next build
python3 -m compileall -q apps packages workers    # quick syntax check
```

Full validation gate before declaring a milestone done is enumerated in `docs/plan.md` "Validation Checklist".

## Environment Setup

The repo deliberately does **not** create or mutate `.venv` for you. Activate one yourself, then `pip install -e ".[dev]"`. The Python package surface is split into many optional extras (`lance`, `rerun`, `lerobot`, `export`, `queue`, `video`, `storage`, `convert`, `ml`) — install only what the feature you're touching needs. The `convert` extra pulls in the standalone [`lerobot2lance`](https://github.com/Topasm/lerobot2lance) package, which powers `POST /datasets/convert-lerobot`. Code paths that depend on extras must degrade gracefully when imports are missing (see existing `try/except ImportError` patterns in `services/lance_store.py`, `services/lance_export.py`, and `routers/datasets.py` for the lerobot2lance hook).

Copy `.env.example` to `.env`. Key vars: `NEXT_PUBLIC_API_BASE_URL`, `ROBOT_DATA_STUDIO_API_KEY` (optional auth), `ROBOT_DATA_STUDIO_JOB_QUEUE=rq` + `ROBOT_DATA_STUDIO_REDIS_URL` (switches from inline to RQ job execution), and the various `*_PROVIDER` / `*_BASE_URL` knobs for VLM and embedding providers.

## Architectural Invariants

These shape almost every change — read `docs/architecture.md` for the long form.

1. **Lance is the durable source of truth.** Raw frames, episodes, videos live in Lance. Curated artifacts (annotations, embeddings, versions, episode labels) are stored as **JSONL under `data/`** as the mandatory local fallback, with **optional Lance mirroring** when `pyarrow`/`lance` are installed. New persistence must follow this dual-write pattern — see `services/annotation_service.py` and `services/lance_store.py`.

2. **Rerun is a viewer, not a store.** `.rrd` files are regenerable cache artifacts under `data/cache/rerun/`, keyed by dataset fingerprint + episode + mode + viz config. Never store annotation truth in Rerun.

3. **VLM output is a proposal, never authoritative.** Generated annotations are written with `source = "vlm"` and `review_status = "pending"` and surface in the review queue until a human accepts them. The provider layer (`workers/vlm_provider.py`) routes between heuristic fallback / OpenAI-compatible / Ollama — always keep the heuristic fallback path working so tests don't need network.

4. **Jobs run inline by default, RQ when configured.** `services/job_queue.py` dispatches the same worker function either synchronously (dev) or via Redis/RQ (when `ROBOT_DATA_STUDIO_JOB_QUEUE=rq`). Worker functions in `workers/` must be importable and side-effect-free at import time. Job progress is streamed to the web via SSE at `GET /api/jobs/{job_id}/events`; metadata persists in `data/app/metadata.sqlite3`.

5. **LeRobot v3 export is a hard contract.** `services/export_service.py` + `services/lerobot_io.py` + `services/lance_export.py` produce LeRobot-compatible snapshots (manifest, frame JSONL, optional Parquet, MP4 artifacts with SHA256 indexes). When `lerobot` is installed, validation runs the official loader. Don't break the manual `.github/workflows/official-export.yml` and `real-dataset-export-smoke.yml` contracts when touching export code.

## API Layout

`apps/api/main.py` mounts ten routers under `/api`: `datasets`, `episodes`, `frames`, `annotations`, `search`, `rerun`, `jobs`, `exports`, `versions`, `users`. Each has a parallel `schemas/<name>.py` (Pydantic) and is thin — heavy logic lives in `services/`. Auth middleware (`services/auth.py`) enforces `X-Robot-Data-Studio-API-Key` only when `ROBOT_DATA_STUDIO_API_KEY` is set; review actor identity comes from `X-Robot-Data-Studio-User` (defaults to `local`).

CORS is locked to `localhost:3000` / `127.0.0.1:30xx` — adjust in `main.py` if you change web ports.

## Web Orchestration

`apps/web/lib/use-studio-data.ts` is the central hook for fetching/mutating studio state — it owns the optimistic-UI patterns and SSE streaming for VLM/export/Rerun jobs. `lib/api.ts` is the typed fetch layer; `lib/types.ts` mirrors API schemas. Feature panels under `features/` consume the hook rather than calling the API directly. Sample fixtures in `lib/sample-data.ts` keep the UI bootable before a dataset is opened.

### Page structure (2 tabs)

`apps/web/app/page.tsx` is a thin shell — header (Browse/Annotate tabs + Export button + cheatsheet) and a banner — that mounts one of two workspaces:

- `features/browse-mode/browse-mode.tsx` — triage: `DatasetBrowser` + `EpisodeList` sidebar | `EpisodeViewer initialLayout="stack"` (cam_head on top + wrist row beneath) + `EpisodeCharts` (recharts state/action lines with skill-clip `ReferenceArea` overlays + click/hover-to-seek) + `EpisodeActionBar` (Keep/Delete/Flag + "Annotate this episode →"). Disposition is soft-only (`label_type=episode_disposition` annotation; `episodes.lance` never mutated).
- `features/annotation-mode/annotation-mode.tsx` — NLE-style cutter: `IconRail` | (annotation header + `EpisodeViewer` preview + `SkillHotBar` 0–9 + `StatusHud` + `EpisodeCharts` (compact) + `TimelinePanel` + `ShortcutChip`) | `AnnotationEditor` (3-tab inspector: Clip / Frame / Coverage). `AutoLabelDialog`, `CheatsheetModal`, and Apply-Last confirm are mounted here.

### Keymap split

Two hooks own the keyboard contract:

- `lib/use-browse-shortcuts.ts` — Browse: `Space ←/→ ↑/↓ K/X/F Enter` (disposition + open-in-Annotate).
- `lib/use-annotate-shortcuts.ts` — Annotate: `I/O` (in/out markers), `1–9` (select skill **and** in one stroke create+accept the I→O clip; if a pending VLM clip is selected instead, reassign skill + accept), `0` (cancel draft), `Backspace` (delete selected clip). `M/B` (bad-frame, bad-range) are opt-in via `useAnnotationEditor.enableBadFrameShortcuts` (persisted to localStorage; toggled in the cheatsheet footer). `?` toggles the cheatsheet, `Esc` closes modals — both live at the page level.

### Skill vocabulary contract (do not break)

The 10 canonical skills are the source of truth across the whole pipeline (`packages/robot_schema/humanoid_skills.json` → `apps/web/lib/skill-vocabulary.ts`). The same string is used as DataView `label_value`, `train_skill_clips.lance` `skill_name`, Skill Registry key, Robot CLI command, and the per-skill checkpoint directory. New skills must be added everywhere or nowhere. Each skill carries a stable color used by the timeline lane, skill hot bar, status HUD, episode chart `ReferenceArea` band, and inspector chip — all reads go through `skillByName`/`skillById`.

### Design tokens & component conventions

`apps/web/app/globals.css` defines the design system at the top of `:root` — spacing (`--space-1..6`), radius (`--radius-sm/md/lg/pill`), font sizes (`--text-xs..xl`), surfaces (`--bg`, `--surface`, `--surface-2`, `--surface-3`, `--video-bg`), state tints (`--accent`, `--accent-2`, `--warning`, `--danger`, plus `*-soft` and `*-soft-border` siblings via `color-mix`), shadows, and `--scrim`. Prefer these over hard-coded values in new CSS.

Buttons use a small system: `.btn` baseline + `.btn--primary | --ghost | --danger | --warning`, plus size/shape modifiers `.btn--sm | --icon | --pill`. Modals use `.modal-overlay` + `.modal-panel` with `.modal-header / .modal-body / .modal-footer` (and a `.modal-panel--cheatsheet` / `.export-modal-panel` width modifier). Specialized variants (`.icon-rail-button`, `.skill-chip`) are kept where they have unique requirements (badge positioning, dynamic `--skill-color`).

### Charts (lazy)

`features/browse-mode/episode-charts.tsx` renders state/action timeseries via `recharts` with playhead `ReferenceLine`, accepted skill clips as colored `ReferenceArea` bands, and click/hover-to-seek. The component is wrapped in `episode-charts-async.tsx` via `next/dynamic({ssr: false})` so the ~110 KB recharts chunk only ships when the user actually opens Browse or Annotate.

### Sidebar / scroll invariants

`.studio-shell` is `height: 100vh; overflow: hidden;` and grids the workspace into a tight column. `.left-panel`, `.right-panel`, and `.episode-table-wrap` use `overflow-y: auto; overflow-x: hidden;` — a horizontal scrollbar in a sidebar is always a layout bug. Episode rows shrink down to a 4-column subset (Episode / Task / Frames / Status) below 1024 px so they fit narrow rails.

## Testing Notes

- Pytest discovers from `apps/api/tests`; `pythonpath = ["."]` lets tests import `apps.api.*` and `workers.*` directly.
- Tests for optional-dependency code paths (Lance, lerobot, transformers) typically `pytest.importorskip(...)` so they no-op without the extra installed.
- Several "smoke" workflows in `.github/workflows/` (`official-export.yml`, `visual-model-smoke.yml`, `real-dataset-export-smoke.yml`, `artifact-publish-smoke.yml`) are manual / opt-in — the local `pytest -q` run does not cover them.
- The web app has no test runner configured; `lint`, `typecheck`, and `build` are the gates.
