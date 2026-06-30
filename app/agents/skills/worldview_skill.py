from app.agents.skills.base import BaseSkill
from app.services.memory_service import MemoryService


class QueryWorldviewSkill(BaseSkill):
    def __init__(self, memory_service: MemoryService, novel_name: str):
        super().__init__(name="query_worldview")
        self.memory_service = memory_service
        self.novel_name = novel_name

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "获取当前小说的全局世界观、背景设定、力量体系等基础法则。如果对设定的基本逻辑有疑问，请调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    def execute(self, **kwargs) -> str:
        worldview = self.memory_service.read_worldview(self.novel_name)
        if worldview:
            return f"【全局世界观设定】：\n{worldview}"
        else:
            return "当前小说暂无世界观设定。"
