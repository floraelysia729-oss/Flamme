"""Tool 层接口定义 — 行为声明式工具协议

借鉴 Claude Code StreamingToolExecutor 的设计:
- 工具自己声明并发安全性、只读性、中断行为
- 结构化返回 ToolResult
- Pydantic schema 输入验证
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


# ── 生命周期状态 ──────────────────────────────────────────────


class ToolStatus(str, Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    YIELDED = "yielded"


# ── 中断行为 ──────────────────────────────────────────────────


class InterruptBehavior(str, Enum):
    CANCEL = "cancel"   # 可安全中途停止
    BLOCK = "block"     # 必须运行完成（如文件写入）


# ── 结构化返回 ────────────────────────────────────────────────


@dataclass
class ToolResult:
    """工具执行的统一返回类型"""
    data: Any = None
    error: str | None = None
    new_messages: list[dict] = field(default_factory=list)

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @classmethod
    def ok(cls, data: Any = None, **extra) -> "ToolResult":
        return cls(data={**{"result": data}, **extra} if extra else data)

    @classmethod
    def err(cls, message: str) -> "ToolResult":
        return cls(error=message)


# ── 进度事件 ──────────────────────────────────────────────────


@dataclass
class ProgressEvent:
    """工具执行中的进度消息"""
    tool_id: str
    message: str
    percentage: float | None = None


# ── Tool Protocol ─────────────────────────────────────────────


@runtime_checkable
class Tool(Protocol):
    """行为声明式工具协议 — 工具自己声明自己的特性"""

    # 身份
    name: str
    description: str

    # 行为声明（保守默认值）
    is_concurrency_safe: bool = False       # 是否可与其他工具并行
    is_read_only: bool = True               # 是否只读（权限系统用）
    interrupt_behavior: InterruptBehavior = InterruptBehavior.BLOCK
    max_result_chars: int = 10_000          # 输出最大字符数

    def execute(self, params: dict) -> ToolResult:
        """执行工具，返回结构化结果"""
        ...

    def validate_input(self, params: dict) -> list[str]:
        """输入校验，返回错误列表（空 = 通过）"""
        ...


# ── BaseTool 基类（可选继承，提供默认实现）──────────────────────


class BaseTool:
    """工具基类 — 提供行为声明的默认值，减少样板代码"""

    name: str = ""
    description: str = ""
    is_concurrency_safe: bool = False
    is_read_only: bool = True
    interrupt_behavior: InterruptBehavior = InterruptBehavior.BLOCK
    max_result_chars: int = 10_000

    def execute(self, params: dict) -> ToolResult:
        raise NotImplementedError

    def stream_execute(self, params: dict):
        """生成器版 execute。yields str 进度消息，最终 return ToolResult。

        默认退化为 execute() 无进度输出。
        Orchestrator 检测到工具有 stream_execute 时会在线程中调用，
        实时将进度 yield 到 SSE 流。
        """
        yield self.execute(params)

    def validate_input(self, params: dict) -> list[str]:
        return []
