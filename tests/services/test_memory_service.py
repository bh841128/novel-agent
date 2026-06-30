from app.services.memory_service import MemoryService


def test_init_creates_memory_files():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_novel")
    mem = settings.user_data_dir / "test_novel" / "memory"
    assert (mem / "worldview.json").exists()
    assert (mem / "timeline.json").exists()
    assert (mem / "recent_summary.json").exists()


def test_recent_summary_has_last_updated_index():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_idx")
    data = svc.read_recent_summary("test_idx")
    assert "last_updated_chapter_index" in data
    assert data["last_updated_chapter_index"] == -1


def test_read_worldview():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_wv")
    wv = svc.read_worldview("test_wv")
    assert wv == ""


def test_read_timeline():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_tl")
    tl = svc.read_timeline("test_tl")
    assert tl == []


def test_write_worldview():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_wv2")
    svc.write_worldview("test_wv2", "# 世界观\n角色：林岚")
    assert svc.read_worldview("test_wv2") == "# 世界观\n角色：林岚"


def test_write_timeline_new_format():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_tl2")
    entries = [
        {"chapter_index": 0, "chapter": "第1章", "content": "事件：战斗", "embedding": [0.1, 0.2]},
    ]
    svc.write_timeline("test_tl2", entries)
    result = svc.read_timeline("test_tl2")
    assert len(result) == 1
    assert result[0]["content"] == "事件：战斗"
    assert result[0]["embedding"] == [0.1, 0.2]


def test_write_recent_summary():
    from app.config import settings
    svc = MemoryService(settings.user_data_dir)
    svc.init_memory_files("test_rs")
    svc.write_recent_summary("test_rs", ["章1", "章2"], "总结内容", 5)
    data = svc.read_recent_summary("test_rs")
    assert data["recent_3_chapters"] == ["章1", "章2"]
    assert data["recent_summary"] == "总结内容"
    assert data["last_updated_chapter_index"] == 5
