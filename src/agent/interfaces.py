"""Agent 编排层接口定义"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentProtocol(Protocol):
    """单 Agent 接口"""

    def run(self, prompt: str, **kwargs) -> str:
        """接收 prompt，返回处理结果文本"""
        ...


@runtime_checkable
class WorkerProtocol(Protocol):
    """Worker 接口 — 从 task_queue 消费任务"""

    @property
    def worker_type(self) -> str:
        """该 Worker 能处理的任务类型"""
        ...

    def execute(self, task: dict) -> str:
        """执行单个任务，返回结果文本

        Args:
            task: task_queue 中的任务记录（含 payload dict）
        """
        ...
