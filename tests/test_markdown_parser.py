"""Markdown Parser 单元测试"""

import os
import tempfile

from src.tools.markdown_parser import MarkdownParser
from src.tools.interfaces import Tool


def test_implements_tool_protocol():
    parser = MarkdownParser()
    assert isinstance(parser, Tool)


def test_parse_with_frontmatter():
    parser = MarkdownParser()
    raw = """---
title: 测试笔记
date: 2026-04-22
level: lite
tags:
  - 数学
  - 线性代数
---
# 标题
正文内容
"""
    metadata, content = parser.parse_string(raw)
    assert metadata["title"] == "测试笔记"
    assert metadata["level"] == "lite"
    assert "数学" in metadata["tags"]
    assert "# 标题" in content
    assert "正文内容" in content


def test_parse_without_frontmatter():
    parser = MarkdownParser()
    raw = "# 没有frontmatter\n\n直接开始写"
    metadata, content = parser.parse_string(raw)
    assert metadata == {}
    assert "没有frontmatter" in content


def test_parse_empty_file():
    parser = MarkdownParser()
    metadata, content = parser.parse_string("")
    assert metadata == {}
    assert content == ""


def test_parse_chinese_content():
    parser = MarkdownParser()
    raw = """---
title: 微积分复习
---
## 极限

极限的定义：对于任意 ε > 0，存在 δ > 0...
"""
    metadata, content = parser.parse_string(raw)
    assert metadata["title"] == "微积分复习"
    assert "极限" in content
    assert "ε" in content


def test_execute_reads_file():
    parser = MarkdownParser()
    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("---\ntitle: 临时文件\n---\n临时内容")
        tmp_path = f.name

    try:
        result = parser.execute({"path": tmp_path})
        assert not result.is_error
        assert result.data["metadata"]["title"] == "临时文件"
        assert "临时内容" in result.data["content"]
    finally:
        os.unlink(tmp_path)


def test_execute_nonexistent_file():
    parser = MarkdownParser()
    result = parser.execute({"path": "/nonexistent/file.md"})
    assert result.is_error


def test_parse_frontmatter_with_related():
    parser = MarkdownParser()
    raw = """---
title: 测试
related:
  - "[[矩阵]]"
  - "[[向量空间]]"
---
内容
"""
    metadata, _ = parser.parse_string(raw)
    assert len(metadata["related"]) == 2
    assert "[[矩阵]]" in metadata["related"]
