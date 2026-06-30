import json
from pathlib import Path


class MemoryService:
    def __init__(self, user_data_dir: Path):
        self.user_data_dir = user_data_dir

    @staticmethod
    def _validate_name(name: str) -> None:
        cleaned = name.strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
            raise ValueError(f"非法小说名称: {name}")

    def _memory_dir(self, novel_name: str) -> Path:
        self._validate_name(novel_name)
        return self.user_data_dir / novel_name / "memory"

    # ------ init ------

    def init_memory_files(self, novel_name: str) -> None:
        mem = self._memory_dir(novel_name)
        mem.mkdir(parents=True, exist_ok=True)

        # 世界观：从 worldview.md 迁移到 worldview.json
        wv_json = mem / "worldview.json"
        wv_md = mem / "worldview.md"
        if not wv_json.exists():
            if wv_md.exists():
                old_content = wv_md.read_text(encoding="utf-8").strip()
                if old_content:
                    migrated = [{"chapter_index": -1, "content": old_content}]
                else:
                    migrated = []
                wv_json.write_text(
                    json.dumps(migrated, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                wv_md.unlink()
            else:
                wv_json.write_text("[]", encoding="utf-8")

        tl_path = mem / "timeline.json"
        if not tl_path.exists():
            tl_path.write_text("[]", encoding="utf-8")

        ei_path = mem / "entity_index.json"
        if not ei_path.exists():
            ei_path.write_text("{}", encoding="utf-8")

        rs_path = mem / "recent_summary.json"
        if not rs_path.exists():
            rs_path.write_text(
                json.dumps(
                    {
                        "recent_3_chapters": [],
                        "recent_summary": "",
                        "last_updated_chapter_index": -1,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        ep_path = mem / "entity_profiles.json"
        if not ep_path.exists():
            ep_path.write_text("{}", encoding="utf-8")

    # ------ worldview (JSON list) ------

    def read_worldview_list(self, novel_name: str) -> list[dict]:
        p = self._memory_dir(novel_name) / "worldview.json"
        if not p.exists():
            return []
        return json.loads(p.read_text(encoding="utf-8"))

    def read_worldview(self, novel_name: str) -> str:
        """返回最新一条世界观的 content，没有则空字符串。"""
        wv_list = self.read_worldview_list(novel_name)
        if not wv_list:
            return ""
        return wv_list[-1].get("content", "")

    def read_style_guidelines(self, novel_name: str) -> str:
        p = self._memory_dir(novel_name) / "style_guidelines.md"
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8")

    def append_worldview(self, novel_name: str, chapter_index: int, content: str) -> None:
        wv_list = self.read_worldview_list(novel_name)
        wv_list.append({"chapter_index": chapter_index, "content": content})
        self._write_worldview_list(novel_name, wv_list)

    def rollback_worldview(self, novel_name: str, from_chapter_index: int) -> None:
        """删除 chapter_index >= from_chapter_index 的世界观条目。"""
        wv_list = self.read_worldview_list(novel_name)
        wv_list = [e for e in wv_list if e.get("chapter_index", -1) < from_chapter_index]
        self._write_worldview_list(novel_name, wv_list)

    def _write_worldview_list(self, novel_name: str, wv_list: list[dict]) -> None:
        (self._memory_dir(novel_name) / "worldview.json").write_text(
            json.dumps(wv_list, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 兼容旧接口：write_worldview 仍可直接覆写最新（用于 SSE 推送时简单读取）
    def write_worldview(self, novel_name: str, content: str) -> None:
        """兼容旧调用，不建议新代码使用，请用 append_worldview。"""
        self.append_worldview(novel_name, -1, content)

    # ------ timeline ------

    def read_timeline(self, novel_name: str) -> list[dict]:
        return json.loads(
            (self._memory_dir(novel_name) / "timeline.json").read_text(encoding="utf-8")
        )

    def write_timeline(self, novel_name: str, events: list[dict]) -> None:
        (self._memory_dir(novel_name) / "timeline.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def rollback_timeline(self, novel_name: str, from_chapter_index: int) -> None:
        tl = self.read_timeline(novel_name)
        tl = [e for e in tl if e.get("chapter_index", -1) < from_chapter_index]
        self.write_timeline(novel_name, tl)

    # ------ entity index ------

    def read_entity_index(self, novel_name: str) -> dict[str, list[int]]:
        p = self._memory_dir(novel_name) / "entity_index.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def write_entity_index(self, novel_name: str, index: dict[str, list[int]]) -> None:
        (self._memory_dir(novel_name) / "entity_index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def update_entity_index(
        self, novel_name: str, chapter_index: int, entities: list[str]
    ) -> None:
        idx = self.read_entity_index(novel_name)
        for ent in entities:
            ent = ent.strip()
            if not ent:
                continue
            if ent not in idx:
                idx[ent] = []
            if chapter_index not in idx[ent]:
                idx[ent].append(chapter_index)
        self.write_entity_index(novel_name, idx)

    def rollback_entity_index(self, novel_name: str, from_chapter_index: int) -> None:
        idx = self.read_entity_index(novel_name)
        cleaned = {}
        for ent, chapters in idx.items():
            filtered = [c for c in chapters if c < from_chapter_index]
            if filtered:
                cleaned[ent] = filtered
        self.write_entity_index(novel_name, cleaned)

    # ------ entity profiles ------

    def read_entity_profiles(self, novel_name: str) -> dict:
        p = self._memory_dir(novel_name) / "entity_profiles.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def write_entity_profiles(self, novel_name: str, profiles: dict) -> None:
        (self._memory_dir(novel_name) / "entity_profiles.json").write_text(
            json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def update_entity_profile(
        self,
        novel_name: str,
        entity_name: str,
        description: str,
        status: str,
        chapter_index: int,
    ) -> None:
        profiles = self.read_entity_profiles(novel_name)
        if entity_name not in profiles:
            profiles[entity_name] = {}
        if description:
            profiles[entity_name]["description"] = description
        if status:
            profiles[entity_name]["current_status"] = status
        profiles[entity_name]["last_updated_chapter"] = chapter_index
        self.write_entity_profiles(novel_name, profiles)

    def rollback_entity_profiles(self, novel_name: str, from_chapter_index: int) -> None:
        profiles = self.read_entity_profiles(novel_name)
        cleaned = {
            k: v
            for k, v in profiles.items()
            if v.get("last_updated_chapter", -1) < from_chapter_index
        }
        self.write_entity_profiles(novel_name, cleaned)

    # ------ recent summary ------

    def read_recent_summary(self, novel_name: str) -> dict:
        return json.loads(
            (self._memory_dir(novel_name) / "recent_summary.json").read_text(encoding="utf-8")
        )

    def write_recent_summary(
        self,
        novel_name: str,
        recent_3: list[str],
        summary_text: str,
        last_index: int,
    ) -> None:
        data = {
            "recent_3_chapters": recent_3,
            "recent_summary": summary_text,
            "last_updated_chapter_index": last_index,
        }
        (self._memory_dir(novel_name) / "recent_summary.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------ rollback all ------

    def rollback_memory(self, novel_name: str, deleted_chapter_index: int) -> None:
        """删除某章节后回滚所有记忆到该章之前。"""
        self.rollback_worldview(novel_name, deleted_chapter_index)
        self.rollback_timeline(novel_name, deleted_chapter_index)
        self.rollback_entity_index(novel_name, deleted_chapter_index)
        self.rollback_entity_profiles(novel_name, deleted_chapter_index)
        summary = self.read_recent_summary(novel_name)
        last_idx = summary.get("last_updated_chapter_index", -1)
        if last_idx >= deleted_chapter_index:
            self.write_recent_summary(
                novel_name, [], "", deleted_chapter_index - 1
            )
