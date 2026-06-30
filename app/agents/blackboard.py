from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Blackboard(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    novel_name: str
    current_prompt: str
    outline: str = ""
    draft: str = ""
    critic_feedback: str = ""
    status: Literal["planning", "drafting", "reviewing", "done"] = "planning"
    chief_directive: str = ""

    worldview: str = ""
    timeline: str = ""
    recent_summary: str = ""
    recent_3_raw: str = ""
    style_guidelines: str = ""
    entity_profiles_text: str = ""

    @model_validator(mode="before")
    @classmethod
    def _map_prompt_kwarg(cls, data: Any) -> Any:
        """Tests construct with ``prompt=``; model field is ``current_prompt``."""
        if isinstance(data, dict):
            d = dict(data)
            if "prompt" in d and "current_prompt" not in d:
                d["current_prompt"] = d.pop("prompt")
            return d
        return data

    def update(self, **kwargs) -> None:
        allowed = type(self).model_fields.keys()
        for key, value in kwargs.items():
            if key in allowed:
                setattr(self, key, value)
