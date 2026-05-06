#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.api.schemas.datasets import DatasetOpenRequest
from apps.api.services.lance_store import LanceDatasetStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open robot datasets and run compatibility checks for summary, episodes, frames, videos, and timeseries."
    )
    parser.add_argument("uris", nargs="+", help="Local path, hf:// URI, or Lance table URI")
    parser.add_argument("--name-prefix", default="compat", help="Dataset name prefix")
    parser.add_argument("--episode-limit", type=int, default=3, help="Episodes to inspect per dataset")
    parser.add_argument("--require-video", action="store_true", help="Fail when no camera has readable video bytes/source")
    parser.add_argument(
        "--health-level",
        choices=("shallow", "deep"),
        default="deep",
        help="Dataset health depth. Smoke tests use deep by default; the web UI uses shallow.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    results = [
        check_dataset(
            uri,
            name=f"{args.name_prefix}-{idx}",
            episode_limit=args.episode_limit,
            require_video=args.require_video,
            health_level=args.health_level,
        )
        for idx, uri in enumerate(args.uris)
    ]
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for result in results:
            status = "OK" if result["ok"] else "FAIL"
            print(f"[{status}] {result['uri']}")
            print(f"  episodes={result.get('episode_count')} frames={result.get('frame_count')} cameras={result.get('camera_names')}")
            for warning in result["warnings"]:
                print(f"  warning: {warning}")
            for error in result["errors"]:
                print(f"  error: {error}")
    return 0 if all(result["ok"] for result in results) else 1


def check_dataset(
    uri: str,
    *,
    name: str,
    episode_limit: int,
    require_video: bool,
    health_level: str,
) -> dict[str, Any]:
    store = LanceDatasetStore()
    result: dict[str, Any] = {
        "uri": uri,
        "ok": False,
        "warnings": [],
        "errors": [],
    }
    try:
        record = store.open_dataset(DatasetOpenRequest(uri=uri, name=name))
        result["dataset_id"] = record.dataset_id
        result["status"] = record.status
        if record.status != "indexed":
            result["errors"].append(record.message or "dataset did not index")
            return result

        summary = store.get_summary(record.dataset_id)
        if summary is None:
            result["errors"].append("missing dataset summary")
            return result
        health = store.get_health(record.dataset_id, level=health_level)
        if health is not None:
            result["health"] = health.model_dump()
            result["warnings"].extend(health.warnings)
            result["errors"].extend(health.errors)
        result.update(
            {
                "episode_count": summary.episode_count,
                "frame_count": summary.frame_count,
                "camera_names": summary.camera_names,
            }
        )
        if summary.episode_count <= 0:
            result["errors"].append("no episodes")

        page = store.list_episode_page(record.dataset_id, limit=episode_limit, offset=0)
        if not page.items:
            result["errors"].append("episode page is empty")
            return result

        video_sources = 0
        for item in page.items:
            episode = store.get_episode(record.dataset_id, item.episode_index)
            if episode is None:
                result["errors"].append(f"episode {item.episode_index} detail missing")
                continue
            timeseries = store.get_episode_timeseries(record.dataset_id, item.episode_index)
            if timeseries is None or _timeseries_frame_count(timeseries) <= 0:
                result["warnings"].append(f"episode {item.episode_index} has no state/action timeseries")
            frames = store.list_frames(record.dataset_id, item.episode_index, limit=10)
            if not frames:
                result["warnings"].append(f"episode {item.episode_index} has no frame rows or derived frames")
            for camera in episode.camera_names:
                source = store.get_video_source(record.dataset_id, item.episode_index, camera)
                if source is not None and source.size > 0:
                    video_sources += 1
        result["video_sources_checked"] = video_sources
        if require_video and video_sources == 0:
            result["errors"].append("no readable video sources found")
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")

    result["ok"] = not result["errors"]
    return result


def _timeseries_frame_count(timeseries: dict[str, Any]) -> int:
    return max(
        _safe_len(timeseries.get("timestamps")),
        _safe_len(timeseries.get("states")),
        _safe_len(timeseries.get("actions")),
    )


def _safe_len(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
