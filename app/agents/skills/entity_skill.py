from app.agents.skills.base import BaseSkill
from app.services.memory_service import MemoryService


class SearchEntitySkill(BaseSkill):
    def __init__(self, memory_service: MemoryService, novel_name: str):
        super().__init__(name="search_entity")
        self.memory_service = memory_service
        self.novel_name = novel_name

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "查阅特定实体（人物角色、地点、组织、物品、功法等）的详细设定档案。当你审查时遇到任何拿不准设定的专有名词，请务必调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "实体名称，例如 '林峰' 或 '青云门'",
                        }
                    },
                    "required": ["name"],
                },
            },
        }

    def execute(self, **kwargs) -> str:
        name = kwargs.get("name", "")
        profiles = self.memory_service.read_entity_profiles(self.novel_name)
        if name in profiles:
            p = profiles[name]
            return f"【{name}】描述：{p.get('description', '')}，当前状态：{p.get('current_status', '')}"
        else:
            return f"未找到名为【{name}】的实体档案。"
