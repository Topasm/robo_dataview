"""VLM auto-labeling worker utilities.

This module intentionally separates proposal generation from persistence. The
API can call it synchronously for the local MVP, and a future RQ/Celery worker
can call the same function asynchronously.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail


@dataclass(frozen=True)
class AutoLabelConfig:
    model: str
    prompt_template: str


def build_vlm_annotation_proposals(
    dataset_id: str,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
) -> list[AnnotationCreate]:
    """Generate pending annotation proposals for one episode.

    The default implementation is a deterministic fallback that mirrors the
    target VLM output contract. Real VLM inference can replace this function's
    internals while keeping the same persisted annotation schema.
    """

    frame_count = max(1, episode.length or 1)
    last_frame = frame_count - 1
    phase_ranges = _phase_ranges(frame_count)
    caption = episode.caption or episode.language_instruction or f"Episode {episode.episode_index}"
    success_value = (
        "success"
        if episode.success_label is True
        else "failure"
        if episode.success_label is False
        else "unknown"
    )
    base = {
        "dataset_id": dataset_id,
        "episode_index": episode.episode_index,
        "source": AnnotationSource.vlm,
        "review_status": ReviewStatus.pending,
        "created_by": f"vlm:{config.model}",
    }

    proposals = [
        AnnotationCreate(
            **base,
            start_frame=0,
            end_frame=last_frame,
            label_type="episode_caption",
            label_value=f"{caption} [proposal:{config.prompt_template}]",
            confidence=0.55,
        ),
        AnnotationCreate(
            **base,
            start_frame=0,
            end_frame=last_frame,
            label_type="success_label",
            label_value=success_value,
            confidence=0.5 if success_value == "unknown" else 0.72,
        ),
        AnnotationCreate(
            **base,
            start_frame=0,
            end_frame=last_frame,
            label_type="object_list",
            label_value="manipulated_object, robot_gripper, workspace",
            confidence=0.42,
        ),
    ]

    for label, start_frame, end_frame in phase_ranges:
        proposals.append(
            AnnotationCreate(
                **base,
                start_frame=start_frame,
                end_frame=end_frame,
                label_type="phase",
                label_value=label,
                confidence=0.48,
            )
        )

    for frame in sorted({0, frame_count // 2, last_frame}):
        proposals.append(
            AnnotationCreate(
                **base,
                start_frame=frame,
                end_frame=frame,
                label_type="important_frame",
                label_value=f"keyframe_{frame}",
                confidence=0.46,
            )
        )

    return proposals


def _phase_ranges(frame_count: int) -> list[tuple[str, int, int]]:
    last_frame = max(0, frame_count - 1)
    if frame_count <= 3:
        return [("episode_phase", 0, last_frame)]

    first_end = max(0, frame_count // 3 - 1)
    second_end = max(first_end + 1, (frame_count * 2) // 3 - 1)
    return [
        ("approach", 0, first_end),
        ("manipulation", first_end + 1, min(second_end, last_frame)),
        ("completion", min(second_end + 1, last_frame), last_frame),
    ]


def main() -> None:
    raise SystemExit("Run VLM auto-labeling through POST /api/jobs/vlm-label.")


if __name__ == "__main__":
    main()
