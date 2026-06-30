import json

from app.agents.blackboard import Blackboard
from app.agents.skills.base import SkillRegistry
from app.services.llm_service import LLMService

CRITIC_SYSTEM = """你是极其严苛的审阅者。
你的任务是审查草稿是否符合大纲、有无逻辑漏洞、是否发生OOC（角色设定崩坏）或设定冲突。

【强制执行的核查规则】
你绝对不能凭主观直觉或大纲的暗示来判断角色的性别、外貌、背景等属性！
在给出最终评判前，你【必须】使用工具 `search_entity` 逐一查询草稿中出现的核心人物、组织或专有名词。
比如，如果草稿写了“林烽/林峰”，你必须先调用工具查询“林峰”的档案，看看档案里他到底是男是女，是什么身份！

流程要求：
1. 提取草稿中的核心实体。
2. 立即调用工具查询这些实体的设定。
3. 仔细对比工具返回的设定与草稿的描写。如果有任何违背设定的描写（如女写成男，或相反），绝对不允许通过。
4. 审查完成后，如果完全合格，请回复以 '【通过】' 开头。否则，严厉指出OOC或漏洞并要求重写。"""


class CriticAgent:
    def __init__(self, llm: LLMService, registry: SkillRegistry | None = None):
        self.llm = llm
        self.registry = registry

    def run_stream(self, bb: Blackboard):
        prompt = (
            f"【原大纲】\n{bb.outline}\n\n【草稿正文】\n{bb.draft}\n\n"
            "请严格审阅上述草稿。"
        )
        messages = [
            {"role": "system", "content": CRITIC_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        tools = self.registry.get_all_schemas() if self.registry else []
        full_text = ""

        try:
            while True:
                has_tool_calls = False
                if tools:
                    for chunk in self.llm.generate_stream_with_tools_sync(
                        messages, tools=tools, max_tokens=4096
                    ):
                        if isinstance(chunk, str):
                            full_text += chunk
                            yield chunk
                        elif isinstance(chunk, dict) and "tool_calls" in chunk:
                            has_tool_calls = True
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": chunk["tool_calls"],
                                }
                            )
                            for tc in chunk["tool_calls"]:
                                try:
                                    kwargs = json.loads(tc["function"]["arguments"])
                                    result = self.registry.execute(
                                        tc["function"]["name"], kwargs
                                    )
                                except Exception as e:
                                    result = f"调用失败: {e}"
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc["id"],
                                        "content": str(result),
                                    }
                                )
                else:
                    for chunk in self.llm.generate_stream_sync(messages, max_tokens=4096):
                        full_text += chunk
                        yield chunk

                if not has_tool_calls:
                    break
        finally:
            if full_text.strip().startswith("【通过】"):
                bb.update(critic_feedback=full_text, status="done")
            else:
                bb.update(critic_feedback=full_text, status="drafting")
