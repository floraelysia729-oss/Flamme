"""端到端集成测试 — ingest Worker + DB 状态"""

import os
import shutil
import tempfile

from unittest.mock import MagicMock

from src.db.client import SQLiteClient
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from tests.helpers import write_md
from src.agent.coordinator import Coordinator


def _setup_env():
    vault_dir = tempfile.mkdtemp()
    db_path = os.path.join(vault_dir, ".wiki", "knowledge.db")
    db = SQLiteClient(db_path)
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    return vault_dir, db, registry


def _cleanup(vault_dir: str, db: SQLiteClient):
    db.close()
    shutil.rmtree(vault_dir, ignore_errors=True)


def _ingest(db, registry, path, level="lite", llm=None, embedding_store=None):
    coord = Coordinator(
        db=db, tools=registry, llm=llm,
        embedding_store=embedding_store, max_workers=1,
    )
    task_id = coord.dispatch("ingest", {"path": path, "level": level})
    return coord.wait_for(task_id, timeout=30)


def test_e2e_ingest_then_status():
    vault_dir, db, registry = _setup_env()
    try:
        md_path = os.path.join(vault_dir, "线性代数.md")
        write_md(
            md_path,
            "线性代数笔记",
            "## 矩阵\n\n矩阵是数的矩形阵列",
            tags=["数学", "线性代数", "矩阵"],
        )

        result = _ingest(db, registry, md_path, level="lite")
        assert "已导入" in result

        stats = db.get_stats()
        assert stats["total_documents"] == 1
        assert stats["by_level"].get("lite") == 1

        doc = db.get_document(md_path)
        assert doc is not None
        assert doc["title"] == "线性代数笔记"
        assert "数学" in doc["tags"]
    finally:
        _cleanup(vault_dir, db)


def test_e2e_multiple_ingest():
    vault_dir, db, registry = _setup_env()
    try:
        files = [
            ("raw1.md", {"title": "R1", "date": "2026-01-01", "level": "raw", "tags": []}, "内容1"),
            ("lite1.md", {"title": "L1", "date": "2026-01-01", "level": "lite", "tags": ["tag1"]}, "内容2"),
            ("pro1.md", {"title": "P1", "date": "2026-01-01", "level": "pro", "tags": ["tag1", "tag2"]}, "内容3"),
        ]

        for filename, metadata, content in files:
            path = os.path.join(vault_dir, filename)
            write_md(path, metadata["title"], content, level=metadata["level"], tags=metadata["tags"])
            _ingest(db, registry, path, level=metadata["level"])

        stats = db.get_stats()
        assert stats["total_documents"] == 3
        assert stats["by_level"]["raw"] == 1
        assert stats["by_level"]["lite"] == 1
        assert stats["by_level"]["pro"] == 1
        assert stats["total_tags"] == 2
    finally:
        _cleanup(vault_dir, db)


def test_e2e_query_with_mock_llm():
    vault_dir, db, registry = _setup_env()
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "矩阵是数的矩形阵列，用于线性变换"

    try:
        path = os.path.join(vault_dir, "test.md")
        write_md(path, "矩阵基础", "矩阵的定义", tags=["数学"])
        _ingest(db, registry, path, llm=mock_llm)

        coord = Coordinator(db=db, tools=registry, llm=mock_llm, max_workers=1)
        task_id = coord.dispatch("query", {"question": "什么是矩阵"})
        result = coord.wait_for(task_id, timeout=30)
        assert "矩阵" in result
        mock_llm.complete.assert_called_once()
    finally:
        _cleanup(vault_dir, db)


def test_e2e_update_document():
    vault_dir, db, registry = _setup_env()
    try:
        path = os.path.join(vault_dir, "test.md")
        write_md(path, "V1", "版本1", level="raw")
        _ingest(db, registry, path, level="raw")

        write_md(path, "V2", "版本2", level="lite", tags=["new"])
        _ingest(db, registry, path, level="lite")

        stats = db.get_stats()
        assert stats["total_documents"] == 1
        doc = db.get_document(path)
        assert doc["title"] == "V2"
        assert "new" in doc["tags"]
    finally:
        _cleanup(vault_dir, db)


def test_e2e_nonexistent_file_ingest():
    vault_dir, db, registry = _setup_env()
    try:
        result = _ingest(db, registry, "/nonexistent/file.md")
        assert isinstance(result, dict)
        assert "error" in result
    finally:
        _cleanup(vault_dir, db)


def test_query_reads_content():
    vault_dir, db, registry = _setup_env()
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "矩阵是数的矩形阵列"

    try:
        path = os.path.join(vault_dir, "math.md")
        write_md(
            path,
            "线性代数",
            "矩阵是线性代数的核心概念。矩阵可以用于表示线性变换。",
            tags=["数学"],
        )
        _ingest(db, registry, path, llm=mock_llm)

        coord = Coordinator(db=db, tools=registry, llm=mock_llm, max_workers=1)
        task_id = coord.dispatch("query", {"question": "什么是矩阵"})
        coord.wait_for(task_id, timeout=30)

        messages = mock_llm.complete.call_args[0][0]
        system_msg = messages[0]["content"]
        assert "线性代数" in system_msg
        assert "矩阵是线性代数的核心概念" in system_msg
    finally:
        _cleanup(vault_dir, db)
