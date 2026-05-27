"""HTTP 请求的 Vault 解析 — Obsidian / Web 客户端统一 X-Vault-Path 契约"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from fastapi import Request

from src.config import Config, config_from_headers, load_config

logger = logging.getLogger(__name__)

_CONFIG_HEADERS = (
    "x-vault-path", "x-llm-key", "x-embed-key", "x-brain-key", "x-mineru-token",
)


@dataclass
class VaultContext:
    """单次 HTTP 请求的 vault 环境（Config + 解析来源）"""

    vault_path: str
    config: Config
    source: str  # "header" | "env" | "detect"

    @property
    def db_path(self) -> str:
        return self.config.db_path


def _vault_source_without_header() -> str:
    if os.environ.get("LLM_WIKI_VAULT"):
        return "env"
    return "detect"


@lru_cache
def _default_config() -> Config:
    return load_config()


def resolve_from_request(request: Request) -> VaultContext:
    """从 HTTP 请求解析 vault — X-Vault-Path 优先，否则 fallback + warning。"""
    headers = {k.lower(): v for k, v in request.headers.items()}
    route = request.url.path
    vault_header = headers.get("x-vault-path", "").strip()

    if vault_header:
        cfg = config_from_headers(headers)
        return VaultContext(vault_path=cfg.vault_path, config=cfg, source="header")

    has_other_headers = any(headers.get(h) for h in _CONFIG_HEADERS if h != "x-vault-path")
    if has_other_headers:
        cfg = config_from_headers(headers)
    else:
        cfg = _default_config()

    source = _vault_source_without_header()
    logger.warning(
        "vault_fallback: route=%s source=%s vault_path=%s (missing X-Vault-Path header)",
        route,
        source,
        cfg.vault_path,
    )
    return VaultContext(vault_path=cfg.vault_path, config=cfg, source=source)


def normalize_doc_path(ctx: VaultContext, path: str) -> str:
    """API 传入路径 → vault 相对路径（正斜杠）。"""
    if not path:
        return path
    decoded = unquote(path).strip()
    return ctx.config.to_relpath(decoded)


def resolve_doc_path(ctx: VaultContext, relpath: str) -> str:
    """vault 相对路径 → 绝对路径（磁盘 I/O）。"""
    return ctx.config.to_abspath(relpath)
