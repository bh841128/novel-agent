from app.services.context_builder import ContextBuilder


def test_write_context_contains_all_sections():
    builder = ContextBuilder()
    msgs = builder.build_write_messages(
        worldview="# 世界观\n林岚是主角",
        timeline_text="【前章-1】\n事件：重逢\n参与者：林岚",
        recent_summary="近章总结",
        recent_3_raw="最近3章原文",
        user_input="续写一段",
    )
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "续写一段"
    contents = [m["content"] for m in msgs]
    assert any("林岚" in c for c in contents)
    assert any("最近3章原文" in c for c in contents)
    assert any("近章总结" in c for c in contents)


def test_ask_context_same_structure():
    builder = ContextBuilder()
    msgs = builder.build_ask_messages(
        worldview="测试世界观内容",
        timeline_text="暂无",
        recent_summary="S",
        recent_3_raw="R",
        user_input="问一个问题",
    )
    assert msgs[-1]["content"] == "问一个问题"
    assert any("测试世界观内容" in m["content"] for m in msgs)


def test_format_timeline():
    builder = ContextBuilder()
    entries = [
        {"chapter": "第1章", "content": "事件：战斗\n地点：广场"},
        {"chapter": "第2章", "content": "事件：重逢\n地点：废墟"},
    ]
    result = builder.format_timeline(entries)
    assert "【第1章】" in result
    assert "【第2章】" in result
    assert "战斗" in result


def test_format_timeline_empty():
    builder = ContextBuilder()
    assert builder.format_timeline([]) == "暂无"
