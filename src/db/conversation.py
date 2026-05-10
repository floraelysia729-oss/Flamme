"""会话记忆存储 — SQLite 存储对话历史"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


class ConversationStore:
    """SQLite 对话历史存储"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_table()

    def _ensure_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
              content TEXT,
              tool_calls TEXT,
              tool_call_id TEXT,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, created_at)"
        )
        self._conn.commit()

    def save_turn(self, session_id: str, role: str, content: str,
                  tool_calls: list | None = None, tool_call_id: str | None = None):
        """保存一轮对话"""
        self._conn.execute(
            """INSERT INTO conversations (session_id, role, content, tool_calls, tool_call_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, role, content,
             json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
             tool_call_id,
             datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_recent(self, session_id: str, n: int = 20) -> list[dict]:
        """获取最近 N 轮对话（不含 system）"""
        rows = self._conn.execute(
            """SELECT * FROM conversations
               WHERE session_id = ? AND role != 'system'
               ORDER BY created_at DESC LIMIT ?""",
            (session_id, n),
        ).fetchall()
        # 反转为时间正序
        rows = list(reversed(rows))
        result = []
        for r in rows:
            entry = {"role": r["role"], "content": r["content"] or ""}
            if r["tool_calls"]:
                entry["tool_calls"] = json.loads(r["tool_calls"])
            if r["tool_call_id"]:
                entry["tool_call_id"] = r["tool_call_id"]
            result.append(entry)
        return result

    def get_messages_for_llm(self, session_id: str, n: int = 10) -> list[dict]:
        """获取格式化后的消息列表，可直接传给 LLM"""
        return self.get_recent(session_id, n)

    def clear_session(self, session_id: str):
        """清空某个会话"""
        self._conn.execute(
            "DELETE FROM conversations WHERE session_id = ?", (session_id,)
        )
        self._conn.commit()

    def list_sessions(self) -> list[dict]:
        """返回所有会话摘要（按最后更新时间倒序）"""
        rows = self._conn.execute("""
            SELECT
                session_id,
                COUNT(*) as message_count,
                MAX(created_at) as last_updated,
                MIN(CASE WHEN role = 'user' THEN content END) as first_user_msg
            FROM conversations
            WHERE role IN ('user', 'assistant')
            GROUP BY session_id
            ORDER BY last_updated DESC
        """).fetchall()
        result = []
        for r in rows:
            title = (r["first_user_msg"] or "新对话")[:40]
            result.append({
                "session_id": r["session_id"],
                "title": title,
                "message_count": r["message_count"],
                "last_updated": r["last_updated"],
            })
        return result

    def get_session_messages(self, session_id: str) -> list[dict]:
        """获取会话全部消息（用于前端恢复）"""
        return self.get_recent(session_id, n=200)

    def close(self):
        self._conn.close()
