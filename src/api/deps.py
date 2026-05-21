"""FastAPI 依赖注入 — lru_cache 单例 + per-request Config"""

from functools import lru_cache

from fastapi import Request

from src.config import load_config, config_from_headers, Config
from src.db.client import SQLiteClient
from src.tools.bootstrap import build_registry
from src.tools.registry import ToolRegistry
from src.tools.embedding_store import EmbeddingStore
from src.llm.provider import DefaultLLM
from src.llm.queue import LLMQueue


@lru_cache
def get_config() -> Config:
    return load_config()


@lru_cache
def get_db() -> SQLiteClient:
    cfg = get_config()
    return SQLiteClient(cfg.db_path, vault_path=cfg.vault_path)


@lru_cache
def get_tool_registry() -> ToolRegistry:
    """统一注册入口 — 调用 bootstrap.build_registry()"""
    return build_registry(
        config=get_config(),
        db=get_db(),
        llm=get_llm(),
        embedding_store=get_embedding_store(),
    )


@lru_cache
def get_embedding_store() -> EmbeddingStore:
    cfg = get_config()
    return EmbeddingStore(cfg.embeddings_dir, dim=cfg.embed_dim)


@lru_cache
def get_llm() -> DefaultLLM | None:
    cfg = get_config()
    if not cfg.llm_api_key and not cfg.embed_api_key:
        return None
    return DefaultLLM(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        model=cfg.llm_model,
        embed_api_key=cfg.embed_api_key,
        embed_base_url=cfg.embed_base_url,
        embed_model=cfg.embed_model,
    )


@lru_cache
def get_brain_llm() -> DefaultLLM | None:
    """GLM 5.1 — Orchestrator 专用"""
    cfg = get_config()
    if not cfg.brain_api_key:
        return None
    return DefaultLLM(
        api_key=cfg.brain_api_key,
        base_url=cfg.brain_base_url,
        model=cfg.brain_model,
        embed_api_key=cfg.embed_api_key,
        embed_base_url=cfg.embed_base_url,
        embed_model=cfg.embed_model,
    )


@lru_cache
def get_llm_queue() -> LLMQueue | None:
    llm = get_llm()
    if not llm:
        return None
    return LLMQueue(max_concurrency=get_config().max_concurrency)


# ── Per-request: 从插件 header 构建 Config + LLM ──

def get_request_config(request: Request) -> Config:
    """从请求 header 读取用户 API key，构建 per-request Config"""
    return config_from_headers(dict(request.headers))


def get_request_config_or_default(request: Request) -> Config:
    """有配置 header 时返回 per-request Config，否则返回 cached 默认 Config"""
    headers = dict(request.headers)
    # 检查是否有任何插件配置 header
    has_overrides = any(headers.get(h) for h in (
        "x-vault-path", "x-llm-key", "x-embed-key", "x-brain-key", "x-mineru-token"
    ))
    if has_overrides:
        return config_from_headers(headers)
    return get_config()


def build_llm_from_config(cfg: Config) -> DefaultLLM | None:
    """从给定 Config 构建 LLM 实例（非缓存）"""
    if not cfg.llm_api_key:
        return None
    return DefaultLLM(
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url,
        model=cfg.llm_model,
        embed_api_key=cfg.embed_api_key,
        embed_base_url=cfg.embed_base_url,
        embed_model=cfg.embed_model,
    )


def build_brain_llm_from_config(cfg: Config) -> DefaultLLM | None:
    """从给定 Config 构建 Brain LLM 实例（非缓存）"""
    if not cfg.brain_api_key:
        return None
    return DefaultLLM(
        api_key=cfg.brain_api_key,
        base_url=cfg.brain_base_url,
        model=cfg.brain_model,
        embed_api_key=cfg.embed_api_key,
        embed_base_url=cfg.embed_base_url,
        embed_model=cfg.embed_model,
    )
