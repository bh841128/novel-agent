from pathlib import Path

from app.services.novel_service import NovelService


def test_create_and_append_chapter(tmp_path: Path):
    service = NovelService(user_data_dir=tmp_path)
    service.create_novel("demo")
    service.append_chapter("demo", "第1章", "正文1")
    chapters = service.get_chapters("demo")
    assert len(chapters) == 1
    assert chapters[0]["title"] == "第1章"
    assert chapters[0]["text"] == "正文1"


def test_delete_last_chapter(tmp_path: Path):
    service = NovelService(user_data_dir=tmp_path)
    service.create_novel("demo")
    service.append_chapter("demo", "第1章", "正文1")
    service.append_chapter("demo", "第2章", "正文2")
    deleted = service.delete_last_chapter("demo")
    assert deleted is True
    chapters = service.get_chapters("demo")
    assert len(chapters) == 1
    assert chapters[0]["title"] == "第1章"


def test_delete_last_chapter_empty(tmp_path: Path):
    service = NovelService(user_data_dir=tmp_path)
    service.create_novel("demo")
    deleted = service.delete_last_chapter("demo")
    assert deleted is False


def test_list_novels(tmp_path: Path):
    service = NovelService(user_data_dir=tmp_path)
    service.create_novel("novel_a")
    service.create_novel("novel_b")
    novels = service.list_novels()
    names = [n["name"] for n in novels]
    assert "novel_a" in names
    assert "novel_b" in names


def test_upload_chapters(tmp_path: Path):
    import json

    service = NovelService(user_data_dir=tmp_path)
    data = [{"start_line": 1, "title": "前章-1", "text": "内容1"}]
    service.upload_novel("uploaded", json.dumps(data))
    chapters = service.get_chapters("uploaded")
    assert len(chapters) == 1
    assert chapters[0]["title"] == "前章-1"
