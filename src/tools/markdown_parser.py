"""Markdown 解析器 — 读取 .md 文件，解析 frontmatter 和正文"""

import re
from pathlib import Path

import yaml

from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult


class MarkdownParser(BaseTool):
    """读取 .md → 解析 YAML frontmatter → 返回 {metadata, content}"""

    name = "markdown_parser"
    description = "读取 .md 文件并解析 frontmatter 和正文内容"
    is_concurrency_safe = True    # 只读，可并行
    is_read_only = True
    interrupt_behavior = InterruptBehavior.CANCEL
    max_result_chars = 100_000    # 文件内容可能很长

    _FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def execute(self, params: dict) -> ToolResult:
        path = params.get("path", "")
        if not path:
            return ToolResult.err("未指定路径")

        file_path = Path(path)
        if not file_path.exists():
            return ToolResult.err(f"文件不存在: {path}")

        raw = file_path.read_text(encoding="utf-8", errors="replace")
        metadata, content = self._parse(raw)

        return ToolResult.ok({
            "path": path,
            "metadata": metadata,
            "content": content,
            "raw": raw,
        })

    def validate_input(self, params: dict) -> list[str]:
        errors = []
        if not params.get("path"):
            errors.append("缺少 path 参数")
        return errors

    def parse_string(self, raw: str) -> tuple[dict, str]:
        """直接解析字符串，不读文件"""
        return self._parse(raw)

    def _parse(self, raw: str) -> tuple[dict, str]:
        match = self._FRONTMATTER_RE.match(raw)
        if not match:
            return {}, raw
        try:
            metadata = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            metadata = {}
        content = raw[match.end():]
        return metadata, content
