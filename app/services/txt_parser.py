"""TXT 小说智能切分模块。

先用内置正则快速匹配常见章节格式，匹配不到时调 LLM 分析前 N 行
推断章节标题正则，再用该正则切分全文。
"""
from __future__ import annotations

import re

from app.services.llm_service import LLMService

BUILTIN_PATTERNS: list[str] = [
    r"^([^卷]{0,20}卷\s+)?(第[0-9０-９零一二三四五六七八九十百千万]+[章回节日]|章[0-9０-９零一二三四五六七八九十百千万]+|[0-9０-９零一二三四五六七八九十百千万]+章|(序|终|楔)章|楔子|外传|附录)[\s:：\.]?[^\n]{0,30}$",
    r"^Chapter\s+\d+",
]

MIN_CHAPTER_MATCHES = 3
SAMPLE_HEAD_LINES = 1000
SAMPLE_TAIL_LINES = 1000
MIN_CHAPTER_TEXT_LEN = 50

LLM_PROMPT_TEMPLATE = """你是一个文本分析专家。分析以下小说文本片段，找出章节标题行的格式规律。

要求：
1. 返回一个 Python 正则表达式，能匹配所有章节标题所在的行（行首匹配）
2. 只返回正则表达式本身，不要加引号、反引号或任何解释
3. 正则必须以 ^ 开头
4. 不要匹配卷标记（如"第X卷"）
5. 【重要】绝不能将横线、等号、星号等纯分隔符（如"----"、"***"、"==="）识别为章节标题！章节标题通常包含文字或数字！
6. 如果存在多种章节格式，请返回一个使用 | 组合的正则表达式以兼容它们。

文本片段（包含开头和结尾的样本）：
{text}"""


class TxtParser:
    """TXT 小说章节切分器。"""

    def __init__(self, llm: LLMService | None = None):
        self.llm = llm

    def detect_pattern(self, lines: list[str]) -> str | None:
        """检测章节标题正则。先试内置，再试 LLM。"""
        head_sample = lines[:SAMPLE_HEAD_LINES]
        tail_sample = lines[-SAMPLE_TAIL_LINES:] if len(lines) > SAMPLE_HEAD_LINES else []
        sample_lines = head_sample + tail_sample

        sample = [l.strip() for l in sample_lines if l.strip()]

        for pattern in BUILTIN_PATTERNS:
            matches = [l for l in sample if re.match(pattern, l)]
            if len(matches) >= MIN_CHAPTER_MATCHES:
                return pattern

        if self.llm:
            return self._llm_detect(sample_lines)
        return None

    def _llm_detect(self, head_lines: list[str]) -> str | None:
        """调 LLM 分析章节格式，返回正则。最多重试一次。"""
        text_block = "".join(head_lines[:SAMPLE_HEAD_LINES])
        if len(head_lines) > SAMPLE_HEAD_LINES:
            text_block += "\n\n... (中间省略) ...\n\n"
            text_block += "".join(head_lines[SAMPLE_HEAD_LINES:])

        prompt = LLM_PROMPT_TEMPLATE.format(text=text_block)

        for attempt in range(2):
            raw = self.llm.generate_sync(
                [{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            pattern = self._clean_pattern(raw)
            if not pattern:
                prompt += "\n\n上次返回的正则无法编译或被判定为纯分隔符，请重新分析并返回一个合法的包含文字/数字的 Python 正则。"
                continue

            matches = [l for l in head_lines if re.match(pattern, l.strip())]
            if len(matches) >= MIN_CHAPTER_MATCHES:
                return pattern

            prompt += f"\n\n上次返回的正则只匹配到 {len(matches)} 行，太少了。请重新分析。"

        return None

    @staticmethod
    def _clean_pattern(raw: str) -> str | None:
        """清理 LLM 返回的正则，验证合法性。"""
        s = raw.strip()
        for wrapper in ['```python', '```', '`']:
            s = s.removeprefix(wrapper).removesuffix(wrapper.rstrip('python'))
        s = s.strip().strip('"').strip("'").strip()
        if not s:
            return None
        try:
            re.compile(s)
            if re.match(r"^[\^\$\.\*\+\-\=\s\\]+$", s):
                return None
            return s
        except re.error:
            return None

    def split(self, full_text: str) -> list[dict]:
        """完整流程：检测格式 → 切分 → 返回 chapters JSON。

        Returns:
            [{"start_line": N, "title": "第X章 标题", "text": "正文..."}, ...]

        Raises:
            ValueError: 无法检测到章节格式
        """
        lines = full_text.splitlines(keepends=True)
        pattern = self.detect_pattern(lines)
        if not pattern:
            raise ValueError(
                '无法自动检测章节格式。请确认文件包含标准章节标题（如"第1章 xxx"），'
                '或先手动转成 JSON 格式后上传。'
            )
        return self._split_by_pattern(lines, pattern)

    def _split_by_pattern(self, lines: list[str], pattern: str) -> list[dict]:
        """用正则按行匹配切分。"""
        chapters: list[dict] = []
        current_title: str | None = None
        current_lines: list[str] = []
        current_start: int = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(pattern, stripped):
                if current_title is not None:
                    text = self._join_text(current_lines)
                    if len(text) >= MIN_CHAPTER_TEXT_LEN:
                        chapters.append({
                            "start_line": current_start + 1,
                            "title": current_title,
                            "text": text,
                        })
                current_title = stripped
                current_lines = []
                current_start = i
            elif current_title is not None:
                current_lines.append(line)

        if current_title is not None:
            text = self._join_text(current_lines)
            if len(text) >= MIN_CHAPTER_TEXT_LEN:
                chapters.append({
                    "start_line": current_start + 1,
                    "title": current_title,
                    "text": text,
                })

        return chapters

    @staticmethod
    def _join_text(lines: list[str]) -> str:
        """合并正文行，清理首尾空行和分隔线。"""
        text = "".join(lines).strip()
        text = re.sub(r"^[-=\*]{3,}\s*$", "", text, flags=re.MULTILINE)
        return text.strip()
