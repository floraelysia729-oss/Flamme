"""Phase 2 端到端集成测试 — embedding + 语义搜索 + query 增强"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock

import numpy as np

from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.tools.markdown_writer import MarkdownWriter
from src.tools.embedding_store import EmbeddingStore
from src.agent.agent import Agent
from src.agent.router import Router


def _setup():
    """创建临时 vault + 数据库 + embedding store"""
    vault_dir = tempfile.mkdtemp()
    db_path = os.path.join(vault_dir, ".wiki", "knowledge.db")
    emb_dir = os.path.join(vault_dir, ".wiki", "embeddings")

    db = SQLiteClient(db_path)
    emb_store = EmbeddingStore(emb_dir, dim=8)
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    registry.register(MarkdownWriter())

    return vault_dir, db, emb_store, registry


def _cleanup(vault_dir: str, db: SQLiteClient):
    db.close()
    shutil.rmtree(vault_dir, ignore_errors=True)


def _mock_llm(dim: int = 8):
    """返回一个 mock LLM，embed 返回随机向量"""
    llm = MagicMock()
    llm.embed.side_effect = lambda texts: [
        np.random.randn(dim).astype(np.float32).tolist() for _ in texts
    ]
    llm.complete.return_value = "这是 LLM 的回答"
    return llm


def test_e2e_ingest_auto_embeds():
    """ingest 时自动生成 embedding"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        # 创建并导入文件
        path = os.path.join(vault_dir, "math.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "矩阵基础", "date": "2026-04-22", "level": "lite", "tags": ["数学"]},
            "content": "矩阵是线性代数的核心概念",
        })

        result = agent.run(f'ingest "{path}"')
        assert "已导入" in result
        assert "已索引" in result

        # 验证 embedding 已生成
        assert emb_store.count() == 1
        llm.embed.assert_called_once()

        # 验证 SQLite embedding 记录
        stats = db.get_embedding_stats()
        assert stats["embedded"] == 1
        assert stats["unembedded"] == 0
    finally:
        _cleanup(vault_dir, db)


def test_e2e_hash_dedup_skips_reembed():
    """同一文件 ingest 两次不重复生成 embedding"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        path = os.path.join(vault_dir, "math.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "矩阵基础", "date": "2026-04-22", "level": "lite", "tags": ["数学"]},
            "content": "矩阵是线性代数的核心概念",
        })

        agent.run(f'ingest "{path}"')
        assert emb_store.count() == 1

        # 第二次 ingest（内容不变，hash 相同）
        result = agent.run(f'ingest "{path}"')
        assert "跳过" in result
        assert emb_store.count() == 1  # 没有增加
        assert llm.embed.call_count == 1  # 没有多调用
    finally:
        _cleanup(vault_dir, db)


def test_e2e_semantic_search():
    """语义搜索返回相关文档"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        # 导入 3 个文档
        for i, (title, content) in enumerate([
            ("矩阵基础", "矩阵是线性代数的核心"),
            ("微积分", "极限与连续性"),
            ("概率论", "随机变量与分布"),
        ]):
            path = os.path.join(vault_dir, f"doc{i}.md")
            MarkdownWriter().execute({
                "path": path,
                "metadata": {"title": title, "date": "2026-04-22", "level": "lite", "tags": ["数学"]},
                "content": content,
            })
            agent.run(f'ingest "{path}"')

        assert emb_store.count() == 3

        # 搜索
        result = agent.run('search "矩阵"')
        assert "语义搜索" in result
        assert "矩阵基础" in result
    finally:
        _cleanup(vault_dir, db)


def test_e2e_index_command():
    """index 命令批量为未索引文档生成 embedding"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        # 直接写 SQLite（不触发 embedding）
        for i in range(3):
            path = os.path.join(vault_dir, f"doc{i}.md")
            MarkdownWriter().execute({
                "path": path,
                "metadata": {"title": f"Doc{i}", "date": "2026-04-22", "level": "lite", "tags": []},
                "content": f"内容 {i}",
            })
            # 手动写入 SQLite，绕过自动 embedding
            db.put_document({
                "path": path,
                "title": f"Doc{i}",
                "level": "lite",
                "tags": [],
                "content_hash": f"hash_{i}",
                "word_count": 5,
            })

        # 验证 0 个 embedding
        assert db.get_embedding_stats()["unembedded"] == 3

        # 执行 index
        result = agent.run("index")
        assert "索引完成" in result
        assert emb_store.count() == 3
    finally:
        _cleanup(vault_dir, db)


def test_e2e_query_uses_semantic_search():
    """query 命令优先使用语义检索而非全量文档列表"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        # 导入文档
        path = os.path.join(vault_dir, "doc.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "线性代数", "date": "2026-04-22", "level": "lite", "tags": ["数学"]},
            "content": "线性代数研究向量空间",
        })
        agent.run(f'ingest "{path}"')

        # query 应该触发 embed（query embedding）+ complete（LLM 回答）
        result = agent.run("什么是线性代数")
        assert "LLM 的回答" in result
        # embed 被调用了：一次 ingest + 一次 query
        assert llm.embed.call_count == 2
        # complete 被调用了
        llm.complete.assert_called_once()

        # 验证 complete 的 system prompt 包含语义检索上下文
        call_args = llm.complete.call_args
        system_msg = call_args[0][0][0]["content"]
        assert "线性代数" in system_msg
    finally:
        _cleanup(vault_dir, db)


def test_e2e_status_shows_embedding_count():
    """status 命令显示向量索引统计"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        result = agent.run("status")
        assert "向量索引: 0/0" in result

        # 添加一个文档
        path = os.path.join(vault_dir, "doc.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "T", "date": "2026-04-22", "level": "lite", "tags": []},
            "content": "内容",
        })
        agent.run(f'ingest "{path}"')

        result = agent.run("status")
        assert "向量索引: 1/1" in result
    finally:
        _cleanup(vault_dir, db)


def test_e2e_search_without_embeddings():
    """向量索引为空时搜索给出提示"""
    vault_dir, db, emb_store, registry = _setup()
    llm = _mock_llm()
    agent = Agent(tools=registry, db=db, llm=llm, embedding_store=emb_store)

    try:
        result = agent.run('search "矩阵"')
        assert "索引为空" in result
    finally:
        _cleanup(vault_dir, db)


def test_route_index_and_search():
    """验证路由能识别 index 和 search"""
    router = Router()

    r = router.route("index")
    assert r["intent"] == "index"

    r = router.route("index --full")
    assert r["intent"] == "index"
    assert r["params"]["full"] is True

    r = router.route('search "矩阵分解"')
    assert r["intent"] == "search"
    assert "矩阵分解" in r["params"]["query"]
