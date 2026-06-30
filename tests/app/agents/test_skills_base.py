import pytest
from app.agents.skills.base import BaseSkill, SkillRegistry


class DummySkill(BaseSkill):
    def __init__(self):
        super().__init__(name="dummy_tool")

    def get_schema(self) -> dict:
        return {"name": "dummy_tool", "description": "dummy"}

    def execute(self, **kwargs) -> str:
        return "dummy result"


def test_skill_registry():
    registry = SkillRegistry()
    skill = DummySkill()
    registry.register(skill)

    schemas = registry.get_all_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "dummy_tool"

    result = registry.execute("dummy_tool", {})
    assert result == "dummy result"

    # 未注册的 tool
    missing = registry.execute("unknown", {})
    assert "未知的技能名" in missing
