import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def isolate_user_data(tmp_path):
    """将 settings.user_data_dir 指向临时目录，并同步更新所有已实例化的 service，
    测试结束后自动清理，永远不碰真实数据。"""
    original = settings.user_data_dir
    test_dir = tmp_path / "user_data"
    test_dir.mkdir()
    settings.user_data_dir = test_dir

    from app.routers import chat, memory, novel
    for mod in (chat, memory, novel):
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if hasattr(obj, "user_data_dir"):
                obj.user_data_dir = test_dir

    yield

    settings.user_data_dir = original
    for mod in (chat, memory, novel):
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if hasattr(obj, "user_data_dir"):
                obj.user_data_dir = original
