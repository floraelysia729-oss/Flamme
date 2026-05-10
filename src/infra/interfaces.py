"""基础设施层接口定义"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class CheckpointManager(Protocol):
    """断点续传接口"""

    def start(self, operation: str, target: str, snapshot: dict) -> int:
        """开始一个操作，返回 checkpoint id"""
        ...

    def update(self, checkpoint_id: int, snapshot: dict) -> None:
        """更新中间状态"""
        ...

    def complete(self, checkpoint_id: int) -> None:
        """标记完成"""
        ...

    def find_pending(self, operation: str) -> dict | None:
        """查找未完成的操作"""
        ...


@runtime_checkable
class GitHelper(Protocol):
    """Git 操作接口"""

    def get_head_commit(self) -> str:
        """获取当前 HEAD commit hash"""
        ...

    def commit(self, message: str) -> None:
        """git add all + commit"""
        ...
