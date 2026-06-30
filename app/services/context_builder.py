class ContextBuilder:
    SYSTEM_PROMPT = "你是一个专业的小说续写助手。请根据提供的世界观设定、事件时间线、前情摘要和最近章节原文，续写高质量的小说内容。保持角色性格一致、情节连贯、文风统一。"

    ASK_SYSTEM_PROMPT = "你是一个小说分析助手。请根据提供的小说世界观、事件时间线和章节内容，回答用户关于小说内容的问题。"

    @staticmethod
    def format_timeline(entries: list[dict]) -> str:
        """将召回的时间线条目格式化为 prompt 文本。"""
        if not entries:
            return "暂无"
        parts = []
        for e in entries:
            chapter = e.get("chapter", "未知章节")
            content = e.get("content", "")
            parts.append(f"【{chapter}】\n{content}")
        return "\n\n".join(parts)

    def _build_messages(
        self,
        system_prompt: str,
        worldview: str,
        timeline_text: str,
        recent_summary: str,
        recent_3_raw: str,
        user_input: str,
        style_guidelines: str = "",
        entity_profiles_text: str = "",
    ) -> list[dict]:
        wv_text = worldview or "暂无世界观数据"
        messages = [{"role": "system", "content": system_prompt}]
        if style_guidelines:
            messages.append({"role": "system", "content": f"【文风与叙事规范】\n{style_guidelines}"})
        messages.append({"role": "system", "content": f"【世界观设定】\n{wv_text}"})
        if entity_profiles_text:
            messages.append({"role": "system", "content": f"【相关人物档案】\n{entity_profiles_text}"})
        messages.append({"role": "system", "content": f"【相关事件时间线】\n{timeline_text}"})
        messages.append({"role": "system", "content": f"【近章情节总结】\n{recent_summary}"})
        messages.append({"role": "system", "content": f"【最近3章原文】\n{recent_3_raw}"})
        messages.append({"role": "user", "content": user_input})
        return messages

    def build_write_messages(
        self,
        worldview: str,
        timeline_text: str,
        recent_summary: str,
        recent_3_raw: str,
        user_input: str,
        style_guidelines: str = "",
        entity_profiles_text: str = "",
    ) -> list[dict]:
        return self._build_messages(
            self.SYSTEM_PROMPT, worldview, timeline_text,
            recent_summary, recent_3_raw, user_input,
            style_guidelines, entity_profiles_text
        )

    def build_ask_messages(
        self,
        worldview: str,
        timeline_text: str,
        recent_summary: str,
        recent_3_raw: str,
        user_input: str,
        style_guidelines: str = "",
        entity_profiles_text: str = "",
    ) -> list[dict]:
        return self._build_messages(
            self.ASK_SYSTEM_PROMPT, worldview, timeline_text,
            recent_summary, recent_3_raw, user_input,
            style_guidelines, entity_profiles_text
        )
