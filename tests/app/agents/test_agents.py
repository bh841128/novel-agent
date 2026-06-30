from app.agents.blackboard import Blackboard
from app.agents.critic import CRITIC_SYSTEM, CriticAgent
from app.agents.planner import PlannerAgent
from app.agents.writer import WriterAgent
from app.services.llm_service import LLMService


class MockLLM(LLMService):
    def __init__(self):
        super().__init__("stub", "test", "test")

    def generate_sync(self, messages, max_tokens=4096):
        return "模拟的回复"

    def generate_stream_sync(self, messages, max_tokens=4096):
        yield "模拟的流式回复"


def test_agents_with_blackboard():
    bb = Blackboard(novel_name="test", current_prompt="测试提示词")
    llm = MockLLM()

    planner = PlannerAgent(llm)
    list(planner.run_stream(bb))
    assert bb.outline == "模拟的流式回复"
    assert bb.status == "drafting"

    writer = WriterAgent(llm)
    list(writer.write_stream(bb))
    assert bb.draft == "模拟的流式回复"
    assert bb.status == "reviewing"

    critic = CriticAgent(llm)
    list(critic.run_stream(bb))
    assert bb.critic_feedback == "模拟的流式回复"
    assert bb.status == "drafting"


class MockLLMPassCritic(MockLLM):
    """Critic step returns approval; other sync calls keep default stub text."""

    def generate_stream_sync(self, messages, max_tokens=4096):
        if messages and messages[0].get("content") == CRITIC_SYSTEM:
            yield "【通过】审阅通过"
        else:
            yield from super().generate_stream_sync(messages, max_tokens=max_tokens)


def test_critic_pass_sets_status_done():
    bb = Blackboard(novel_name="test", current_prompt="测试提示词")
    llm = MockLLMPassCritic()

    list(PlannerAgent(llm).run_stream(bb))
    list(WriterAgent(llm).write_stream(bb))
    list(CriticAgent(llm).run_stream(bb))

    assert bb.critic_feedback.startswith("【通过】")
    assert bb.status == "done"


class MockLLMMultiChunk(MockLLM):
    def generate_stream_sync(self, messages, max_tokens=4096):
        yield "a"
        yield "b"
        yield "c"


def test_writer_persists_partial_draft_when_stream_not_exhausted():
    bb = Blackboard(novel_name="n", current_prompt="p", outline="outline")
    writer = WriterAgent(MockLLMMultiChunk())
    gen = writer.write_stream(bb)
    assert next(gen) == "a"
    gen.close()
    assert bb.draft == "a"
    assert bb.status == "reviewing"
