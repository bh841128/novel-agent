from app.agents.blackboard import Blackboard


def test_blackboard_initialization_and_update():
    bb = Blackboard(novel_name="test_novel", prompt="测试提示")
    assert bb.novel_name == "test_novel"
    assert bb.current_prompt == "测试提示"
    assert bb.outline == ""
    assert bb.draft == ""
    assert bb.critic_feedback == ""
    assert bb.status == "planning"

    bb.update(outline="这是一个大纲", status="drafting")
    assert bb.outline == "这是一个大纲"
    assert bb.status == "drafting"
