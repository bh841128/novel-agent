import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.agents.skills.base import SkillRegistry


def _write_pipeline_llm_side_effect():
    """Mocks ChiefEditor + Critic ``generate_sync`` sequence for one /write."""
    return [
        '{"thought":"t","action":"call_planner"}',
        '{"thought":"t","action":"call_writer"}',
        '{"thought":"t","action":"call_critic"}',
        "【通过】审阅通过",
    ]


def _stream_with_tools_for_agents():
    """Each call returns a new iterator; text must start with 【通过】 when Critic runs with tools."""
    return lambda *args, **kwargs: iter(["【通过】mock"])


def _create_client():
    client = TestClient(create_app())
    return client


@patch("app.routers.chat.timeline_retriever")
@patch("app.routers.chat.llm_service")
def test_ask_endpoint_returns_sse(mock_llm, mock_retriever):
    mock_retriever.retrieve.return_value = []
    mock_llm.generate_stream_sync.return_value = iter(["回答内容"])
    client = _create_client()
    client.post("/api/novels", json={"name": "ask_test"})
    resp = client.post("/api/chat/ask", json={"novel_name": "ask_test", "content": "这是谁"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "data:" in resp.text


@patch("app.routers.memory.sync_memory_single_chapter")
@patch("app.routers.chat.timeline_retriever")
@patch("app.routers.chat.llm_service")
def test_write_endpoint_returns_sse(mock_llm, mock_retriever, _mock_sync_memory):
    mock_retriever.retrieve.return_value = []
    mock_llm.generate_sync.side_effect = _write_pipeline_llm_side_effect()
    mock_llm.generate_with_tools_sync.return_value = {
        "content": "大纲内容",
        "tool_calls": [],
    }
    mock_llm.generate_stream_sync.return_value = iter(["续写内容"])
    mock_llm.generate_stream_with_tools_sync.side_effect = _stream_with_tools_for_agents()
    client = _create_client()
    novel_name = f"write_test_{uuid.uuid4().hex}"
    client.post("/api/novels", json={"name": novel_name})
    resp = client.post("/api/chat/write", json={"novel_name": novel_name, "content": "续写"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


@patch("app.routers.memory.sync_memory_single_chapter")
@patch("app.routers.chat.timeline_retriever")
@patch("app.routers.chat.llm_service")
def test_write_appends_chapter(mock_llm, mock_retriever, _mock_sync_memory):
    mock_retriever.retrieve.return_value = []
    mock_llm.generate_sync.side_effect = _write_pipeline_llm_side_effect()
    mock_llm.generate_with_tools_sync.return_value = {
        "content": "大纲内容",
        "tool_calls": [],
    }
    mock_llm.generate_stream_sync.return_value = iter(["一段新内容"])
    mock_llm.generate_stream_with_tools_sync.side_effect = _stream_with_tools_for_agents()
    client = _create_client()
    client.post("/api/novels", json={"name": "write_append"})
    client.post("/api/chat/write", json={"novel_name": "write_append", "content": "续写一段"})
    resp = client.get("/api/novels/write_append/chapters")
    chapters = resp.json()
    assert len(chapters) >= 1


@patch("app.routers.memory.sync_memory_single_chapter")
@patch("app.routers.chat.timeline_retriever")
@patch("app.routers.chat.llm_service")
def test_delete_last_chapter(mock_llm, mock_retriever, _mock_sync_memory):
    mock_retriever.retrieve.return_value = []
    mock_llm.generate_sync.side_effect = (
        _write_pipeline_llm_side_effect() + _write_pipeline_llm_side_effect()
    )
    mock_llm.generate_with_tools_sync.return_value = {
        "content": "大纲内容",
        "tool_calls": [],
    }
    mock_llm.generate_stream_sync.side_effect = [
        iter(["第一段内容"]),
        iter(["第二段内容"]),
    ]
    mock_llm.generate_stream_with_tools_sync.side_effect = _stream_with_tools_for_agents()
    client = _create_client()
    novel_name = f"del_test_{uuid.uuid4().hex}"
    client.post("/api/novels", json={"name": novel_name})
    client.post("/api/chat/write", json={"novel_name": novel_name, "content": "第一段"})
    client.post("/api/chat/write", json={"novel_name": novel_name, "content": "第二段"})

    resp = client.delete(f"/api/chat/{novel_name}/last")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    chapters = client.get(f"/api/novels/{novel_name}/chapters").json()
    assert len(chapters) == 1


@patch("app.routers.memory.sync_memory_single_chapter")
@patch("app.routers.chat.CriticAgent")
@patch("app.routers.chat.timeline_retriever")
@patch("app.routers.chat.llm_service")
def test_write_passes_skill_registry_to_critic(
    mock_llm, mock_retriever, mock_critic_cls, _mock_sync_memory,
):
    """CriticAgent must receive the same SkillRegistry as planner/writer (global skills)."""
    mock_retriever.retrieve.return_value = []
    mock_inst = mock_critic_cls.return_value

    def _critic_run_stream(bb):
        bb.update(critic_feedback="【通过】", status="done")
        yield from ()

    mock_inst.run_stream.side_effect = _critic_run_stream

    mock_llm.generate_sync.side_effect = _write_pipeline_llm_side_effect()
    mock_llm.generate_with_tools_sync.return_value = {
        "content": "大纲内容",
        "tool_calls": [],
    }
    mock_llm.generate_stream_sync.return_value = iter(["续写内容"])
    mock_llm.generate_stream_with_tools_sync.side_effect = _stream_with_tools_for_agents()

    client = _create_client()
    novel_name = f"registry_test_{uuid.uuid4().hex}"
    client.post("/api/novels", json={"name": novel_name})
    client.post("/api/chat/write", json={"novel_name": novel_name, "content": "续写"})

    mock_critic_cls.assert_called_once()
    registry = mock_critic_cls.call_args.kwargs.get("registry")
    assert registry is not None
    assert isinstance(registry, SkillRegistry)
    names = {s["function"]["name"] for s in registry.get_all_schemas()}
    assert names == {"search_entity", "query_worldview"}


@patch("app.routers.chat.timeline_retriever")
@patch("app.routers.chat.llm_service")
def test_ask_does_not_persist(mock_llm, mock_retriever):
    mock_retriever.retrieve.return_value = []
    mock_llm.generate_stream_sync.return_value = iter(["这是回答"])
    client = _create_client()
    client.post("/api/novels", json={"name": "ask_no_persist"})
    client.post("/api/chat/ask", json={"novel_name": "ask_no_persist", "content": "问题"})
    chapters = client.get("/api/novels/ask_no_persist/chapters").json()
    assert len(chapters) == 0
