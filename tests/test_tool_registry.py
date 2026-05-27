"""Tool Registry 单元测试"""

from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.tools.graph_query import GraphQueryTool


def test_register_and_get():
    registry = ToolRegistry()
    parser = MarkdownParser()
    registry.register(parser)

    assert registry.has("markdown_parser")
    tool = registry.get("markdown_parser")
    assert tool is parser


def test_list_tools():
    registry = ToolRegistry()
    registry.register(MarkdownParser())
    registry.register(GraphQueryTool())

    tools = registry.list_tools()
    names = [t["name"] for t in tools]
    assert "markdown_parser" in names
    assert "graph_query" in names


def test_get_nonexistent():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None
    assert not registry.has("nonexistent")


def test_register_replaces():
    registry = ToolRegistry()
    p1 = MarkdownParser()
    p2 = MarkdownParser()
    registry.register(p1)
    registry.register(p2)

    assert registry.get("markdown_parser") is p2
