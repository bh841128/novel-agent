import json

from app.agents.blackboard import Blackboard
from app.agents.skills.base import SkillRegistry
from app.services.context_builder import ContextBuilder
from app.services.llm_service import LLMService


class PlannerAgent:
    def __init__(self, llm: LLMService, registry: SkillRegistry | None = None):
        self.llm = llm
        self.cb = ContextBuilder()
        self.registry = registry

    def run_stream(self, bb: Blackboard):
        messages = self.cb.build_write_messages(
            bb.worldview,
            bb.timeline,
            bb.recent_summary,
            bb.recent_3_raw,
            "请写大纲：" + bb.current_prompt,
            bb.style_guidelines,
            bb.entity_profiles_text,
        )
        planner_note = "\n你现在的角色是规划师(Planner)，只输出剧情大纲和核心动机。如果需要查阅角色详细档案，请调用相应的工具技能。"
        sys_msg = next((m for m in messages if m.get("role") == "system"), None)
        if sys_msg is not None:
            sys_msg["content"] = (sys_msg.get("content") or "") + planner_note
            if bb.chief_directive:
                sys_msg["content"] += (
                    f"\n\n【总编（最高调度官）发来的最高级别批示】：\n{bb.chief_directive}\n"
                    "必须严格按照此批示执行本轮任务！"
                )

        tools = self.registry.get_all_schemas() if self.registry else []
        full_text = ""

        while True:
            has_tool_calls = False
            if tools:
                for chunk in self.llm.generate_stream_with_tools_sync(messages, tools=tools, max_tokens=4096):
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
                            yield f"\n*[调用技能：{tc['function']['name']}]*\n"
            else:
                for chunk in self.llm.generate_stream_sync(messages, max_tokens=4096):
                    full_text += chunk
                    yield chunk

            if not has_tool_calls:
                break

        bb.update(
            outline=full_text,
            status="drafting",
        )
