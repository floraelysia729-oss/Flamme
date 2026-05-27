"""FastAPI 依赖注入 — per-request Config + LLM builder"""

from functools import lru_cache

from fastapi import Request

from src.config import load_config, config_from_headers, Config
from src.llm.provider import DefaultLLM
from src.api.vault_context import VaultContext, resolve_from_request


@lru_cache
def get_config() -> Config:
    """进程默认 Config — 无插件 header 时的 fallback（dev/CLI）"""
    return load_config()


def get_vault_context(request: Request) -> VaultContext:
    """HTTP 请求 vault 环境 — X-Vault-Path 优先"""
    return resolve_from_request(request)


def get_request_config(request: Request) -> Config:
    """从请求 header 读取用户 API key，构建 per-request Config"""
    return config_from_headers(dict(request.headers))


def get_request_config_or_default(request: Request) -> Config:
    """经 VaultContext 解析 Config（含 vault 来源与 fallback warning）"""
    return get_vault_context(request).config


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
