"""Agent + Router 单元测试"""

import os
import tempfile

from unittest.mock import MagicMock

from src.agent.router import Router
from src.agent.agent import Agent
from src.agent.interfaces import AgentProtocol
from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.tools.markdown_writer import MarkdownWriter
from src.db.client import SQLiteClient


# --- Router 测试 ---


def test_route_status():
    router = Router()
    for cmd in ("status", "stat", "统计"):
        result = router.route(cmd)
        assert result["intent"] == "status", f"'{cmd}' 应路由到 status"


def test_route_ingest():
    router = Router()
    result = router.route('ingest "notes/test.md"')
    assert result["intent"] == "ingest"
    assert "test.md" in result["params"]["path"]


def test_route_ingest_chinese():
    router = Router()
    result = router.route("导入笔记.md")
    assert result["intent"] == "ingest"


def test_route_query_default():
    router = Router()
    result = router.route("什么是矩阵的奇异值分解")
    assert result["intent"] == "query"
    assert "奇异值分解" in result["params"]["question"]


# --- Agent 测试 ---


def _make_agent(tmp_db: str) -> tuple[Agent, SQLiteClient]:
    db = SQLiteClient(tmp_db)
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    registry.register(MarkdownWriter())
    agent = Agent(tools=registry, db=db)
    return agent, db


def test_agent_protocol():
    tmp = tempfile.mktemp(suffix=".db")
    agent, db = _make_agent(tmp)
    assert isinstance(agent, AgentProtocol)
    db.close()
    os.unlink(tmp)


def test_agent_status():
    tmp = tempfile.mktemp(suffix=".db")
    agent, db = _make_agent(tmp)

    # 空库
    result = agent.run("status")
    assert "文档总数: 0" in result

    db.close()
    os.unlink(tmp)


def test_agent_ingest():
    tmp = tempfile.mktemp(suffix=".db")
    agent, db = _make_agent(tmp)

    # 创建临时 md 文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("---\ntitle: 测试\nlevel: lite\ntags: [a]\n---\n内容")
        md_path = f.name

    try:
        result = agent.run(f'ingest "{md_path}" --level lite')
        assert "已导入" in result

        # 验证 SQLite 有记录
        stats = db.get_stats()
        assert stats["total_documents"] == 1
    finally:
        os.unlink(md_path)
        db.close()
        os.unlink(tmp)


def test_agent_ingest_no_path():
    tmp = tempfile.mktemp(suffix=".db")
    agent, db = _make_agent(tmp)

    result = agent.run("ingest")
    assert "错误" in result

    db.close()
    os.unlink(tmp)


def test_agent_query_with_mock_llm():
    tmp = tempfile.mktemp(suffix=".db")
    agent, db = _make_agent(tmp)

    # 插入一些文档
    db.put_document({"path": "a.md", "title": "线性代数", "level": "lite", "tags": ["数学"]})

    # Mock LLM
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "线性代数是研究向量空间的数学分支"
    agent._llm = mock_llm

    result = agent.run("什么是线性代数")
    assert "线性代数" in result
    mock_llm.complete.assert_called_once()

    db.close()
    os.unlink(tmp)


def test_agent_query_without_llm():
    tmp = tempfile.mktemp(suffix=".db")
    agent, db = _make_agent(tmp)

    result = agent.run("什么是矩阵")
    assert "LLM 未配置" in result

    db.close()
    os.unlink(tmp)
