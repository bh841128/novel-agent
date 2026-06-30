import sys
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from openai import AsyncOpenAI, OpenAI

LLM_TIMEOUT = 300  # 5 分钟超时


def _log(msg: str):
    print(f"[LLM] {msg}", flush=True, file=sys.stderr)


class LLMService:
    """通过 OpenAI 兼容 API 调用 LLM，支持同步/异步流式输出。

    传入 base_url="stub" 用于测试，不会创建真实客户端。
    """

    def __init__(self, base_url: str, api_key: str, model: str):
        self.model = model
        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

        if base_url != "stub":
            self._client = OpenAI(
                base_url=base_url, api_key=api_key, timeout=LLM_TIMEOUT, max_retries=2
            )
            self._async_client = AsyncOpenAI(
                base_url=base_url, api_key=api_key, timeout=LLM_TIMEOUT, max_retries=2
            )

    @staticmethod
    def _log_prompt(messages: list[dict], max_tokens: int, stream: bool, tools: list[dict] | None = None):
        roles = [m.get("role", "?") for m in messages]
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        tools_info = f" tools={len(tools)}" if tools else ""
        _log(f">>> roles={roles} chars={total_chars} max_tokens={max_tokens} stream={stream}{tools_info}")

    def generate_stream_sync(
        self, messages: list[dict], max_tokens: int = 4096
    ) -> Iterator[str]:
        assert self._client is not None, "Client not initialized (stub mode)"
        self._log_prompt(messages, max_tokens, stream=True)
        t0 = time.time()
        token_count = 0
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        token_count += 1
                        yield delta.content
            elapsed = time.time() - t0
            _log(f"<<< stream done chunks={token_count} {elapsed:.1f}s")
        except Exception as e:
            _log(f"\n[LLM Stream Error]: {str(e)}\n")
            raise e

    def generate_sync(self, messages: list[dict], max_tokens: int = 4096) -> str:
        """内部使用流式请求以防止长文本阻塞静默，并将进度打印到控制台。"""
        assert self._client is not None, "Client not initialized (stub mode)"
        self._log_prompt(messages, max_tokens, stream=True)
        t0 = time.time()
        
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                stream=True,
            )
            result_chunks = []
            for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        result_chunks.append(delta.content)
                        sys.stdout.write(delta.content)
                        sys.stdout.flush()
            sys.stdout.write("\n")
            sys.stdout.flush()
            result = "".join(result_chunks)
            elapsed = time.time() - t0
            _log(f"<<< sync done len={len(result)} {elapsed:.1f}s")
            return result
        except Exception as e:
            sys.stdout.write(f"\n[LLM Error]: {str(e)}\n")
            sys.stdout.flush()
            raise e

    def generate_with_tools_sync(
        self, messages: list[dict], tools: list[dict], max_tokens: int = 4096
    ) -> dict[str, Any]:
        """同步调用，支持工具。返回完整的 message 字典（包含 content 和 tool_calls）。"""
        assert self._client is not None, "Client not initialized (stub mode)"
        self._log_prompt(messages, max_tokens, stream=False, tools=tools)
        t0 = time.time()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            tools=tools,
        )
        msg = resp.choices[0].message
        result = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in msg.tool_calls
            ]
        elapsed = time.time() - t0
        _log(f"<<< sync_with_tools done len={len(result['content'])} tool_calls={len(result.get('tool_calls', []))} {elapsed:.1f}s")
        return result

    def generate_stream_with_tools_sync(
        self, messages: list[dict], tools: list[dict], max_tokens: int = 8192
    ) -> Iterator[str | dict[str, Any]]:
        """
        同步流式调用，支持工具。
        生成文本时 yield 字符串 chunk。
        如果遇到 tool_calls，则在收集完整后 yield 一个包含 tool_calls 的字典: {"tool_calls": [...]}
        """
        assert self._client is not None, "Client not initialized (stub mode)"
        self._log_prompt(messages, max_tokens, stream=True, tools=tools)
        t0 = time.time()
        token_count = 0
        
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            tools=tools,
        )
        
        tool_calls = []
        
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            
            if delta.content:
                token_count += 1
                yield delta.content
                
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    while len(tool_calls) <= tc.index:
                        tool_calls.append({
                            "id": "", 
                            "type": "function", 
                            "function": {"name": "", "arguments": ""}
                        })
                    if tc.id:
                        tool_calls[tc.index]["id"] = tc.id
                    if tc.function.name:
                        tool_calls[tc.index]["function"]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

        if tool_calls:
            yield {"tool_calls": tool_calls}

        elapsed = time.time() - t0
        _log(f"<<< stream_with_tools done chunks={token_count} tool_calls={len(tool_calls)} {elapsed:.1f}s")

    # Async versions kept original as they are currently unused by the agents but good to have
    async def generate_stream(
        self, messages: list[dict], max_tokens: int = 4096
    ) -> AsyncIterator[str]:
        assert self._async_client is not None, "Async client not initialized (stub mode)"
        self._log_prompt(messages, max_tokens, stream=True)
        t0 = time.time()
        token_count = 0
        stream = await self._async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    token_count += 1
                    yield delta.content
        elapsed = time.time() - t0
        _log(f"<<< async stream done chunks={token_count} {elapsed:.1f}s")

    async def generate(self, messages: list[dict], max_tokens: int = 4096) -> str:
        assert self._async_client is not None, "Async client not initialized (stub mode)"
        self._log_prompt(messages, max_tokens, stream=False)
        t0 = time.time()
        resp = await self._async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        result = resp.choices[0].message.content or "" if resp.choices else ""
        elapsed = time.time() - t0
        _log(f"<<< async done len={len(result)} {elapsed:.1f}s")
        return result
