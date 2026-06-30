import json
from collections.abc import Iterator

from app.agents.blackboard import Blackboard
from app.agents.skills.base import SkillRegistry
from app.services.context_builder import ContextBuilder
from app.services.llm_service import LLMService


class WriterAgent:
    def __init__(self, llm: LLMService, registry: SkillRegistry | None = None):
        self.llm = llm
        self.cb = ContextBuilder()
        self.registry = registry

    def write_stream(self, bb: Blackboard) -> Iterator[str]:
        prompt = (
            f"【写作要求】\n{bb.current_prompt}\n【本章大纲】\n{bb.outline}\n请根据大纲和要求开始撰写正文。"
        )
        if bb.critic_feedback:
            prompt += f"\n【审阅意见】\n{bb.critic_feedback}\n请根据意见进行修改。"
        if bb.chief_directive:
            prompt += (
                f"\n\n【总编（最高调度官）发来的最高级别批示】：\n{bb.chief_directive}\n"
                "写作时必须严格遵守此批示！"
            )

        messages = self.cb.build_write_messages(
            bb.worldview,
            bb.timeline,
            bb.recent_summary,
            bb.recent_3_raw,
            prompt,
            bb.style_guidelines,
            bb.entity_profiles_text,
        )

        tools = self.registry.get_all_schemas() if self.registry else []
        full_text = ""

        try:
            while True:
                has_tool_calls = False
                if tools:
                    for chunk in self.llm.generate_stream_with_tools_sync(messages, tools=tools, max_tokens=8192):
                        if isinstance(chunk, str):
                            full_text += chunk
                            yield chunk
                        elif isinstance(chunk, dict) and "tool_calls" in chunk:
                            has_tool_calls = True
                            messages.append({
                                "role": "assistant",
                                "content": "",
                                "tool_calls": chunk["tool_calls"]
                            })
                            for tc in chunk["tool_calls"]:
                                try:
                                    kwargs = json.loads(tc["function"]["arguments"])
                                    result = self.registry.execute(tc["function"]["name"], kwargs)
                                except Exception as e:
                                    result = f"调用失败: {e}"
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": str(result)
                                })
                else:
                    for chunk in self.llm.generate_stream_sync(messages, max_tokens=8192):
                        full_text += chunk
                        yield chunk

                if not has_tool_calls:
                    break
        finally:
            bb.update(draft=full_text, status="reviewing")
