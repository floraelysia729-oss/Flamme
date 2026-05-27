"""Paths and wiki page migration tests."""

import os
import shutil
import tempfile
from pathlib import Path

from src.db.client import SQLiteClient
from src.scripts.migrate_wiki_pages import migrate_wiki_pages
from src.tools.paths import page_type_dir, topics_dir
from src.tools.wiki_ops import WikiCreatePageTool


def test_page_type_dir_creates_vault_level_topics():
    tmpdir = tempfile.mkdtemp()
    vault = Path(tmpdir) / "vault"
    vault.mkdir()
    try:
        d = topics_dir(vault)
        assert d == vault / "topics"
        assert d.is_dir()
        assert page_type_dir(vault, "comparison") == vault / "comparisons"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_migrate_wiki_pages_from_root_flamme():
    tmpdir = tempfile.mkdtemp()
    vault = Path(tmpdir) / "vault"
    legacy = vault / ".flamme" / "topics"
    legacy.mkdir(parents=True)
    (legacy / "旧主题.md").write_text("---\ntitle: 旧主题\ntype: topic\n---\n", encoding="utf-8")

    db_path = vault / ".wiki" / "knowledge.db"
    db_path.parent.mkdir(parents=True)
    db = SQLiteClient(str(db_path))
    db.put_document({
        "path": ".flamme/topics/旧主题.md",
        "title": "旧主题",
        "level": "pro",
        "status": "draft",
        "content_hash": "x",
        "word_count": 1,
        "tags": [],
    })
    db.close()

    try:
        migrate_wiki_pages(vault, cleanup=True, update_db=True)
        assert (vault / "topics" / "旧主题.md").is_file()
        assert not (vault / ".flamme").exists()

        db = SQLiteClient(str(db_path))
        doc = db.get_document("topics/旧主题.md")
        assert doc is not None
        assert doc["title"] == "旧主题"
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_wiki_create_comparison_page_path():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)

    db = SQLiteClient(db_path)
    tool = WikiCreatePageTool(db=db, vault_path=vault)
    try:
        result = tool.execute({
            "title": "对比页",
            "type": "comparison",
            "content": "正文",
        })
        assert not result.is_error
        rel = result.data["path"].replace("\\", "/")
        assert "comparisons/" in rel
        assert ".flamme" not in rel
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
