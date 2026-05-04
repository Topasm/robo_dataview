from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.api.schemas.annotations import AnnotationCreate
from apps.api.schemas.common import AnnotationSource, ReviewStatus
from apps.api.schemas.episodes import EpisodeDetail
from workers.keyframe_extractor import (
    KeyframeArtifact,
    extract_keyframes_from_blob,
    publish_keyframe_artifacts,
)
from workers.vlm_autolabel import AutoLabelConfig, build_vlm_annotation_proposals, select_keyframes

KEYFRAME_CACHE_ROOT = Path("data/cache/keyframes")
OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class VlmProviderResult:
    provider: str
    raw_response: dict[str, object]
    proposals: list[AnnotationCreate]


class VlmProvider(Protocol):
    name: str

    def propose(
        self,
        *,
        dataset_id: str,
        episode: EpisodeDetail,
        config: AutoLabelConfig,
        video_blobs: dict[str, bytes] | None = None,
    ) -> VlmProviderResult:
        ...


class HeuristicVlmProvider:
    name = "heuristic-fallback"

    def propose(
        self,
        *,
        dataset_id: str,
        episode: EpisodeDetail,
        config: AutoLabelConfig,
        video_blobs: dict[str, bytes] | None = None,
    ) -> VlmProviderResult:
        proposals = build_vlm_annotation_proposals(dataset_id, episode, config)
        keyframes = select_keyframes(
            max(1, episode.length or 1),
            min_keyframes=config.min_keyframes,
            max_keyframes=config.max_keyframes,
        )
        artifacts = _extract_keyframe_artifacts(
            dataset_id=dataset_id,
            episode=episode,
            config=config,
            keyframes=keyframes,
            video_blobs=video_blobs or {},
        )
        return VlmProviderResult(
            provider=self.name,
            raw_response={
                "provider": self.name,
                "model": config.model,
                "prompt_template": config.prompt_template,
                "prompt_version": config.prompt_version,
                "episode_index": episode.episode_index,
                "keyframes": keyframes,
                "keyframe_images": [_artifact_payload(artifact) for artifact in artifacts],
                "keyframe_image_count": len(artifacts),
                "proposal_count": len(proposals),
            },
            proposals=proposals,
        )


class OpenAICompatibleVlmProvider:
    name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("ROBOT_DATA_STUDIO_VLM_API_KEY")
        )
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("ROBOT_DATA_STUDIO_VLM_BASE_URL", OPENAI_COMPATIBLE_BASE_URL)
        ).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("ROBOT_DATA_STUDIO_VLM_TIMEOUT_SECONDS", "90"))
        )

    def propose(
        self,
        *,
        dataset_id: str,
        episode: EpisodeDetail,
        config: AutoLabelConfig,
        video_blobs: dict[str, bytes] | None = None,
    ) -> VlmProviderResult:
        keyframes = select_keyframes(
            max(1, episode.length or 1),
            min_keyframes=config.min_keyframes,
            max_keyframes=config.max_keyframes,
        )
        artifacts = _extract_keyframe_artifacts(
            dataset_id=dataset_id,
            episode=episode,
            config=config,
            keyframes=keyframes,
            video_blobs=video_blobs or {},
        )
        request_body = _openai_compatible_request_body(
            episode=episode,
            config=config,
            keyframes=keyframes,
            artifacts=artifacts,
        )
        raw_response: dict[str, object] = {
            "provider": self.name,
            "model": _provider_model(config.model),
            "prompt_template": config.prompt_template,
            "prompt_version": config.prompt_version,
            "episode_index": episode.episode_index,
            "keyframes": keyframes,
            "keyframe_images": [_artifact_payload(artifact) for artifact in artifacts],
            "keyframe_image_count": len(artifacts),
            "request": _redacted_request_payload(request_body),
        }

        if self._requires_api_key() and not self.api_key:
            raw_response["error"] = (
                "ROBOT_DATA_STUDIO_VLM_API_KEY is required for the default OpenAI endpoint."
            )
            return VlmProviderResult(provider=self.name, raw_response=raw_response, proposals=[])

        try:
            response_payload = self._post_json(request_body)
            parsed_output = _parse_openai_compatible_output(response_payload)
            proposals = _annotation_proposals_from_model_output(
                dataset_id=dataset_id,
                episode=episode,
                config=config,
                output=parsed_output,
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raw_response["error"] = str(exc)
            return VlmProviderResult(provider=self.name, raw_response=raw_response, proposals=[])

        raw_response["response"] = response_payload
        raw_response["parsed_output"] = parsed_output
        raw_response["proposal_count"] = len(proposals)
        return VlmProviderResult(provider=self.name, raw_response=raw_response, proposals=proposals)

    def _requires_api_key(self) -> bool:
        return self.base_url == OPENAI_COMPATIBLE_BASE_URL

    def _post_json(self, body: dict[str, object]) -> dict[str, object]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class OllamaVlmProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv(
                "ROBOT_DATA_STUDIO_OLLAMA_BASE_URL",
                os.getenv("ROBOT_DATA_STUDIO_VLM_BASE_URL", OLLAMA_BASE_URL),
            )
        ).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("ROBOT_DATA_STUDIO_VLM_TIMEOUT_SECONDS", "180"))
        )

    def propose(
        self,
        *,
        dataset_id: str,
        episode: EpisodeDetail,
        config: AutoLabelConfig,
        video_blobs: dict[str, bytes] | None = None,
    ) -> VlmProviderResult:
        keyframes = select_keyframes(
            max(1, episode.length or 1),
            min_keyframes=config.min_keyframes,
            max_keyframes=config.max_keyframes,
        )
        artifacts = _extract_keyframe_artifacts(
            dataset_id=dataset_id,
            episode=episode,
            config=config,
            keyframes=keyframes,
            video_blobs=video_blobs or {},
        )
        request_body = _ollama_request_body(
            episode=episode,
            config=config,
            keyframes=keyframes,
            artifacts=artifacts,
        )
        raw_response: dict[str, object] = {
            "provider": self.name,
            "model": _provider_model(config.model),
            "prompt_template": config.prompt_template,
            "prompt_version": config.prompt_version,
            "episode_index": episode.episode_index,
            "keyframes": keyframes,
            "keyframe_images": [_artifact_payload(artifact) for artifact in artifacts],
            "keyframe_image_count": len(artifacts),
            "request": _redacted_ollama_request_payload(request_body),
        }

        try:
            response_payload = self._post_json(request_body)
            parsed_output = _parse_ollama_output(response_payload)
            proposals = _annotation_proposals_from_model_output(
                dataset_id=dataset_id,
                episode=episode,
                config=config,
                output=parsed_output,
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raw_response["error"] = str(exc)
            return VlmProviderResult(provider=self.name, raw_response=raw_response, proposals=[])

        raw_response["response"] = response_payload
        raw_response["parsed_output"] = parsed_output
        raw_response["proposal_count"] = len(proposals)
        return VlmProviderResult(provider=self.name, raw_response=raw_response, proposals=proposals)

    def _post_json(self, body: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def get_vlm_provider(model: str) -> VlmProvider:
    provider_name = os.getenv("ROBOT_DATA_STUDIO_VLM_PROVIDER", "").lower()
    model_name = model.lower()
    if provider_name == "ollama" or model_name.startswith("ollama:"):
        return OllamaVlmProvider()
    if (
        provider_name in {"openai", "openai-compatible"}
        or model_name.startswith("openai:")
        or model_name.startswith("openai-compatible:")
    ):
        return OpenAICompatibleVlmProvider()
    return HeuristicVlmProvider()


def _extract_keyframe_artifacts(
    *,
    dataset_id: str,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
    keyframes: list[int],
    video_blobs: dict[str, bytes],
) -> list[KeyframeArtifact]:
    if not video_blobs or not keyframes:
        return []

    output_dir = (
        KEYFRAME_CACHE_ROOT
        / _dataset_cache_dir(dataset_id)
        / f"episode_{episode.episode_index:06d}"
        / f"{config.prompt_template}_{config.prompt_version}"
    )
    artifacts: list[KeyframeArtifact] = []
    for camera, blob in sorted(video_blobs.items()):
        artifacts.extend(
            extract_keyframes_from_blob(
                blob=blob,
                camera=camera,
                frame_indices=keyframes,
                output_dir=output_dir,
            )
        )
    return publish_keyframe_artifacts(artifacts)


def _artifact_payload(artifact: KeyframeArtifact) -> dict[str, object]:
    return {
        "camera": artifact.camera,
        "frame_index": artifact.frame_index,
        "uri": artifact.uri,
        "width": artifact.width,
        "height": artifact.height,
        "content_type": artifact.content_type,
        "published_uri": artifact.published_uri,
        "publish_size_bytes": artifact.publish_size_bytes,
        "publish_error": artifact.publish_error,
    }


def _ollama_request_body(
    *,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
    keyframes: list[int],
    artifacts: list[KeyframeArtifact],
) -> dict[str, object]:
    images = [
        encoded
        for artifact in artifacts[: config.max_keyframes]
        if (encoded := _artifact_base64(artifact)) is not None
    ]
    user_message: dict[str, object] = {
        "role": "user",
        "content": _vlm_user_prompt(episode=episode, config=config, keyframes=keyframes),
    }
    if images:
        user_message["images"] = images
    return {
        "model": _provider_model(config.model),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You label robot learning episodes for dataset curation. "
                    "Return only valid JSON matching the requested schema."
                ),
            },
            user_message,
        ],
    }


def _openai_compatible_request_body(
    *,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
    keyframes: list[int],
    artifacts: list[KeyframeArtifact],
) -> dict[str, object]:
    content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": _vlm_user_prompt(episode=episode, config=config, keyframes=keyframes),
        }
    ]
    for artifact in artifacts[: config.max_keyframes]:
        data_url = _artifact_data_url(artifact)
        if data_url is None:
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": data_url,
                    "detail": "low",
                },
            }
        )
    return {
        "model": _provider_model(config.model),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You label robot learning episodes for dataset curation. "
                    "Return only valid JSON matching the requested schema."
                ),
            },
            {
                "role": "user",
                "content": content,
            },
        ],
    }


def _vlm_user_prompt(
    *,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
    keyframes: list[int],
) -> str:
    prompt_body = config.prompt_body or (
        "Return an episode caption, ordered phases, success/failure, objects, and important frames."
    )
    return "\n".join(
        [
            prompt_body,
            "",
            "Episode metadata:",
            f"- episode_index: {episode.episode_index}",
            f"- task_index: {episode.task_index}",
            f"- frame_count: {episode.length}",
            f"- fps: {episode.fps}",
            f"- cameras: {', '.join(episode.camera_names) if episode.camera_names else 'none'}",
            f"- existing_caption: {episode.caption or ''}",
            f"- language_instruction: {episode.language_instruction or ''}",
            f"- sampled_keyframes: {keyframes}",
            "",
            "Return JSON with these keys:",
            "- episode_caption: string or {text, confidence}",
            "- success_label: success | failure | unknown, or {value, confidence}",
            "- failure_reason: optional string or {text, confidence}",
            "- object_list: string or list[str]",
            "- phases: list of {label, start_frame, end_frame, confidence}",
            "- important_frames: list of frame indices or {frame_index, label, confidence}",
        ]
    )


def _artifact_data_url(artifact: KeyframeArtifact) -> str | None:
    encoded = _artifact_base64(artifact)
    if encoded is None:
        return None
    return f"data:{artifact.content_type};base64,{encoded}"


def _artifact_base64(artifact: KeyframeArtifact) -> str | None:
    path = Path(artifact.uri)
    if not path.exists() or not path.is_file():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _redacted_request_payload(body: dict[str, object]) -> dict[str, object]:
    redacted = json.loads(json.dumps(body))
    for message in redacted.get("messages", []):
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "image_url":
                continue
            image_url = item.get("image_url")
            if isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
                image_url["url"] = "[image-data-url]"
    return redacted


def _redacted_ollama_request_payload(body: dict[str, object]) -> dict[str, object]:
    redacted = json.loads(json.dumps(body))
    for message in redacted.get("messages", []):
        if not isinstance(message, dict) or "images" not in message:
            continue
        images = message.get("images")
        if isinstance(images, list):
            message["images"] = ["[image-base64]" for _ in images]
    return redacted


def _parse_openai_compatible_output(response_payload: dict[str, object]) -> dict[str, object]:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return _load_json_from_text(content)
                if isinstance(content, dict):
                    return content
                if isinstance(content, list):
                    text = " ".join(
                        str(item.get("text", ""))
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    )
                    return _load_json_from_text(text)
    return response_payload


def _parse_ollama_output(response_payload: dict[str, object]) -> dict[str, object]:
    message = response_payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return _load_json_from_text(content)
        if isinstance(content, dict):
            return content
    response_text = response_payload.get("response")
    if isinstance(response_text, str):
        return _load_json_from_text(response_text)
    return response_payload


def _load_json_from_text(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    parsed = json.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _annotation_proposals_from_model_output(
    *,
    dataset_id: str,
    episode: EpisodeDetail,
    config: AutoLabelConfig,
    output: dict[str, object],
) -> list[AnnotationCreate]:
    frame_count = max(1, episode.length or 1)
    last_frame = frame_count - 1
    base = {
        "dataset_id": dataset_id,
        "episode_index": episode.episode_index,
        "source": AnnotationSource.vlm,
        "review_status": ReviewStatus.pending,
        "created_by": f"vlm:{config.model}",
    }
    proposals: list[AnnotationCreate] = []

    caption_text, caption_confidence = _text_and_confidence(output.get("episode_caption"))
    if caption_text:
        proposals.append(
            AnnotationCreate(
                **base,
                start_frame=0,
                end_frame=last_frame,
                label_type="episode_caption",
                label_value=caption_text,
                confidence=caption_confidence,
            )
        )

    success_text, success_confidence = _text_and_confidence(output.get("success_label"))
    if success_text:
        proposals.append(
            AnnotationCreate(
                **base,
                start_frame=0,
                end_frame=last_frame,
                label_type="success_label",
                label_value=success_text,
                confidence=success_confidence,
            )
        )

    failure_text, failure_confidence = _text_and_confidence(output.get("failure_reason"))
    if failure_text:
        proposals.append(
            AnnotationCreate(
                **base,
                start_frame=0,
                end_frame=last_frame,
                label_type="failure_reason",
                label_value=failure_text,
                confidence=failure_confidence,
            )
        )

    object_text, object_confidence = _objects_and_confidence(output.get("object_list"))
    if object_text:
        proposals.append(
            AnnotationCreate(
                **base,
                start_frame=0,
                end_frame=last_frame,
                label_type="object_list",
                label_value=object_text,
                confidence=object_confidence,
            )
        )

    phases = output.get("phases")
    if isinstance(phases, list):
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            label = str(phase.get("label") or phase.get("phase") or phase.get("name") or "").strip()
            if not label:
                continue
            start_frame = _bounded_frame(phase.get("start_frame"), last_frame)
            end_frame = _bounded_frame(phase.get("end_frame"), last_frame)
            if end_frame < start_frame:
                start_frame, end_frame = end_frame, start_frame
            proposals.append(
                AnnotationCreate(
                    **base,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    label_type="phase",
                    label_value=label,
                    confidence=_confidence(phase.get("confidence")),
                )
            )

    important_frames = output.get("important_frames")
    if isinstance(important_frames, list):
        for item in important_frames:
            frame_index = item.get("frame_index") if isinstance(item, dict) else item
            frame = _bounded_frame(frame_index, last_frame)
            label = (
                str(
                    item.get("label") or item.get("reason") or f"important_frame_{frame:06d}"
                ).strip()
                if isinstance(item, dict)
                else f"important_frame_{frame:06d}"
            )
            proposals.append(
                AnnotationCreate(
                    **base,
                    start_frame=frame,
                    end_frame=frame,
                    label_type="important_frame",
                    label_value=label,
                    confidence=_confidence(item.get("confidence") if isinstance(item, dict) else None),
                )
            )

    return proposals


def _text_and_confidence(value: object) -> tuple[str | None, float]:
    if value is None:
        return None, 0.5
    if isinstance(value, dict):
        text = value.get("text", value.get("value", value.get("label")))
        return _clean_text(text), _confidence(value.get("confidence"))
    return _clean_text(value), 0.5


def _objects_and_confidence(value: object) -> tuple[str | None, float]:
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
        return (text or None), 0.5
    return _text_and_confidence(value)


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _bounded_frame(value: object, last_frame: int) -> int:
    try:
        frame = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(last_frame, frame))


def _provider_model(model: str) -> str:
    for prefix in ("openai-compatible:", "openai:", "ollama:"):
        if model.lower().startswith(prefix):
            return model[len(prefix) :]
    return model


def _dataset_cache_dir(dataset_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_id).strip("._-")
    digest = hashlib.sha1(dataset_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:80] or 'dataset'}-{digest}"
