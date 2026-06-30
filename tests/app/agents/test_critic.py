from app.agents.blackboard import Blackboard
from app.agents.critic import CriticAgent
from app.agents.skills.base import SkillRegistry, BaseSkill
from app.services.llm_service import LLMService


class DummySkill(BaseSkill):
    def __init__(self):
        super().__init__("dummy_tool")

    def get_schema(self):
        return {"type": "function", "function": {"name": "dummy_tool", "parameters": {}}}

    def execute(self, **kwargs):
        return "工具调用结果"


class MockCriticLLM(LLMService):
    def __init__(self):
        super().__init__("stub", "test", "test")
        self.call_count = 0

    def generate_stream_with_tools_sync(self, messages, tools, max_tokens):
        self.call_count += 1
        if self.call_count == 1:
            yield {
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "dummy_tool", "arguments": "{}"},
                    }
                ]
            }
        else:
            yield "【通过】"


def test_critic_agent_with_tool_calling():
    llm = MockCriticLLM()
    registry = SkillRegistry()
    registry.register(DummySkill())

    critic = CriticAgent(llm, registry=registry)
    bb = Blackboard(
        novel_name="test",
        current_prompt="test",
        status="reviewing",
        outline="大纲",
        draft="草稿",
    )

    list(critic.run_stream(bb))

    assert bb.status == "done"
    assert "【通过】" in bb.critic_feedback
    assert llm.call_count == 2
