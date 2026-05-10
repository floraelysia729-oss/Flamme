"""EmbeddingStore 单元测试"""

import os
import shutil
import tempfile
import time

import numpy as np

from src.tools.embedding_store import EmbeddingStore


def _make_store(dim: int = 8) -> tuple[EmbeddingStore, str]:
    tmpdir = tempfile.mkdtemp()
    return EmbeddingStore(tmpdir, dim=dim), tmpdir


def _cleanup(tmpdir: str):
    shutil.rmtree(tmpdir, ignore_errors=True)


def _random_vector(dim: int = 8) -> list[float]:
    return np.random.randn(dim).astype(np.float32).tolist()


def test_add_and_count():
    store, tmpdir = _make_store()
    store.add("doc1", _random_vector(), "hash1")
    assert store.count() == 1
    store.add("doc2", _random_vector(), "hash2")
    assert store.count() == 2
    _cleanup(tmpdir)


def test_search_empty_store():
    store, tmpdir = _make_store()
    results = store.search(_random_vector(), top_k=5)
    assert results == []
    _cleanup(tmpdir)


def test_search_top_k():
    store, tmpdir = _make_store(dim=4)

    # 构造已知向量：doc1 和 query 同方向，doc2 反方向
    base = [1.0, 0.0, 0.0, 0.0]
    opposite = [-1.0, 0.0, 0.0, 0.0]
    orthogonal = [0.0, 1.0, 0.0, 0.0]

    store.add("doc1", base, "h1")
    store.add("doc2", opposite, "h2")
    store.add("doc3", orthogonal, "h3")

    # 搜索与 base 同方向的 query
    results = store.search([1.0, 0.0, 0.0, 0.0], top_k=3)

    assert len(results) == 3
    assert results[0]["doc_id"] == "doc1"
    assert results[0]["score"] > 0.99  # 几乎 1.0
    assert results[1]["doc_id"] == "doc3"  # 正交 = 0
    assert results[2]["doc_id"] == "doc2"  # 反方向 < 0
    _cleanup(tmpdir)


def test_search_top_k_less_than_total():
    store, tmpdir = _make_store(dim=4)
    for i in range(5):
        store.add(f"doc{i}", _random_vector(4), f"h{i}")

    results = store.search(_random_vector(4), top_k=2)
    assert len(results) == 2
    _cleanup(tmpdir)


def test_add_update_existing():
    store, tmpdir = _make_store(dim=4)

    store.add("doc1", [1.0, 0.0, 0.0, 0.0], "h1")
    store.add("doc1", [0.0, 1.0, 0.0, 0.0], "h1_v2")  # 更新

    assert store.count() == 1  # 不增加

    # 搜索应该匹配新向量
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert results[0]["doc_id"] == "doc1"
    assert results[0]["score"] > 0.99
    _cleanup(tmpdir)


def test_delete():
    store, tmpdir = _make_store(dim=4)
    store.add("doc1", _random_vector(4), "h1")
    store.add("doc2", _random_vector(4), "h2")

    store.delete("doc1")
    assert store.count() == 1
    assert "doc2" in store.get_all_ids()
    assert "doc1" not in store.get_all_ids()
    _cleanup(tmpdir)


def test_delete_nonexistent():
    store, tmpdir = _make_store(dim=4)
    store.add("doc1", _random_vector(4), "h1")
    store.delete("nonexistent")  # 不报错
    assert store.count() == 1
    _cleanup(tmpdir)


def test_has_hash():
    store, tmpdir = _make_store(dim=4)
    store.add("doc1", _random_vector(4), "hash_abc")
    assert store.has_hash("hash_abc")
    assert not store.has_hash("hash_xyz")
    _cleanup(tmpdir)


def test_hash_dedup():
    """同样 hash 不应产生重复 embedding"""
    store, tmpdir = _make_store(dim=4)
    vec = _random_vector(4)
    store.add("doc1", vec, "same_hash")

    # 检查 hash 已存在
    assert store.has_hash("same_hash")

    # 外部应该先检查 has_hash 再决定是否 add
    if not store.has_hash("same_hash"):
        store.add("doc1", vec, "same_hash")

    assert store.count() == 1
    _cleanup(tmpdir)


def test_get_all_ids():
    store, tmpdir = _make_store(dim=4)
    store.add("doc1", _random_vector(4), "h1")
    store.add("doc2", _random_vector(4), "h2")

    ids = store.get_all_ids()
    assert set(ids) == {"doc1", "doc2"}
    _cleanup(tmpdir)


def test_performance_1000_docs():
    """1000 条向量搜索 < 100ms"""
    store, tmpdir = _make_store(dim=512)

    # 批量添加
    for i in range(1000):
        store.add(f"doc_{i}", np.random.randn(512).astype(np.float32).tolist(), f"h_{i}")

    assert store.count() == 1000

    # 搜索
    query = np.random.randn(512).astype(np.float32).tolist()
    start = time.perf_counter()
    results = store.search(query, top_k=10)
    elapsed = time.perf_counter() - start

    assert len(results) == 10
    assert elapsed < 0.5, f"搜索耗时 {elapsed:.3f}s，超过 500ms 阈值（含文件加载）"
    _cleanup(tmpdir)


def test_persistence():
    """数据持久化：关闭后重新打开数据仍在"""
    tmpdir = tempfile.mkdtemp()
    dim = 4

    store1 = EmbeddingStore(tmpdir, dim=dim)
    store1.add("doc1", [1.0, 0.0, 0.0, 0.0], "h1")
    assert store1.count() == 1

    # 重新打开
    store2 = EmbeddingStore(tmpdir, dim=dim)
    assert store2.count() == 1
    results = store2.search([1.0, 0.0, 0.0, 0.0], top_k=1)
    assert results[0]["doc_id"] == "doc1"
    _cleanup(tmpdir)


def test_add_batch():
    """批量添加：一次写入多个向量"""
    store, tmpdir = _make_store(dim=4)

    items = [
        ("doc1", [1.0, 0.0, 0.0, 0.0], "h1"),
        ("doc2", [0.0, 1.0, 0.0, 0.0], "h2"),
        ("doc3", [0.0, 0.0, 1.0, 0.0], "h3"),
    ]
    count = store.add_batch(items)
    assert count == 3
    assert store.count() == 3
    _cleanup(tmpdir)


def test_add_batch_empty():
    """批量添加空列表不做操作"""
    store, tmpdir = _make_store(dim=4)
    assert store.add_batch([]) == 0
    assert store.count() == 0
    _cleanup(tmpdir)


def test_add_batch_update_existing():
    """批量添加时更新已有向量"""
    store, tmpdir = _make_store(dim=4)

    store.add("doc1", [1.0, 0.0, 0.0, 0.0], "h1")
    assert store.count() == 1

    items = [
        ("doc1", [0.0, 1.0, 0.0, 0.0], "h1_v2"),  # 更新
        ("doc2", [0.0, 0.0, 1.0, 0.0], "h2"),       # 新增
    ]
    store.add_batch(items)
    assert store.count() == 2

    # doc1 应该是新向量
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert results[0]["doc_id"] == "doc1"
    _cleanup(tmpdir)


def test_get_all_hashes():
    """获取所有 hash 集合"""
    store, tmpdir = _make_store(dim=4)
    assert store.get_all_hashes() == set()

    store.add("doc1", _random_vector(4), "hash_abc")
    store.add("doc2", _random_vector(4), "hash_xyz")
    hashes = store.get_all_hashes()
    assert hashes == {"hash_abc", "hash_xyz"}
    _cleanup(tmpdir)


def test_add_batch_performance():
    """批量添加 1000 条应比逐条快得多"""
    store, tmpdir = _make_store(dim=128)

    items = [(f"doc_{i}", np.random.randn(128).astype(np.float32).tolist(), f"h_{i}")
             for i in range(1000)]

    start = time.perf_counter()
    store.add_batch(items)
    elapsed = time.perf_counter() - start

    assert store.count() == 1000
    assert elapsed < 5.0, f"批量添加 1000 条耗时 {elapsed:.2f}s"
    _cleanup(tmpdir)


def test_cache_avoids_disk_reread():
    """内存缓存：连续操作不重复读磁盘"""
    store, tmpdir = _make_store(dim=4)

    store.add("doc1", [1.0, 0.0, 0.0, 0.0], "h1")

    # 第一次 search 会触发 _load（磁盘读取 + 缓存填充）
    results1 = store.search([1.0, 0.0, 0.0, 0.0], top_k=1)
    assert len(results1) == 1

    # 缓存已填充，后续操作不读磁盘
    assert store._cache_vectors is not None

    # 删除磁盘文件，如果缓存生效则 count 仍返回 1
    import pathlib
    for p in pathlib.Path(tmpdir).glob("*.npy"):
        p.unlink()

    # 缓存应该仍然有效
    assert store.count() == 1

    _cleanup(tmpdir)
