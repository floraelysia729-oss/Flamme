"""Vault 同步工具 — 扫描 .md 文件，对比 SQLite 索引，执行增量同步

文件是真相来源，SQLite 只是索引。sync 不修改任何 .md 文件，
只在 DB 中 upsert/delete 元数据记录。
"""

import hashlib
import os
from pathlib import Path

from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult


SKIP_DIRS = {".wiki", ".obsidian", ".git", "node_modules", ".trash", ".claude", "__pycache__"}


def scan_all_md(vault_path: str) -> list[str]:
    """扫描 vault 中所有可索引的 .md 文件，返回相对路径列表"""
    vault = Path(vault_path)
    files = []
    for p in vault.rglob("*.md"):
        # 跳过排除目录
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        # 跳过 excalidraw 文件（由专门工具处理）
        if p.name.endswith(".excalidraw.md"):
            continue
        # 转为 vault 相对路径（正斜杠）
        try:
            rel = str(p.relative_to(vault)).replace("\\", "/")
            files.append(rel)
        except ValueError:
            continue
    return sorted(files)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def infer_level(relpath: str) -> str:
    """从路径推断级别：pro/xxx → pro, lite/xxx → lite, 其余 → raw"""
    if relpath.startswith("pro/"):
        return "pro"
    elif relpath.startswith("lite/"):
        return "lite"
    elif relpath.startswith("raw/"):
        return "raw"
    return "lite"


class SyncTool(BaseTool):
    """扫描 vault 文件 → 对比 SQLite → 增量同步索引"""

    name = "sync"
    description = "扫描 vault 文件并同步 SQLite 索引"
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = InterruptBehavior.BLOCK
    max_result_chars = 10_000

    def __init__(self, db, vault_path: str, parser=None):
        self._db = db
        self._vault_path = vault_path
        self._parser = parser

    def execute(self, params: dict) -> ToolResult:
        vault = self._vault_path
        if not vault or not Path(vault).is_dir():
            return ToolResult.err(f"vault 路径无效: {vault}")

        # 1. 扫描文件
        disk_files = scan_all_md(vault)
        disk_set = set(disk_files)

        # 2. 获取 DB 中已有记录
        db_docs = self._db.list_documents()
        db_map = {doc["path"]: doc for doc in db_docs}

        added, updated, removed, unchanged = [], [], [], []

        # 3. 新增/更新
        for relpath in disk_files:
            abs_path = os.path.join(vault, relpath)
            try:
                raw = Path(abs_path).read_text(encoding="utf-8")
            except Exception:
                continue

            h = content_hash(raw)
            doc = db_map.get(relpath)

            # 解析 frontmatter 拿元数据
            metadata = self._parse_frontmatter(raw)
            title = metadata.get("title", Path(relpath).stem)
            tags = metadata.get("tags") or []
            level = metadata.get("level", infer_level(relpath))
            status = metadata.get("status", "draft")
            word_count = len(raw)

            if doc is None:
                # 新文件
                self._db.put_document({
                    "path": relpath, "title": title, "level": level,
                    "status": status, "content_hash": h,
                    "word_count": word_count, "tags": tags,
                })
                added.append(relpath)
            elif doc.get("content_hash") != h:
                # 内容变了
                self._db.put_document({
                    "path": relpath, "title": title, "level": level,
                    "status": status, "content_hash": h,
                    "word_count": word_count, "tags": tags,
                })
                updated.append(relpath)
            else:
                unchanged.append(relpath)

        # 4. 删除 DB 中没有对应文件的记录
        for doc in db_docs:
            if doc["path"] not in disk_set:
                abs_check = os.path.join(vault, doc["path"])
                if not os.path.isfile(abs_check):
                    self._db.delete_document(doc["path"])
                    removed.append(doc["path"])

        # 5. 统计需要 embedding 的
        unembedded = self._db.get_unembedded_docs()
        to_embed = [d["path"] for d in unembedded]

        return ToolResult.ok({
            "added": added,
            "updated": updated,
            "removed": removed,
            "unchanged": len(unchanged),
            "to_embed": to_embed,
            "total_disk": len(disk_files),
            "total_db": len(db_docs) - len(removed) + len(added),
        })

    def _parse_frontmatter(self, raw: str) -> dict:
        """解析 YAML frontmatter"""
        if not raw.startswith("---"):
            return {}
        end = raw.find("---", 3)
        if end < 0:
            return {}
        try:
            import yaml
            return yaml.safe_load(raw[3:end]) or {}
        except Exception:
            return {}

    def validate_input(self, params: dict) -> list[str]:
        return []
