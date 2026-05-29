"""Vault 运维后端测试 — scanner / planner / API"""

import os
import shutil
import tempfile

from fastapi.testclient import TestClient

from src.config import Config
from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.vault.scanner import scan_vault
from src.vault.planner import build_plan
from src.vault.runner import run_vault
from src.vault.baseline import load_baseline, save_baseline
from src.agent.coordinator import Coordinator
from tests.helpers import write_md


def _make_config(vault_dir: str) -> Config:
    return Config(vault_path=vault_dir)


def _setup(vault_dir: str):
    db_path = os.path.join(vault_dir, ".wiki", "knowledge.db")
    db = SQLiteClient(db_path, vault_path=vault_dir)
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    cfg = _make_config(vault_dir)
    coord = Coordinator(db=db, tools=registry, max_workers=1)
    return cfg, db, registry, coord


def test_scan_detects_new_md_and_binary():
    vault_dir = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(vault_dir, "线代"), exist_ok=True)
        md_path = os.path.join(vault_dir, "线代", "笔记.md")
        write_md(md_path, "笔记", "内容", level="source")
        pdf_path = os.path.join(vault_dir, "线代", "课件.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 fake")

        _, db, _, _ = _setup(vault_dir)
        try:
            scan = scan_vault(vault_dir, db)
            assert any("笔记.md" in p for p in scan["md_new"])
            assert any("课件.pdf" in p for p in scan["binary_unprocessed"])
            assert scan["binary_total"] == 1
        finally:
            db.close()
    finally:
        shutil.rmtree(vault_dir, ignore_errors=True)


def test_plan_after_ingest_index():
    vault_dir = tempfile.mkdtemp()
    try:
        md_path = os.path.join(vault_dir, "hello.md")
        write_md(md_path, "Hello", "world", level="source")

        cfg, db, registry, coord = _setup(vault_dir)
        try:
            result = run_vault(cfg, db, coord, registry, preset="index", embed=False, graph=False)
            assert "error" not in result
            assert any(s["step"] == "sync" for s in result["steps"])
            assert load_baseline(cfg.wiki_dir) is not None

            plan = build_plan(vault_dir, cfg.wiki_dir, db)
            assert db.get_document("hello.md") is not None
            assert plan["scan"]["md_new"] == []
        finally:
            db.close()
    finally:
        shutil.rmtree(vault_dir, ignore_errors=True)


def test_vault_api_plan_and_status():
    # 使用项目内 ASCII 路径，避免 Windows 用户目录中文导致 TestClient header 编码失败
    vault_dir = os.path.join(os.path.dirname(__file__), "fixtures", "_vault_api")
    shutil.rmtree(vault_dir, ignore_errors=True)
    os.makedirs(vault_dir, exist_ok=True)
    try:
        write_md(os.path.join(vault_dir, "a.md"), "A", "content", level="source")

        from src.api.app import app
        client = TestClient(app)
        headers = {"X-Vault-Path": vault_dir}

        status = client.get("/api/vault/status", headers=headers)
        assert status.status_code == 200
        body = status.json()
        assert body["vault_path"] == vault_dir
        assert "presets" in body

        plan = client.get("/api/vault/plan", headers=headers)
        assert plan.status_code == 200
        pdata = plan.json()
        assert pdata["pending_count"] >= 1
        assert "sync" in pdata["actions"]
    finally:
        shutil.rmtree(vault_dir, ignore_errors=True)

def test_purge_missing_only_touches_db():
    vault_dir = tempfile.mkdtemp()
    try:
        md_path = os.path.join(vault_dir, "keep.md")
        write_md(md_path, "Keep", "body", level="source")
        _, db, _, _ = _setup(vault_dir)
        try:
            db.put_document({
                "path": "gone.md", "title": "Gone", "level": "source",
                "content_hash": "x", "word_count": 1, "tags": [],
            })
            deleted = db.purge_missing()
            assert "gone.md" in deleted
            assert os.path.isfile(md_path)
        finally:
            db.close()
    finally:
        shutil.rmtree(vault_dir, ignore_errors=True)


def test_baseline_save_load():
    wiki = tempfile.mkdtemp()
    try:
        data = save_baseline(wiki, git_commit="abc123", preset="test", summary={"n": 1})
        assert data["git_commit"] == "abc123"
        loaded = load_baseline(wiki)
        assert loaded["preset"] == "test"
    finally:
        shutil.rmtree(wiki, ignore_errors=True)
