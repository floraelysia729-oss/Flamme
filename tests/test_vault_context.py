"""VaultContext 单元测试"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.api.vault_context import (
    VaultContext,
    normalize_doc_path,
    resolve_doc_path,
    resolve_from_request,
)


def _mock_request(headers: dict | None = None, path: str = "/api/status"):
    req = MagicMock()
    req.headers = headers or {}
    req.url.path = path
    return req


def test_resolve_from_header(tmp_path, monkeypatch):
    vault = tmp_path / "my-vault"
    vault.mkdir()
    monkeypatch.delenv("LLM_WIKI_VAULT", raising=False)

    ctx = resolve_from_request(_mock_request({"x-vault-path": str(vault)}))
    assert ctx.source == "header"
    assert Path(ctx.vault_path).resolve() == vault.resolve()
    assert ctx.db_path.endswith("knowledge.db")


def test_resolve_fallback_env(tmp_path, monkeypatch):
    from src.api import vault_context

    vault = tmp_path / "env-vault"
    vault.mkdir()
    monkeypatch.setenv("LLM_WIKI_VAULT", str(vault))
    monkeypatch.setattr("src.config._load_dotenv", lambda: None)
    vault_context._default_config.cache_clear()

    ctx = resolve_from_request(_mock_request({}))
    assert ctx.source == "env"
    assert Path(ctx.vault_path).resolve() == vault.resolve()
    vault_context._default_config.cache_clear()


def test_normalize_and_resolve(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    from src.config import Config

    cfg = Config(vault_path=str(vault))
    ctx = VaultContext(vault_path=str(vault), config=cfg, source="header")

    rel = normalize_doc_path(ctx, str(vault / "notes" / "a.md"))
    assert rel == "notes/a.md"

    rel2 = normalize_doc_path(ctx, "notes\\b.md")
    assert rel2 == "notes/b.md"

    abs_path = resolve_doc_path(ctx, "notes/a.md")
    assert Path(abs_path) == vault / "notes" / "a.md"
