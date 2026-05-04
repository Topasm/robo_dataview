from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


class UnknownPromptTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    title: str
    description: str
    body: str
    expected_outputs: tuple[str, ...]


_PROMPT_METADATA = {
    "episode_autolabel_v1": {
        "filename": "episode_autolabel_v1.md",
        "version": "v1",
        "title": "Episode Auto-Label",
        "description": "Caption, phases, success/failure, objects, and keyframes.",
        "expected_outputs": (
            "episode_caption",
            "phase",
            "success_label",
            "object_list",
            "important_frame",
        ),
    },
}


def list_prompt_templates() -> list[PromptTemplate]:
    return [get_prompt_template(prompt_id) for prompt_id in sorted(_PROMPT_METADATA)]


def get_prompt_template(prompt_id: str) -> PromptTemplate:
    metadata = _PROMPT_METADATA.get(prompt_id)
    if metadata is None:
        raise UnknownPromptTemplateError(f"Unknown prompt template: {prompt_id}")
    body = files(__package__).joinpath(str(metadata["filename"])).read_text(encoding="utf-8")
    return PromptTemplate(
        prompt_id=prompt_id,
        version=str(metadata["version"]),
        title=str(metadata["title"]),
        description=str(metadata["description"]),
        body=body,
        expected_outputs=tuple(metadata["expected_outputs"]),
    )
