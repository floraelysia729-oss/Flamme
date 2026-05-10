"""LLM Provider — 支持 chat 和 embed 分开配置不同供应商

TS 映射: 同名 class, openai npm SDK, 同样的 messages 格式
"""

from openai import OpenAI

from src.llm.interfaces import LLMProvider


class DefaultLLM:
    """通用 LLM Provider — chat 和 embed 可分别配置

    - chat 走 llm_base_url + llm_model
    - embed 走 embed_base_url（默认同 llm_base_url）+ embed_model
    """

    def __init__(self, api_key: str, base_url: str, model: str = "glm-4-flash",
                 embed_api_key: str = "", embed_base_url: str = "",
                 embed_model: str = "text-embedding-v3"):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._embed_model = embed_model

        # embed 可以用不同的 key/url（千问 DashScope）
        emb_key = embed_api_key or api_key
        emb_url = embed_base_url or base_url
        if emb_key == api_key and emb_url == base_url:
            self._embed_client = self._client
        else:
            self._embed_client = OpenAI(api_key=emb_key, base_url=emb_url)

    def complete(self, messages: list[dict], **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=kwargs.get("model", self._model),
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        return response.choices[0].message.content or ""

    def stream_complete(self, messages: list[dict], **kwargs):
        """流式生成，逐 token yield"""
        stream = self._client.chat.completions.create(
            model=kwargs.get("model", self._model),
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def chat_with_tools(self, messages: list[dict], tools: list[dict],
                        tool_choice: str = "auto", **kwargs) -> dict:
        """带 function calling 的聊天，返回原始 response 对象"""
        response = self._client.chat.completions.create(
            model=kwargs.get("model", self._model),
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        return response

    def stream_chat_with_tools(self, messages: list[dict], tools: list[dict],
                               tool_choice: str = "auto", **kwargs):
        """带 function calling 的流式聊天

        如果有 tool_calls，第一个 chunk 会携带 tool_call 信息。
        如果无 tool_calls，流式输出文本 token。
        """
        stream = self._client.chat.completions.create(
            model=kwargs.get("model", self._model),
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            stream=True,
        )
        return stream

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._embed_client.embeddings.create(
            model=self._embed_model,
            input=texts,
        )
        return [item.embedding for item in response.data]
