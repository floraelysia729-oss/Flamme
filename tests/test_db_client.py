"""SQLite Client 单元测试"""

import os
import tempfile

from src.db.client import SQLiteClient
from src.db.interfaces_kb import KnowledgeStore


def _make_client() -> SQLiteClient:
    """创建临时数据库的 client"""
    tmp = tempfile.mktemp(suffix=".db")
    client = SQLiteClient(tmp)
    # monkey-patch close 也删除文件
    client._tmp_path = tmp
    return client


def _cleanup(client: SQLiteClient):
    path = client._tmp_path
    client.close()
    if os.path.exists(path):
        os.unlink(path)


def test_implements_protocol():
    client = _make_client()
    assert isinstance(client, KnowledgeStore)
    _cleanup(client)


def test_put_and_get_document():
    client = _make_client()
    doc = {
        "path": "notes/test.md",
        "title": "测试文档",
        "level": "lite",
        "tags": ["数学", "线性代数"],
        "word_count": 100,
        "content_hash": "abc123",
    }
    client.put_document(doc)

    result = client.get_document("notes/test.md")
    assert result is not None
    assert result["title"] == "测试文档"
    assert result["level"] == "lite"
    assert "数学" in result["tags"]
    assert "线性代数" in result["tags"]
    _cleanup(client)


def test_update_document():
    client = _make_client()
    client.put_document({"path": "a.md", "title": "旧标题", "level": "raw"})
    client.put_document({"path": "a.md", "title": "新标题", "level": "lite"})

    result = client.get_document("a.md")
    assert result["title"] == "新标题"
    assert result["level"] == "lite"
    _cleanup(client)


def test_delete_document():
    client = _make_client()
    client.put_document({"path": "a.md", "title": "删除测试", "level": "raw"})
    client.delete_document("a.md")

    assert client.get_document("a.md") is None
    _cleanup(client)


def test_list_documents_with_level_filter():
    client = _make_client()
    client.put_document({"path": "a.md", "title": "A", "level": "raw"})
    client.put_document({"path": "b.md", "title": "B", "level": "lite"})
    client.put_document({"path": "c.md", "title": "C", "level": "pro"})

    lite_docs = client.list_documents(level="lite")
    assert len(lite_docs) == 1
    assert lite_docs[0]["path"] == "b.md"

    all_docs = client.list_documents()
    assert len(all_docs) == 3
    _cleanup(client)


def test_get_stats():
    client = _make_client()
    client.put_document({"path": "a.md", "title": "A", "level": "raw", "tags": ["t1"]})
    client.put_document({"path": "b.md", "title": "B", "level": "lite", "tags": ["t1", "t2"]})

    stats = client.get_stats()
    assert stats["total_documents"] == 2
    assert stats["by_level"]["raw"] == 1
    assert stats["by_level"]["lite"] == 1
    assert stats["total_tags"] == 2
    _cleanup(client)


def test_get_nonexistent_document():
    client = _make_client()
    assert client.get_document("nonexistent.md") is None
    _cleanup(client)


def test_checkpoint_lifecycle():
    client = _make_client()
    # 创建
    cp_id = client.create_checkpoint("ingest", "batch1", {"done": 0, "total": 5}, "abc123")
    assert cp_id > 0

    # 查找 pending
    pending = client.find_pending_checkpoint("ingest")
    assert pending is not None
    assert pending["snapshot"]["total"] == 5

    # 更新
    client.update_checkpoint(cp_id, {"done": 3, "total": 5})
    pending = client.find_pending_checkpoint("ingest")
    assert pending["snapshot"]["done"] == 3

    # 完成
    client.complete_checkpoint(cp_id)
    assert client.find_pending_checkpoint("ingest") is None
    _cleanup(client)
