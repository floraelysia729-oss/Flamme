"""知识基座层接口定义"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class KnowledgeStore(Protocol):
    """结构化知识存储接口 — SQLite 实现"""

    def get_document(self, path: str) -> dict | None:
        """按路径获取文档元数据"""
        ...

    def put_document(self, doc: dict) -> None:
        """写入或更新文档元数据"""
        ...

    def delete_document(self, path: str) -> None:
        """删除文档记录"""
        ...

    def list_documents(self, level: str | None = None) -> list[dict]:
        """列出文档，可选按 level 过滤"""
        ...

    def get_stats(self) -> dict:
        """返回 vault 统计信息"""
        ...
