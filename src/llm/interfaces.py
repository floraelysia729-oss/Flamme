"""LLM Provider 接口定义"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM 调用接口 — 智谱/千问/OpenAI 兼容"""

    def complete(self, messages: list[dict], **kwargs) -> str:
        """同步聊天补全，返回 assistant 文本"""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """生成 embedding 向量"""
        ...
