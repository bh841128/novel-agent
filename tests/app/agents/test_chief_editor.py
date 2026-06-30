from app.agents.blackboard import Blackboard
from app.agents.chief_editor import ChiefEditorAgent
from app.services.llm_service import LLMService


class MockLLM(LLMService):
    def __init__(self):
        super().__init__("stub", "test", "test")
        self.call_count = 0

    def generate_stream_sync(self, messages, max_tokens=4096):
        self.call_count += 1
        bb_status = messages[1]["content"]  # 从 prompt 中获取模拟的状态
        if "当前流程状态: planning" in bb_status:
            yield (
                '{"thought": "我们需要先写大纲", "directive": "先规划", '
                '"action": "call_planner"}'
            )
        elif "当前流程状态: drafting" in bb_status:
            yield (
                '{"thought": "大纲已就绪，开始起草", "directive": "继续", '
                '"action": "call_writer"}'
            )
        elif "当前流程状态: reviewing" in bb_status:
            yield (
                '{"thought": "草稿已就绪，开始审阅", "directive": "审一下", '
                '"action": "call_critic"}'
            )
        elif "当前流程状态: done" in bb_status:
            yield '{"thought": "一切就绪", "directive": "收工", "action": "finish"}'
        else:
            yield '{"thought": "出错", "directive": "无", "action": "finish"}'


class MalformedJsonLLM(LLMService):
    def __init__(self):
        super().__init__("stub", "test", "test")

    def generate_stream_sync(self, messages, max_tokens=4096):
        yield "this is not valid json {"


class InvalidActionLLM(LLMService):
    def __init__(self):
        super().__init__("stub", "test", "test")

    def generate_stream_sync(self, messages, max_tokens=4096):
        yield '{"thought": "bad", "directive": "x", "action": "call_hacker"}'


class MockLLMOutlineAssert(LLMService):
    def __init__(self):
        super().__init__("stub", "test", "test")

    def generate_stream_sync(self, messages, max_tokens=4096):
        # 验证消息中是否包含了截断的大纲内容
        assert "大纲内容" in messages[1]["content"]
        yield (
            '{"thought": "写得不错", "directive": "继续写", "action": "call_writer"}'
        )


def test_chief_editor_react_decision():
    llm = MockLLMOutlineAssert()
    editor = ChiefEditorAgent(llm)

    bb = Blackboard(
        novel_name="test",
        current_prompt="test",
        status="drafting",
        outline="大纲内容",
    )

    action, thought, directive = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, thought, directive = chunk

    assert action == "call_writer"
    assert thought == "写得不错"
    assert directive == "继续写"


def test_chief_editor_routing():
    llm = MockLLM()
    editor = ChiefEditorAgent(llm)

    # 测试规划阶段的路由
    bb = Blackboard(novel_name="test", current_prompt="test", status="planning")
    action, thought, directive = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, thought, directive = chunk
    assert action == "call_planner"
    assert thought == "我们需要先写大纲"

    # 测试完成阶段的路由
    bb.status = "done"
    action, thought, directive = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, thought, directive = chunk
    assert action == "finish"
    assert thought == "一切就绪"


def test_chief_editor_drafting_routes_to_writer():
    editor = ChiefEditorAgent(MockLLM())
    bb = Blackboard(
        novel_name="t",
        current_prompt="p",
        status="drafting",
        outline="has outline",
    )
    action, _, _ = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, _, _ = chunk
    assert action == "call_writer"


def test_chief_editor_reviewing_routes_to_critic():
    editor = ChiefEditorAgent(MockLLM())
    bb = Blackboard(
        novel_name="t",
        current_prompt="p",
        status="reviewing",
        outline="o",
        draft="d",
    )
    action, _, _ = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, _, _ = chunk
    assert action == "call_critic"


def test_chief_editor_malformed_llm_output_defaults_to_finish():
    editor = ChiefEditorAgent(MalformedJsonLLM())
    bb = Blackboard(novel_name="t", current_prompt="p", status="planning")
    action, thought, directive = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, thought, directive = chunk
    assert action == "finish"
    assert thought == "解析 JSON 失败"
    assert directive == "无批示"


def test_chief_editor_invalid_action_defaults_to_finish():
    editor = ChiefEditorAgent(InvalidActionLLM())
    bb = Blackboard(novel_name="t", current_prompt="p", status="planning")
    action, thought, directive = None, None, None
    for chunk in editor.decide_next_action_stream(bb):
        if isinstance(chunk, tuple):
            action, thought, directive = chunk
    assert action == "finish"
    assert thought == "bad"
    assert directive == "x"
