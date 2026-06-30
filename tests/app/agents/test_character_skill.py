import pytest
import os
from app.agents.skills import SearchEntitySkill
from app.services.memory_service import MemoryService


def test_search_entity_skill_schema():
    memory_service = MemoryService("dummy")
    skill = SearchEntitySkill(memory_service, "test_novel")
    schema = skill.get_schema()
    assert schema["function"]["name"] == "search_entity"


def test_search_entity_skill_execute(tmp_path):
    os.makedirs(tmp_path / "test_novel" / "memory")
    with open(tmp_path / "test_novel" / "memory" / "entity_profiles.json", "w", encoding="utf-8") as f:
        f.write('{"Alice": {"description": "一个勇敢的骑士。", "current_status": "存活"}}')

    memory_service = MemoryService(tmp_path)
    skill = SearchEntitySkill(memory_service, "test_novel")

    result = skill.execute(name="Alice")
    assert "勇敢的骑士" in result

    result_missing = skill.execute(name="Bob")
    assert "未找到" in result_missing
