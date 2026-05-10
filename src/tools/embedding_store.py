"""向量存储 — numpy .npy 文件 + 暴力余弦搜索

TS 映射: 同名 class, ndarray 替换为 Float32Array, cosinesimilarity lib
"""

import os
from pathlib import Path

import numpy as np


class EmbeddingStore:
    """基于 numpy 的向量存储 — 内存缓存 + 暴力余弦 top-K"""

    def __init__(self, store_dir: str, dim: int = 1024):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dim = dim
        self._vectors_path = self._dir / "vectors.npy"
        self._ids_path = self._dir / "ids.npy"
        self._hashes_path = self._dir / "hashes.npy"
        # 内存缓存，避免每次操作都读磁盘
        self._cache_vectors: np.ndarray | None = None
        self._cache_ids: np.ndarray | None = None
        self._cache_hashes: np.ndarray | None = None

    def _load(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """加载向量、ID、hash 数组。优先返回内存缓存"""
        if self._cache_vectors is not None:
            return self._cache_vectors, self._cache_ids, self._cache_hashes
        if not self._vectors_path.exists():
            empty = (
                np.zeros((0, self._dim), dtype=np.float32),
                np.array([], dtype=object),
                np.array([], dtype=object),
            )
            self._cache_vectors, self._cache_ids, self._cache_hashes = empty
            return empty
        vectors = np.load(self._vectors_path)
        ids = np.load(self._ids_path, allow_pickle=True)
        hashes = np.load(self._hashes_path, allow_pickle=True)
        self._cache_vectors, self._cache_ids, self._cache_hashes = vectors, ids, hashes
        return vectors, ids, hashes

    def _save(self, vectors: np.ndarray, ids: np.ndarray, hashes: np.ndarray) -> None:
        """写入临时文件后 os.replace 原子替换（Windows 安全），同步更新缓存"""
        tmp_vec = str(self._vectors_path) + ".tmp"
        tmp_ids = str(self._ids_path) + ".tmp"
        tmp_hash = str(self._hashes_path) + ".tmp"

        np.save(tmp_vec, vectors)
        np.save(tmp_ids, ids)
        np.save(tmp_hash, hashes)

        # np.save 会自动加 .npy 后缀
        os.replace(tmp_vec + ".npy", self._vectors_path)
        os.replace(tmp_ids + ".npy", self._ids_path)
        os.replace(tmp_hash + ".npy", self._hashes_path)

        # 同步更新内存缓存
        self._cache_vectors = vectors
        self._cache_ids = ids
        self._cache_hashes = hashes

    def add(self, doc_id: str, vector: list[float], content_hash: str) -> None:
        """添加一个向量。如果 doc_id 已存在则更新"""
        vectors, ids, hashes = self._load()

        # 检查是否已存在（按 doc_id）
        if len(ids) > 0:
            existing_idx = np.where(ids == doc_id)[0]
            if len(existing_idx) > 0:
                # 更新已有向量
                idx = existing_idx[0]
                vectors_write = vectors.copy() if not vectors.flags.writeable else vectors
                vectors_write[idx] = vector
                hashes_write = hashes.copy() if not hashes.flags.writeable else hashes
                hashes_write[idx] = content_hash
                self._save(vectors_write, ids, hashes_write)
                return

        # 追加
        new_vector = np.array([vector], dtype=np.float32)
        new_ids = np.array([doc_id], dtype=object)
        new_hashes = np.array([content_hash], dtype=object)

        if len(vectors) == 0:
            self._save(new_vector, new_ids, new_hashes)
        else:
            self._save(
                np.vstack([vectors, new_vector]),
                np.concatenate([ids, new_ids]),
                np.concatenate([hashes, new_hashes]),
            )

    def has_hash(self, content_hash: str) -> bool:
        """检查 hash 是否已存在"""
        _, _, hashes = self._load()
        if len(hashes) == 0:
            return False
        return content_hash in hashes

    def get_all_hashes(self) -> set[str]:
        """返回所有已存储的 content hash（用于批量去重）"""
        _, _, hashes = self._load()
        if len(hashes) == 0:
            return set()
        return set(str(h) for h in hashes)

    def add_batch(self, items: list[tuple[str, list[float], str]]) -> int:
        """批量添加向量，只做一次磁盘读写。返回处理的数量

        items: [(doc_id, vector, content_hash), ...]
        """
        if not items:
            return 0

        vectors, ids, hashes = self._load()
        id_to_idx = {str(id_val): i for i, id_val in enumerate(ids)} if len(ids) > 0 else {}

        to_append_vecs = []
        to_append_ids = []
        to_append_hashes = []

        for doc_id, vector, content_hash in items:
            if doc_id in id_to_idx:
                # 更新已有向量
                idx = id_to_idx[doc_id]
                if not vectors.flags.writeable:
                    vectors = vectors.copy()
                vectors[idx] = vector
                if not hashes.flags.writeable:
                    hashes = hashes.copy()
                hashes[idx] = content_hash
            else:
                to_append_vecs.append(vector)
                to_append_ids.append(doc_id)
                to_append_hashes.append(content_hash)

        if to_append_vecs:
            new_vec = np.array(to_append_vecs, dtype=np.float32)
            new_ids = np.array(to_append_ids, dtype=object)
            new_hash = np.array(to_append_hashes, dtype=object)
            if len(vectors) == 0:
                vectors, ids, hashes = new_vec, new_ids, new_hash
            else:
                vectors = np.vstack([vectors, new_vec])
                ids = np.concatenate([ids, new_ids])
                hashes = np.concatenate([hashes, new_hash])

        self._save(vectors, ids, hashes)
        return len(items)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        """余弦相似度 top-K 搜索

        returns: [{"doc_id": str, "score": float}, ...]
        """
        vectors, ids, _ = self._load()
        if len(vectors) == 0:
            return []

        query = np.array(query_vector, dtype=np.float32).reshape(1, -1)

        # 归一化
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query = query / query_norm

        vec_norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vec_norms = np.where(vec_norms == 0, 1, vec_norms)
        normalized = vectors / vec_norms

        # 余弦相似度 = 归一化后的点积
        scores = (normalized @ query.T).flatten()

        # top-K
        k = min(top_k, len(scores))
        top_indices = np.argsort(scores)[::-1][:k]

        results = []
        for idx in top_indices:
            results.append({
                "doc_id": str(ids[idx]),
                "score": float(scores[idx]),
            })
        return results

    def delete(self, doc_id: str) -> None:
        """删除一个向量"""
        vectors, ids, hashes = self._load()
        if len(ids) == 0:
            return

        mask = ids != doc_id
        if mask.all():
            return  # 不存在

        self._save(vectors[mask], ids[mask], hashes[mask])

    def count(self) -> int:
        """返回存储的向量数"""
        vectors, _, _ = self._load()
        return len(vectors)

    def get_all_ids(self) -> list[str]:
        """返回所有 doc_id"""
        _, ids, _ = self._load()
        return [str(i) for i in ids] if len(ids) > 0 else []
