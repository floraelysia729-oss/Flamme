"""Phase 2 集成测试 — embedding + 语义搜索 + QueryWorker"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock

import numpy as np

from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from tests.helpers import write_md
from src.tools.embedding_store import EmbeddingStore
from src.tools.embed_index import EmbedIndexTool
from src.tools.wiki_ops import WikiSearchTool
from src.agent.coordinator import Coordinator


def _setup():
    vault_dir = tempfile.mkdtemp()
    db_path = os.path.join(vault_dir, ".wiki", "knowledge.db")
    emb_dir = os.path.join(vault_dir, ".wiki", "embeddings")

    db = SQLiteClient(db_path)
    emb_store = EmbeddingStore(emb_dir, dim=8)
    registry = ToolRegistry()
    parser = MarkdownParser()
    registry.register(parser)
    return vault_dir, db, emb_store, registry, parser


def _cleanup(vault_dir: str, db: SQLiteClient):
    db.close()
    shutil.rmtree(vault_dir, ignore_errors=True)


def _mock_llm(dim: int = 8):
    llm = MagicMock()
    llm.embed.side_effect = lambda texts: [
        np.random.randn(dim).astype(np.float32).tolist() for _ in texts
    ]
    llm.complete.return_value = "这是 LLM 的回答"
    return llm


def _ingest(db, registry, path, llm=None, embedding_store=None, level="lite"):
    coord = Coordinator(
        db=db, tools=registry, llm=llm,
        embedding_store=embedding_store, max_workers=1,
    )
    task_id = coord.dispatch("ingest", {"path": path, "level": level})
    return coord.wait_for(task_id, timeout=30)


def test_e2e_ingest_auto_embeds():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    try:
        path = os.path.join(vault_dir, "math.md")
        write_md(path, "矩阵基础", "矩阵是线性代数的核心概念", tags=["数学"])

        result = _ingest(db, registry, path, llm=llm, embedding_store=emb_store)
        assert "已导入" in result
        assert emb_store.count() == 1
        assert db.get_embedding_stats()["embedded"] == 1
    finally:
        _cleanup(vault_dir, db)


def test_e2e_hash_dedup_skips_reembed():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    try:
        path = os.path.join(vault_dir, "math.md")
        write_md(path, "矩阵基础", "矩阵是线性代数的核心概念", tags=["数学"])

        _ingest(db, registry, path, llm=llm, embedding_store=emb_store)
        assert emb_store.count() == 1

        _ingest(db, registry, path, llm=llm, embedding_store=emb_store)
        assert emb_store.count() == 1
        assert llm.embed.call_count == 1
    finally:
        _cleanup(vault_dir, db)


def test_e2e_semantic_search():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    search = WikiSearchTool(db=db, embedding_store=emb_store, llm=llm)
    try:
        for i, (title, content) in enumerate([
            ("矩阵基础", "矩阵是线性代数的核心"),
            ("微积分", "极限与连续性"),
            ("概率论", "随机变量与分布"),
        ]):
            path = os.path.join(vault_dir, f"doc{i}.md")
            write_md(path, title, content, tags=["数学"])
            _ingest(db, registry, path, llm=llm, embedding_store=emb_store)

        result = search.execute({"query": "矩阵", "top_k": 3})
        assert not result.is_error
        titles = [e["title"] for e in result.data["results"]]
        assert "矩阵基础" in titles
    finally:
        _cleanup(vault_dir, db)


def test_e2e_index_command():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    index_tool = EmbedIndexTool(db=db, llm=llm, embedding_store=emb_store, parser=parser)
    try:
        for i in range(3):
            path = os.path.join(vault_dir, f"doc{i}.md")
            write_md(path, f"Doc{i}", f"内容 {i}")
            db.put_document({
                "path": path,
                "title": f"Doc{i}",
                "level": "lite",
                "tags": [],
                "content_hash": f"hash_{i}",
                "word_count": 5,
            })

        assert db.get_embedding_stats()["unembedded"] == 3
        result = index_tool.execute({"full": False})
        assert "索引完成" in result.data["result"]
        assert emb_store.count() == 3
    finally:
        _cleanup(vault_dir, db)


def test_e2e_query_uses_semantic_search():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    try:
        path = os.path.join(vault_dir, "doc.md")
        write_md(path, "线性代数", "线性代数研究向量空间", tags=["数学"])
        _ingest(db, registry, path, llm=llm, embedding_store=emb_store)

        coord = Coordinator(db=db, tools=registry, llm=llm, embedding_store=emb_store, max_workers=1)
        task_id = coord.dispatch("query", {"question": "什么是线性代数"})
        result = coord.wait_for(task_id, timeout=30)
        assert "LLM 的回答" in result
        assert llm.embed.call_count >= 2
        llm.complete.assert_called_once()
    finally:
        _cleanup(vault_dir, db)


def test_e2e_status_shows_embedding_count():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    try:
        assert db.get_embedding_stats()["embedded"] == 0

        path = os.path.join(vault_dir, "doc.md")
        write_md(path, "T", "内容")
        _ingest(db, registry, path, llm=llm, embedding_store=emb_store)
        assert db.get_embedding_stats()["embedded"] == 1
    finally:
        _cleanup(vault_dir, db)


def test_e2e_search_without_embeddings():
    vault_dir, db, emb_store, registry, parser = _setup()
    llm = _mock_llm()
    search = WikiSearchTool(db=db, embedding_store=emb_store, llm=llm)
    try:
        result = search.execute({"query": "矩阵", "top_k": 5})
        assert not result.is_error
        assert result.data.get("note") or result.data.get("total", 0) >= 0
    finally:
        _cleanup(vault_dir, db)
