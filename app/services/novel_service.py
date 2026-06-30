import json
import shutil
from pathlib import Path


class NovelService:
    def __init__(self, user_data_dir: Path):
        self.user_data_dir = user_data_dir
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or "/" in name or "\\" in name or ".." in name or name.strip() != name:
            raise ValueError(f"非法小说名称: {name}")

    def _novel_dir(self, name: str) -> Path:
        self._validate_name(name)
        return self.user_data_dir / name

    def _chapters_path(self, name: str) -> Path:
        return self._novel_dir(name) / "chapters.json"

    def create_novel(self, name: str) -> None:
        novel_dir = self._novel_dir(name)
        (novel_dir / "memory").mkdir(parents=True, exist_ok=True)
        path = self._chapters_path(name)
        if not path.exists():
            path.write_text("[]", encoding="utf-8")

    def list_novels(self) -> list[dict]:
        result = []
        if not self.user_data_dir.exists():
            return result
        for d in sorted(self.user_data_dir.iterdir()):
            if d.is_dir() and (d / "chapters.json").exists():
                chapters = json.loads((d / "chapters.json").read_text(encoding="utf-8"))
                result.append({"name": d.name, "chapter_count": len(chapters)})
        return result

    def get_chapters(self, name: str) -> list[dict]:
        path = self._chapters_path(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def append_chapter(self, name: str, title: str, text: str, prompt: str = "") -> dict:
        chapters = self.get_chapters(name)
        chapter = {"start_line": len(chapters) + 1, "title": title, "text": text}
        if prompt:
            chapter["prompt"] = prompt
        chapters.append(chapter)
        self._chapters_path(name).write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return chapter

    def delete_last_chapter(self, name: str) -> bool:
        chapters = self.get_chapters(name)
        if not chapters:
            return False
        chapters.pop()
        self._chapters_path(name).write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    def delete_novel(self, name: str) -> bool:
        novel_dir = self._novel_dir(name)
        if novel_dir.exists():
            shutil.rmtree(novel_dir)
            return True
        return False

    def rename_novel(self, old_name: str, new_name: str) -> bool:
        old_dir = self._novel_dir(old_name)
        new_dir = self._novel_dir(new_name)
        if not old_dir.exists() or new_dir.exists():
            return False
        old_dir.rename(new_dir)
        return True

    def upload_novel(self, name: str, json_content: str) -> int:
        chapters = json.loads(json_content)
        novel_dir = self._novel_dir(name)
        (novel_dir / "memory").mkdir(parents=True, exist_ok=True)
        self._chapters_path(name).write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return len(chapters)
