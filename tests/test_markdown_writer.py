"""Markdown Writer 单元测试"""

import os
import tempfile

from src.tools.markdown_writer import MarkdownWriter
from src.tools.markdown_parser import MarkdownParser
from src.tools.interfaces import Tool


def test_implements_tool_protocol():
    writer = MarkdownWriter()
    assert isinstance(writer, Tool)


def test_write_and_read_roundtrip():
    """写入后再读出，验证 frontmatter 一致"""
    writer = MarkdownWriter()
    parser = MarkdownParser()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.md")
        metadata = {
            "title": "测试笔记",
            "date": "2026-04-22",
            "level": "lite",
            "tags": ["数学", "线性代数"],
        }
        content = "## 正文\n\n一些内容"

        # 写入
        result = writer.execute({"path": path, "metadata": metadata, "content": content})
        assert result["success"]

        # 读回
        parsed = parser.execute({"path": path})
        assert parsed["metadata"]["title"] == "测试笔记"
        assert parsed["metadata"]["level"] == "lite"
        assert "数学" in parsed["metadata"]["tags"]
        assert "正文" in parsed["content"]


def test_reject_missing_required_fields():
    writer = MarkdownWriter()
    result = writer.execute({
        "path": "/tmp/test.md",
        "metadata": {"title": "只有标题"},  # 缺 date, level, tags
        "content": "内容",
    })
    assert "error" in result
    assert "缺少必填字段" in result["error"]


def test_reject_invalid_level():
    writer = MarkdownWriter()
    result = writer.execute({
        "path": "/tmp/test.md",
        "metadata": {"title": "T", "date": "2026-01-01", "level": "invalid", "tags": []},
        "content": "",
    })
    assert "error" in result
    assert "无效 level" in result["error"]


def test_wiki_mode_validation():
    writer = MarkdownWriter()
    result = writer.execute({
        "path": "/tmp/test.md",
        "metadata": {"title": "T", "type": "entity", "created": "2026-01-01", "tags": ["a"]},
        "content": "",
        "wiki_mode": True,
    })
    assert result["success"]


def test_validate_returns_errors():
    writer = MarkdownWriter()
    errors = writer.validate({"title": "T"})  # 缺 date, level, tags
    assert len(errors) > 0


def test_overwrite_existing_file():
    writer = MarkdownWriter()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.md")
        metadata = {"title": "v1", "date": "2026-01-01", "level": "raw", "tags": []}
        writer.execute({"path": path, "metadata": metadata, "content": "v1"})

        metadata["title"] = "v2"
        writer.execute({"path": path, "metadata": metadata, "content": "v2"})

        parser = MarkdownParser()
        result = parser.execute({"path": path})
        assert result["metadata"]["title"] == "v2"
