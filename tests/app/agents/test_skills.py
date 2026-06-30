from app.agents.skills.entity_skill import SearchEntitySkill
from app.agents.skills.worldview_skill import QueryWorldviewSkill


class MockMemoryService:
    def read_entity_profiles(self, novel_name):
        return {"测试实体": {"description": "这是一个实体", "current_status": "存活"}}

    def read_worldview(self, novel_name):
        return "这是测试世界观设定。"


def test_search_entity_skill():
    skill = SearchEntitySkill(MockMemoryService(), "test_novel")
    assert skill.name == "search_entity"

    schema = skill.get_schema()
    assert schema["function"]["name"] == "search_entity"

    result_found = skill.execute(name="测试实体")
    assert "测试实体" in result_found
    assert "这是一个实体" in result_found

    result_not_found = skill.execute(name="不存在")
    assert "未找到" in result_not_found


def test_query_worldview_skill():
    skill = QueryWorldviewSkill(MockMemoryService(), "test_novel")
    assert skill.name == "query_worldview"

    schema = skill.get_schema()
    assert schema["function"]["name"] == "query_worldview"

    result = skill.execute()
    assert "测试世界观设定" in result
