import shutil
import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app


def test_get_memory_endpoint():
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "mem_test"})
    resp = client.get("/api/memory/mem_test")
    assert resp.status_code == 200
    data = resp.json()
    assert "worldview" in data
    assert "timeline" in data
    assert "recent_summary" in data


@patch("app.routers.memory.llm_service")
def test_update_memory_returns_sse(mock_llm):
    mock_llm.generate_sync.return_value = "否"
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "mem_update_test"})
    resp = client.post("/api/memory/mem_update_test/update")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


@patch("app.routers.memory.embedding_service")
@patch("app.routers.memory.llm_service")
def test_update_memory_with_chapters(mock_llm, mock_emb):
    mock_emb.encode_single.return_value = [0.1, 0.2, 0.3]
    mock_llm.generate_sync.side_effect = [
        "是",  # ch1 judge
        "# 世界观v1\n角色A登场",  # ch1 worldview update
        "事件：角色A登场\n地点：广场\n参与者：角色A\n过程：角色A首次出现\n结局状态：正式加入",  # ch1 timeline
        "否",  # ch2 judge
        "事件：日常训练\n地点：训练场\n参与者：角色A\n过程：训练\n结局状态：完成",  # ch2 timeline
        "情节总结内容",  # summary
    ]
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "mem_full_test"})
    import json
    from app.config import settings
    chapters_path = settings.user_data_dir / "mem_full_test" / "chapters.json"
    chapters_path.write_text(json.dumps([
        {"start_line": 1, "title": "第1章", "text": "第一章内容"},
        {"start_line": 2, "title": "第2章", "text": "第二章内容"},
    ], ensure_ascii=False), encoding="utf-8")

    resp = client.post("/api/memory/mem_full_test/update")
    assert resp.status_code == 200
    text = resp.text
    assert "世界观" in text


@patch("app.routers.memory.llm_service")
def test_cancel_update(mock_llm):
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "cancel_test"})
    resp = client.post("/api/memory/cancel_test/cancel")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True


@patch("app.routers.memory.embedding_service")
@patch("app.routers.memory.llm_service")
def test_worldview_judge_false_positive(mock_llm, mock_emb):
    """'但是' 包含 '是' 字但不应触发世界观更新"""
    mock_emb.encode_single.return_value = [0.1, 0.2]
    mock_llm.generate_sync.side_effect = [
        "但是",  # ch1 judge — should be treated as "否"
        "事件：普通战斗\n地点：战场\n参与者：战士\n过程：战斗\n结局状态：结束",  # ch1 timeline
        "情节总结",  # summary
    ]
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "judge_fp_test"})
    import json
    from app.config import settings
    chapters_path = settings.user_data_dir / "judge_fp_test" / "chapters.json"
    chapters_path.write_text(json.dumps([
        {"start_line": 1, "title": "第1章", "text": "普通战斗场景"},
    ], ensure_ascii=False), encoding="utf-8")

    resp = client.post("/api/memory/judge_fp_test/update")
    assert resp.status_code == 200
    text = resp.text
    assert "世界观已更新" not in text
    assert "世界观无需更新" in text


@patch("app.routers.memory.embedding_service")
@patch("app.routers.memory.llm_service")
def test_worldview_judge_exact_yes(mock_llm, mock_emb):
    """精确回答 '是' 应触发世界观更新"""
    mock_emb.encode_single.return_value = [0.1, 0.2]
    mock_llm.generate_sync.side_effect = [
        "是",  # ch1 judge
        "# 新世界观\n角色A登场",  # ch1 worldview update
        "事件：新角色登场\n地点：废墟\n参与者：角色A\n过程：登场\n结局状态：加入",  # ch1 timeline
        "情节总结",  # summary
    ]
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "judge_yes_test"})
    import json
    from app.config import settings
    chapters_path = settings.user_data_dir / "judge_yes_test" / "chapters.json"
    chapters_path.write_text(json.dumps([
        {"start_line": 1, "title": "第1章", "text": "新角色登场"},
    ], ensure_ascii=False), encoding="utf-8")

    resp = client.post("/api/memory/judge_yes_test/update")
    text = resp.text
    assert "世界观已更新" in text


@patch("app.routers.memory.embedding_service")
@patch("app.routers.memory.llm_service")
def test_concurrent_update_rejected(mock_llm, mock_emb):
    """同一小说不能并行更新，第二次请求应返回 409"""
    mock_emb.encode_single.return_value = [0.1]

    def slow_generate(*args, **kwargs):
        time.sleep(0.5)
        return "否"

    mock_llm.generate_sync.side_effect = slow_generate

    import json
    from app.config import settings

    novel_dir = settings.user_data_dir / "concurrent_test"
    shutil.rmtree(novel_dir, ignore_errors=True)

    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "concurrent_test"})
    chapters_path = novel_dir / "chapters.json"
    chapters_path.write_text(
        json.dumps(
            [{"start_line": 1, "title": "第1章", "text": "内容"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    results = {}

    def do_update(key):
        r = client.post("/api/memory/concurrent_test/update")
        results[key] = r.status_code

    t1 = threading.Thread(target=do_update, args=("first",))
    t2 = threading.Thread(target=do_update, args=("second",))
    t1.start()
    time.sleep(0.1)
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    statuses = sorted(results.values())
    assert 409 in statuses, f"Expected one 409, got {results}"


@patch("app.routers.memory.embedding_service")
@patch("app.routers.memory.llm_service")
def test_timeline_empty_content_skipped(mock_llm, mock_emb):
    """时间线为空时应有跳过消息"""
    mock_emb.encode_single.return_value = [0.1]
    mock_llm.generate_sync.side_effect = [
        "否",  # ch1 judge
        "",    # ch1 timeline — empty
        "情节总结",  # summary
    ]
    client = TestClient(create_app())
    client.post("/api/novels", json={"name": "tl_empty_test"})
    import json
    from app.config import settings
    chapters_path = settings.user_data_dir / "tl_empty_test" / "chapters.json"
    chapters_path.write_text(json.dumps([
        {"start_line": 1, "title": "第1章", "text": "内容"},
    ], ensure_ascii=False), encoding="utf-8")

    resp = client.post("/api/memory/tl_empty_test/update")
    text = resp.text
    assert "时间线为空" in text
    assert "done" in text
