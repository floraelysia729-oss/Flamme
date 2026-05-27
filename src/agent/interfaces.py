"""编排层接口定义"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class WorkerProtocol(Protocol):
    """Worker 接口 — 从 task_queue 消费任务"""

    @property
    def worker_type(self) -> str:
        """该 Worker 能处理的任务类型"""
        ...

    def execute(self, task: dict) -> str:
        """执行单个任务，返回结果文本"""
        ...
