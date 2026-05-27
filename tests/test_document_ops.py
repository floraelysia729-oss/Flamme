"""document_ops 单元测试"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.tools.wiki_ops import WikiReadPageTool, WikiSearchTool
from src.api.document_ops import filter_documents, paginate, read_document, search_documents
from src.api.vault_context import VaultContext
from src.config import Config


@pytest.fixture
def vault_db():
    tmpdir = tempfile.mkdtemp()
    vault = os.path.join(tmpdir, "vault")
    os.makedirs(vault)
    md = Path(vault) / "notes" / "alpha.md"
    md.parent.mkdir(parents=True)
    md.write_text("---\ntitle: Alpha\ntags: [math]\nlevel: lite\n---\n\n# Alpha\n", encoding="utf-8")
    Path(vault, "notes", "beta.md").write_text(
        "---\ntitle: Beta\nlevel: pro\n---\n\n# Beta\n", encoding="utf-8"
    )
    db_path = os.path.join(tmpdir, "test.db")
    db = SQLiteClient(db_path, vault_path=vault)
    db.put_document({
        "path": "notes/alpha.md", "title": "Alpha", "level": "lite",
        "tags": ["math"], "content_hash": "a", "word_count": 10,
    })
    db.put_document({
        "path": "notes/beta.md", "title": "Beta", "level": "pro",
        "tags": [], "content_hash": "b", "word_count": 10,
    })
    registry = ToolRegistry()
    registry.register(WikiReadPageTool(db, parser=MarkdownParser()))
    registry.register(WikiSearchTool(db, embedding_store=None, llm=None))
    cfg = Config(vault_path=vault)
    ctx = VaultContext(vault_path=vault, config=cfg, source="header")
    yield ctx, db, registry
    db.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_filter_and_paginate(vault_db):
    _ctx, db, _ = vault_db
    docs = filter_documents(db, search="alpha")
    assert len(docs) == 1
    assert docs[0]["title"] == "Alpha"

    docs = filter_documents(db, tag="math")
    assert len(docs) == 1

    page, total = paginate(filter_documents(db), page=1, per_page=1)
    assert total == 2
    assert len(page) == 1


def test_read_document(vault_db):
    ctx, db, registry = vault_db
    result = read_document(ctx, db, registry, "notes/alpha.md")
    assert result["title"] == "Alpha"
    assert "Alpha" in result["content"]
    assert result["metadata"]["path"] == "notes/alpha.md"

    missing = read_document(ctx, db, registry, "missing.md")
    assert missing["error"] == "not found"

    abs_path = str(Path(db._vault_path) / "notes" / "alpha.md")
    result2 = read_document(ctx, db, registry, abs_path)
    assert result2["title"] == "Alpha"


def test_search_documents_fallback_list(vault_db):
    _ctx, _db, registry = vault_db
    result = search_documents(registry, "anything", top_k=5)
    assert "results" in result
    assert result["total"] >= 1
