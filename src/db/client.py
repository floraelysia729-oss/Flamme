"""SQLite 知识存储实现 — 实现 KnowledgeStore Protocol"""

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from datetime import datetime

from src.db.interfaces_kb import KnowledgeStore

logger = logging.getLogger(__name__)


class SQLiteClient:
    """SQLite 实现 — TS 映射: 同名 class, better-sqlite3 API"""

    def __init__(self, db_path: str, vault_path: str = ""):
        self._db_path = db_path
        self._vault_path = vault_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _norm(self, path: str) -> str:
        """归一化 path → vault 相对路径（正斜杠）"""
        if not path:
            return path
        if self._vault_path:
            p = Path(path)
            try:
                return str(p.relative_to(self._vault_path)).replace("\\", "/")
            except ValueError:
                pass
        return Path(path).as_posix()

    def resolve(self, path: str) -> str:
        """将 DB 中的相对路径还原为绝对路径（用于文件 I/O）

        写入时 _norm 转为相对路径存储；读取后需要访问文件时调用 resolve 还原。
        """
        if not path or not self._vault_path or os.path.isabs(path):
            return path
        return os.path.join(self._vault_path, path)

    def _init_schema(self):
        schema_path = Path(__file__).parent / "schema.sql"
        self._conn.executescript(schema_path.read_text(encoding="utf-8"))
        self._conn.commit()
        # 增量迁移：补齐已有 DB 的 entities 新列
        self._migrate_entities_columns()

    def _migrate_entities_columns(self):
        """为已有 DB 的 entities 表补齐新增列（幂等）"""
        new_cols = [
            ("community", "INTEGER DEFAULT -1"),
            ("tags", "TEXT DEFAULT ''"),
            ("entity_file", "TEXT DEFAULT ''"),
            ("source_file", "TEXT DEFAULT ''"),
            ("level", "TEXT DEFAULT ''"),
            ("content_hash", "TEXT DEFAULT ''"),
        ]
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(entities)").fetchall()}
        for col_name, col_type in new_cols:
            if col_name not in existing:
                self._conn.execute(f"ALTER TABLE entities ADD COLUMN {col_name} {col_type}")
        self._conn.commit()

    def close(self):
        self._conn.close()

    # --- KnowledgeStore Protocol ---

    def get_document(self, path: str) -> dict | None:
        path = self._norm(path)
        row = self._conn.execute(
            "SELECT * FROM documents WHERE path = ?", (path,)
        ).fetchone()
        if not row:
            return None
        doc = dict(row)
        # 附带标签
        tags = self._conn.execute(
            """SELECT t.name FROM tags t
               JOIN document_tags dt ON t.id = dt.tag_id
               WHERE dt.doc_path = ?""",
            (path,),
        ).fetchall()
        doc["tags"] = [t["name"] for t in tags]
        return doc

    def put_document(self, doc: dict) -> None:
        now = datetime.now().isoformat()
        path = self._norm(doc["path"])

        # upsert document
        self._conn.execute(
            """INSERT INTO documents (path, title, level, status, content_hash, word_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                 title=excluded.title, level=excluded.level, status=excluded.status,
                 content_hash=excluded.content_hash, word_count=excluded.word_count,
                 updated_at=excluded.updated_at""",
            (
                path,
                doc.get("title", ""),
                doc.get("level", "lite"),
                doc.get("status", "draft"),
                doc.get("content_hash"),
                doc.get("word_count"),
                doc.get("created_at", now),
                now,
            ),
        )

        # 处理标签
        tags = doc.get("tags", [])
        # 先清除旧标签
        self._conn.execute(
            "DELETE FROM document_tags WHERE doc_path = ?", (path,)
        )
        for tag_name in tags:
            self._conn.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
            )
            tag_row = self._conn.execute(
                "SELECT id FROM tags WHERE name = ?", (tag_name,)
            ).fetchone()
            self._conn.execute(
                "INSERT INTO document_tags (doc_path, tag_id) VALUES (?, ?)",
                (path, tag_row["id"]),
            )

        self._conn.commit()

    def delete_document(self, path: str) -> None:
        path = self._norm(path)
        self._conn.execute("DELETE FROM documents WHERE path = ?", (path,))
        self._conn.commit()

    def purge_missing(self) -> list[str]:
        """删除 DB 中所有指向不存在文件的记录，返回被删除的 path 列表"""
        vault = self._vault_path
        if not vault:
            return []
        docs = self.list_documents()
        deleted = []
        for doc in docs:
            abs_path = os.path.join(vault, doc["path"])
            if not os.path.isfile(abs_path):
                self._conn.execute("DELETE FROM documents WHERE path = ?", (doc["path"],))
                deleted.append(doc["path"])
        if deleted:
            self._conn.commit()
        return deleted

    def list_documents(self, level: str | None = None) -> list[dict]:
        if level:
            rows = self._conn.execute(
                "SELECT * FROM documents WHERE level = ? ORDER BY updated_at DESC",
                (level,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
        by_level = {}
        for row in self._conn.execute(
            "SELECT level, COUNT(*) as c FROM documents GROUP BY level"
        ).fetchall():
            by_level[row["level"] or "none"] = row["c"]
        tags_count = self._conn.execute("SELECT COUNT(*) as c FROM tags").fetchone()["c"]
        last_updated = self._conn.execute(
            "SELECT MAX(updated_at) as t FROM documents"
        ).fetchone()["t"]
        return {
            "total_documents": total,
            "by_level": by_level,
            "total_tags": tags_count,
            "last_updated": last_updated,
        }

    # --- Checkpoint 操作 ---

    def create_checkpoint(self, operation: str, target: str, snapshot: dict, git_commit: str) -> int:
        cursor = self._conn.execute(
            """INSERT INTO checkpoints (operation, target, snapshot, git_commit)
               VALUES (?, ?, ?, ?)""",
            (operation, target, json.dumps(snapshot, ensure_ascii=False), git_commit),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update_checkpoint(self, checkpoint_id: int, snapshot: dict) -> None:
        self._conn.execute(
            "UPDATE checkpoints SET snapshot = ?, updated_at = ? WHERE id = ?",
            (json.dumps(snapshot, ensure_ascii=False), datetime.now().isoformat(), checkpoint_id),
        )
        self._conn.commit()

    def complete_checkpoint(self, checkpoint_id: int) -> None:
        self._conn.execute(
            "UPDATE checkpoints SET status = 'done', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), checkpoint_id),
        )
        self._conn.commit()

    def find_pending_checkpoint(self, operation: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE operation = ? AND status = 'in_progress' ORDER BY id DESC LIMIT 1",
            (operation,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"]) if result["snapshot"] else {}
        return result

    # --- Embedding 关联操作 ---

    def put_embedding(self, doc_path: str, content_hash: str, model: str = "text-embedding-v3", dim: int = 1024) -> int:
        """写入 embedding 元数据记录，返回 embedding id"""
        doc_path = self._norm(doc_path)
        cursor = self._conn.execute(
            """INSERT INTO embeddings (doc_path, content_hash, dim, model)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(doc_path) DO UPDATE SET
                 content_hash=excluded.content_hash, dim=excluded.dim, model=excluded.model""",
            (doc_path, content_hash, dim, model),
        )
        emb_id = cursor.lastrowid
        # 关联到 documents
        self._conn.execute(
            "UPDATE documents SET embedding_id = ? WHERE path = ?",
            (emb_id, doc_path),
        )
        self._conn.commit()
        return emb_id

    def get_embedding_by_doc(self, doc_path: str) -> dict | None:
        doc_path = self._norm(doc_path)
        row = self._conn.execute(
            "SELECT * FROM embeddings WHERE doc_path = ?", (doc_path,)
        ).fetchone()
        return dict(row) if row else None

    def get_embedding_by_hash(self, content_hash: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM embeddings WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return dict(row) if row else None

    def get_unembedded_docs(self) -> list[dict]:
        """获取还没有 embedding 的文档列表"""
        rows = self._conn.execute(
            """SELECT d.* FROM documents d
               LEFT JOIN embeddings e ON d.path = e.doc_path
               WHERE e.id IS NULL"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_embedding_stats(self) -> dict:
        total_docs = self._conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
        embedded = self._conn.execute("SELECT COUNT(*) as c FROM embeddings").fetchone()["c"]
        return {
            "total_documents": total_docs,
            "embedded": embedded,
            "unembedded": total_docs - embedded,
        }

    # --- Task Queue 操作 (Phase 4) ---

    # 最大 generation，防止死循环
    MAX_GENERATION = 5

    def push_task(self, task_type: str, payload: dict, generation: int = 0) -> int:
        """推送任务到队列，返回 task id"""
        cursor = self._conn.execute(
            """INSERT INTO task_queue (type, status, payload, generation, created_at, updated_at)
               VALUES (?, 'pending', ?, ?, ?, ?)""",
            (task_type, json.dumps(payload, ensure_ascii=False), generation,
             datetime.now().isoformat(), datetime.now().isoformat()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def claim_task(self, worker_id: str, task_type: str | None = None) -> dict | None:
        """原子地认领一个 pending 任务 (pending → claimed)

        使用 BEGIN IMMEDIATE 获取写锁，防止并发 worker claim 同一任务。

        Args:
            worker_id: 认领的 worker 标识
            task_type: 只认领指定类型，None 则不限
        Returns:
            任务 dict 或 None（无可用任务）
        """
        # BEGIN IMMEDIATE 获取写锁，保证 SELECT + UPDATE 原子性
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            # 构建查询：pending + generation 未超限
            if task_type:
                row = self._conn.execute(
                    """SELECT * FROM task_queue
                       WHERE status = 'pending' AND type = ? AND generation <= ?
                       ORDER BY created_at ASC LIMIT 1""",
                    (task_type, self.MAX_GENERATION),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """SELECT * FROM task_queue
                       WHERE status = 'pending' AND generation <= ?
                       ORDER BY created_at ASC LIMIT 1""",
                    (self.MAX_GENERATION,),
                ).fetchone()

            if not row:
                self._conn.execute("COMMIT")
                return None

            task_id = row["id"]
            now = datetime.now().isoformat()
            self._conn.execute(
                """UPDATE task_queue SET status = 'claimed', claimed_by = ?, updated_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (worker_id, now, task_id),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

        # 读取并返回
        row = self._conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
        task = dict(row)
        if task.get("payload"):
            task["payload"] = json.loads(task["payload"])
        return task

    def claim_task_by_id(self, worker_id: str, task_id: int,
                         task_type: str | None = None) -> dict | None:
        """原子地认领指定任务（仅当该任务是 pending 且 generation 未超限）"""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            if task_type:
                row = self._conn.execute(
                    """SELECT * FROM task_queue
                       WHERE id = ? AND status = 'pending' AND type = ? AND generation <= ?""",
                    (task_id, task_type, self.MAX_GENERATION),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """SELECT * FROM task_queue
                       WHERE id = ? AND status = 'pending' AND generation <= ?""",
                    (task_id, self.MAX_GENERATION),
                ).fetchone()

            if not row:
                self._conn.execute("COMMIT")
                return None

            now = datetime.now().isoformat()
            self._conn.execute(
                """UPDATE task_queue SET status = 'claimed', claimed_by = ?, updated_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (worker_id, now, task_id),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

        claimed = self._conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
        task = dict(claimed)
        if task.get("payload"):
            task["payload"] = json.loads(task["payload"])
        return task

    def complete_task(self, task_id: int, result: dict | None = None) -> None:
        """标记任务完成"""
        now = datetime.now().isoformat()
        payload = json.dumps(result, ensure_ascii=False) if result else None
        self._execute_with_lock_retry(
            "UPDATE task_queue SET status = 'done', payload = ?, updated_at = ? WHERE id = ?",
            (payload, now, task_id),
        )

    def fail_task(self, task_id: int, error: str | None = None) -> None:
        """标记任务失败（status → failed，可被重新 claim）"""
        now = datetime.now().isoformat()
        # 将 error 写入 payload
        row = self._conn.execute("SELECT payload FROM task_queue WHERE id = ?", (task_id,)).fetchone()
        existing = json.loads(row["payload"]) if row and row["payload"] else {}
        existing["_error"] = error
        self._execute_with_lock_retry(
            "UPDATE task_queue SET status = 'failed', payload = ?, updated_at = ? WHERE id = ?",
            (json.dumps(existing, ensure_ascii=False), now, task_id),
        )

    def get_tasks_by_status(self, status: str) -> list[dict]:
        """按状态查询任务"""
        rows = self._conn.execute(
            "SELECT * FROM task_queue WHERE status = ? ORDER BY created_at ASC",
            (status,),
        ).fetchall()
        tasks = []
        for r in rows:
            task = dict(r)
            if task.get("payload"):
                task["payload"] = json.loads(task["payload"])
            tasks.append(task)
        return tasks

    def retry_failed_task(self, task_id: int, generation: int | None = None) -> bool:
        """将 failed 任务重置为 pending 以便重新 claim

        Args:
            task_id: 任务 ID
            generation: 可选覆盖 generation（默认 +1）
        Returns:
            是否成功重置
        """
        row = self._conn.execute(
            "SELECT generation FROM task_queue WHERE id = ? AND status = 'failed'",
            (task_id,),
        ).fetchone()
        if not row:
            return False

        new_gen = generation if generation is not None else row["generation"] + 1
        if new_gen > self.MAX_GENERATION:
            return False

        now = datetime.now().isoformat()
        self._conn.execute(
            """UPDATE task_queue SET status = 'pending', generation = ?,
               claimed_by = NULL, updated_at = ? WHERE id = ?""",
            (new_gen, now, task_id),
        )
        self._conn.commit()
        return True

    def get_task_stats(self) -> dict:
        """任务队列统计"""
        stats = {}
        for row in self._conn.execute(
            "SELECT status, COUNT(*) as c FROM task_queue GROUP BY status"
        ).fetchall():
            stats[row["status"]] = row["c"]
        return stats

    def _execute_with_lock_retry(self, sql: str, params: tuple,
                                 retries: int = 5, delay: float = 0.2) -> None:
        """执行写入 SQL，遇到 database is locked 时重试"""
        for attempt in range(retries):
            try:
                self._conn.execute(sql, params)
                self._conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "database is locked" not in str(e).lower() or attempt == retries - 1:
                    raise
                time.sleep(delay * (attempt + 1))

    # --- Entity / Relation 操作 ---

    def upsert_entity(self, name: str, entity_type: str, wiki_path: str,
                      community: int = -1, tags: str = '',
                      entity_file: str = '', source_file: str = '',
                      level: str = '', content_hash: str = '') -> int:
        """插入或更新实体，返回 entity id"""
        wiki_path = self._norm(wiki_path)
        cursor = self._conn.execute(
            """INSERT INTO entities (name, type, wiki_path, community, tags,
                                      entity_file, source_file, level, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 type=excluded.type, wiki_path=excluded.wiki_path,
                 community=excluded.community, tags=excluded.tags,
                 entity_file=excluded.entity_file, source_file=excluded.source_file,
                 level=excluded.level, content_hash=excluded.content_hash""",
            (name, entity_type, wiki_path, community, tags,
             entity_file, source_file, level, content_hash),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT id FROM entities WHERE name=?", (name,)).fetchone()
        return row["id"] if row else cursor.lastrowid

    def upsert_relation(self, source_name: str, target_name: str,
                        relation_type: str, source_doc: str) -> None:
        """插入实体间关系（去重：同 source+target+type 不重复插入）"""
        src = self._conn.execute("SELECT id FROM entities WHERE name=?", (source_name,)).fetchone()
        tgt = self._conn.execute("SELECT id FROM entities WHERE name=?", (target_name,)).fetchone()
        if not src or not tgt:
            logger.warning(
                "upsert_relation: entity not found — src=%s (found=%s), tgt=%s (found=%s), type=%s",
                source_name, src is not None, target_name, tgt is not None, relation_type,
            )
            return
        # 去重检查
        existing = self._conn.execute(
            """SELECT id FROM relations
               WHERE source_entity=? AND target_entity=? AND relation_type=?""",
            (src["id"], tgt["id"], relation_type),
        ).fetchone()
        if existing:
            return
        self._conn.execute(
            """INSERT INTO relations (source_entity, target_entity, relation_type, source_doc)
               VALUES (?, ?, ?, ?)""",
            (src["id"], tgt["id"], relation_type, source_doc),
        )
        self._conn.commit()

    # --- Glossary 操作 ---

    def lookup_term(self, term: str, domain: str = "") -> list[dict]:
        """精确查找术语，无 domain 时返回所有领域定义"""
        if domain:
            rows = self._conn.execute(
                "SELECT * FROM glossary WHERE term = ? AND domain = ?",
                (term, domain),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM glossary WHERE term = ? ORDER BY domain",
                (term,),
            ).fetchall()
        return [dict(r) for r in rows]

    def define_term(self, term: str, domain: str, definition: str,
                    aliases: str = "", seealso: str = "",
                    source: str = "") -> int:
        """添加或更新术语定义（upsert by term+domain），返回 id"""
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """INSERT INTO glossary (term, domain, definition, aliases, seealso, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(term, domain) DO UPDATE SET
                 definition=excluded.definition, aliases=excluded.aliases,
                 seealso=excluded.seealso, source=excluded.source, updated_at=excluded.updated_at""",
            (term, domain, definition, aliases, seealso, source, now, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_terms(self, domain: str = "") -> list[dict]:
        """列出所有术语，可按领域过滤"""
        if domain:
            rows = self._conn.execute(
                "SELECT * FROM glossary WHERE domain = ? ORDER BY term",
                (domain,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM glossary ORDER BY domain, term",
            ).fetchall()
        return [dict(r) for r in rows]

    def search_terms(self, query: str) -> list[dict]:
        """模糊搜索术语、别名、定义"""
        pattern = f"%{query}%"
        rows = self._conn.execute(
            """SELECT * FROM glossary
               WHERE term LIKE ? OR aliases LIKE ? OR definition LIKE ?
               ORDER BY domain, term""",
            (pattern, pattern, pattern),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_term(self, term: str, domain: str) -> bool:
        """删除指定术语的指定领域定义"""
        cursor = self._conn.execute(
            "DELETE FROM glossary WHERE term = ? AND domain = ?",
            (term, domain),
        )
        self._conn.commit()
        return cursor.rowcount > 0
