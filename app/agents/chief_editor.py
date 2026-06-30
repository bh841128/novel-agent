import json
import logging

from app.agents.blackboard import Blackboard
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = frozenset({"call_planner", "call_writer", "call_critic", "finish"})

CHIEF_EDITOR_PROMPT = """你是一个总编兼总调度（Orchestrator）。
当前小说的状态和阶段性产出记录在黑板（Blackboard）中。
请仔细阅读当前的大纲或草稿内容，决定下一步调用哪个 Agent。
必须且只能返回以下 JSON 格式：
{
  "thought": "你对当前文本质量的思考和评价，为什么要做这个决定",
  "directive": "你要下达给被唤醒 Agent 的具体修改指令或提醒（如果不需修改，可以只写'按原计划继续'）",
  "action": "call_planner" | "call_writer" | "call_critic" | "finish"
}

判断逻辑建议：
- 如果尚未有大纲，调用 call_planner
- 如果大纲内容严重跑题、缺乏核心冲突，请在 directive 中指出，并返回 call_planner 重写
- 如果大纲合格，调用 call_writer
- 如果已有草稿，但尚未经过审阅，调用 call_critic
- 如果审阅已通过（或你认为内容已足够完美），调用 finish 结束流程
"""


def _normalize_action(action: object) -> str:
    if isinstance(action, str) and action in ALLOWED_ACTIONS:
        return action
    logger.warning(f"ChiefEditor received invalid action {action}; defaulting to finish")
    return "finish"


class ChiefEditorAgent:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def decide_next_action_stream(self, blackboard: Blackboard):
        """流式返回思考过程，最终 yield 一个包含 (action, thought, directive) 的 tuple"""
        outline_preview = blackboard.outline[:2000] + (
            "..." if len(blackboard.outline) > 2000 else ""
        )
        draft_preview = blackboard.draft[:2000] + (
            "..." if len(blackboard.draft) > 2000 else ""
        )

        bb_state = (
            f"【当前黑板状态】\n"
            f"- 目标提示词: {blackboard.current_prompt}\n"
            f"- 当前流程状态: {blackboard.status}\n\n"
            f"【当前产出】\n"
            f"- 大纲 (前2000字): {outline_preview if outline_preview else '暂无'}\n\n"
            f"- 草稿 (前2000字): {draft_preview if draft_preview else '暂无'}\n\n"
            f"【历史审阅反馈】\n"
            f"- {blackboard.critic_feedback if blackboard.critic_feedback else '无'}"
        )

        messages = [
            {"role": "system", "content": CHIEF_EDITOR_PROMPT},
            {"role": "user", "content": bb_state},
        ]

        full_text = ""
        try:
            for chunk in self.llm.generate_stream_sync(messages, max_tokens=1000):
                full_text += chunk
                yield chunk

            start = full_text.find("{")
            end = full_text.rfind("}") + 1
            if start != -1 and end != 0:
                data = json.loads(full_text[start:end])
                action = _normalize_action(data.get("action", "finish"))
                thought = data.get("thought", "")
                directive = data.get("directive", "")
                yield (action, thought, directive)
            else:
                logger.warning("ChiefEditor could not find JSON object; defaulting to finish")
                yield ("finish", "解析 JSON 失败", "无批示")
        except Exception as e:
            logger.exception("ChiefEditor error")
            yield ("finish", f"发生异常: {str(e)}", "无批示")
