"""端到端集成测试 — 完整管道：创建文件 → ingest → query → status"""

import os
import tempfile

from unittest.mock import MagicMock

from src.config import load_config
from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.tools.markdown_writer import MarkdownWriter
from src.agent.agent import Agent


def _setup_env():
    """创建临时 vault + 数据库"""
    vault_dir = tempfile.mkdtemp()
    db_path = os.path.join(vault_dir, ".wiki", "knowledge.db")

    db = SQLiteClient(db_path)
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    registry.register(MarkdownWriter())

    return vault_dir, db, registry


def _cleanup(vault_dir: str, db: SQLiteClient):
    db.close()
    import shutil
    shutil.rmtree(vault_dir, ignore_errors=True)


def test_e2e_ingest_then_status():
    """创建 .md → ingest → status 显示 1 条"""
    vault_dir, db, registry = _setup_env()
    agent = Agent(tools=registry, db=db)

    try:
        # 1. 创建测试文件
        md_path = os.path.join(vault_dir, "线性代数.md")
        MarkdownWriter().execute({
            "path": md_path,
            "metadata": {
                "title": "线性代数笔记",
                "date": "2026-04-22",
                "level": "lite",
                "tags": ["数学", "线性代数", "矩阵"],
            },
            "content": "## 矩阵\n\n矩阵是数的矩形阵列",
        })

        # 2. ingest
        result = agent.run(f'ingest "{md_path}"')
        assert "已导入" in result

        # 3. status
        stats_output = agent.run("status")
        assert "文档总数: 1" in stats_output
        assert "lite: 1" in stats_output

        # 4. 直接查 SQLite 验证
        doc = db.get_document(md_path)
        assert doc is not None
        assert doc["title"] == "线性代数笔记"
        assert "数学" in doc["tags"]
    finally:
        _cleanup(vault_dir, db)


def test_e2e_multiple_ingest():
    """多个文件 ingest → 按级别统计"""
    vault_dir, db, registry = _setup_env()
    agent = Agent(tools=registry, db=db)

    try:
        files = [
            ("raw1.md", {"title": "R1", "date": "2026-01-01", "level": "raw", "tags": []}, "内容1"),
            ("lite1.md", {"title": "L1", "date": "2026-01-01", "level": "lite", "tags": ["tag1"]}, "内容2"),
            ("pro1.md", {"title": "P1", "date": "2026-01-01", "level": "pro", "tags": ["tag1", "tag2"]}, "内容3"),
        ]

        for filename, metadata, content in files:
            path = os.path.join(vault_dir, filename)
            MarkdownWriter().execute({"path": path, "metadata": metadata, "content": content})
            agent.run(f'ingest "{path}"')

        stats_output = agent.run("status")
        assert "文档总数: 3" in stats_output
        assert "raw: 1" in stats_output
        assert "lite: 1" in stats_output
        assert "pro: 1" in stats_output

        stats = db.get_stats()
        assert stats["total_tags"] == 2
    finally:
        _cleanup(vault_dir, db)


def test_e2e_query_with_mock_llm():
    """ingest 后用 mock LLM 查询"""
    vault_dir, db, registry = _setup_env()

    mock_llm = MagicMock()
    mock_llm.complete.return_value = "矩阵是数的矩形阵列，用于线性变换"

    agent = Agent(tools=registry, db=db, llm=mock_llm)

    try:
        # 先 ingest
        path = os.path.join(vault_dir, "test.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "矩阵基础", "date": "2026-01-01", "level": "lite", "tags": ["数学"]},
            "content": "矩阵的定义",
        })
        agent.run(f'ingest "{path}"')

        # 查询
        result = agent.run("什么是矩阵")
        assert "矩阵" in result
        mock_llm.complete.assert_called_once()

        # 验证 LLM 收到了文档上下文
        call_args = mock_llm.complete.call_args
        messages = call_args[0][0]
        system_msg = messages[0]["content"]
        assert "矩阵基础" in system_msg
    finally:
        _cleanup(vault_dir, db)


def test_e2e_update_document():
    """同一文件 ingest 两次 → 更新而非重复"""
    vault_dir, db, registry = _setup_env()
    agent = Agent(tools=registry, db=db)

    try:
        path = os.path.join(vault_dir, "test.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "V1", "date": "2026-01-01", "level": "raw", "tags": []},
            "content": "版本1",
        })
        agent.run(f'ingest "{path}"')

        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "V2", "date": "2026-01-02", "level": "lite", "tags": ["new"]},
            "content": "版本2",
        })
        agent.run(f'ingest "{path}"')

        stats = db.get_stats()
        assert stats["total_documents"] == 1  # 不重复

        doc = db.get_document(path)
        assert doc["title"] == "V2"
        assert "new" in doc["tags"]
    finally:
        _cleanup(vault_dir, db)


def test_e2e_nonexistent_file_ingest():
    """ingest 不存在的文件 → 报错"""
    vault_dir, db, registry = _setup_env()
    agent = Agent(tools=registry, db=db)

    try:
        result = agent.run('ingest "/nonexistent/file.md"')
        assert "错误" in result
    finally:
        _cleanup(vault_dir, db)


def test_query_reads_content():
    """query 时 LLM 收到的 context 包含文档正文片段"""
    vault_dir, db, registry = _setup_env()

    mock_llm = MagicMock()
    mock_llm.complete.return_value = "矩阵是数的矩形阵列"

    agent = Agent(tools=registry, db=db, llm=mock_llm)

    try:
        # 创建含正文的文档
        path = os.path.join(vault_dir, "math.md")
        MarkdownWriter().execute({
            "path": path,
            "metadata": {"title": "线性代数", "date": "2026-01-01", "level": "lite", "tags": ["数学"]},
            "content": "矩阵是线性代数的核心概念。矩阵可以用于表示线性变换。",
        })
        agent.run(f'ingest "{path}"')

        # query（走 fallback 路径，因为没有 embedding store）
        result = agent.run("什么是矩阵")

        # 验证 LLM 收到了正文内容
        call_args = mock_llm.complete.call_args
        messages = call_args[0][0]
        system_msg = messages[0]["content"]
        assert "线性代数" in system_msg
        # 正文片段应该出现在 context 中
        assert "矩阵是线性代数的核心概念" in system_msg
    finally:
        _cleanup(vault_dir, db)
