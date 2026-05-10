"""Tool 注册中心 — 可插拔的工具注册和查询"""

from src.tools.interfaces import Tool


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """按名称获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """列出所有已注册工具（含行为声明）"""
        results = []
        for t in self._tools.values():
            info = {"name": t.name, "description": t.description}
            if hasattr(t, "is_concurrency_safe"):
                info["concurrency_safe"] = t.is_concurrency_safe
            if hasattr(t, "is_read_only"):
                info["read_only"] = t.is_read_only
            results.append(info)
        return results

    def has(self, name: str) -> bool:
        """检查工具是否已注册"""
        return name in self._tools

    def get_tools_by_names(self, names: list[str]) -> list:
        """按名称列表获取工具子集"""
        return [self._tools[n] for n in names if n in self._tools]

    def get_safe_tools(self) -> list[Tool]:
        """获取所有并发安全的工具"""
        return [t for t in self._tools.values() if getattr(t, "is_concurrency_safe", False)]

    def get_unsafe_tools(self) -> list[Tool]:
        """获取所有非并发安全的工具"""
        return [t for t in self._tools.values() if not getattr(t, "is_concurrency_safe", False)]
