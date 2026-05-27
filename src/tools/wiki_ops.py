"""Wiki 操作工具集 — 共享工具池

供 Orchestrator 和 API 路由直接调用的知识库操作工具。
每个工具继承 BaseTool，声明并发安全性。
"""

import os
import re
from datetime import date
from pathlib import Path

from src.tools.paths import entities_dir, page_type_dir

import yaml

from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult


# ── 读工具 (safe) ────────────────────────────────────────────


class WikiSearchTool(BaseTool):
    """搜索知识库（向量检索）"""

    name = "wiki_search"
    description = "搜索知识库，返回相关页面摘要"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = InterruptBehavior.CANCEL
    max_result_chars = 50_000

    def __init__(self, db, embedding_store, llm=None):
        self._db = db
        self._embedding_store = embedding_store
        self._llm = llm

    def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        top_k = params.get("top_k", 5)

        if not query:
            return ToolResult.err("空搜索")

        # 有向量索引时走语义搜索
        if self._embedding_store and self._embedding_store.count() > 0 and self._llm:
            try:
                embeddings = self._llm.embed([query])
                results = self._embedding_store.search(embeddings[0], top_k=top_k)
                entries = []
                for r in results:
                    doc = self._db.get_document(r["doc_id"])
                    if doc:
                        entries.append({
                            "title": doc["title"],
                            "path": doc["path"],
                            "level": doc.get("level", ""),
                            "score": round(r["score"], 3),
                        })
                return ToolResult.ok({"results": entries, "total": len(entries)})
            except Exception as e:
                return ToolResult.err(f"语义搜索失败: {e}")

        # 退回文档列表
        docs = self._db.list_documents()
        entries = [
            {"title": doc["title"], "path": doc["path"], "level": doc.get("level", "")}
            for doc in docs[:top_k]
        ]
        return ToolResult.ok({"results": entries, "total": len(entries), "note": "向量索引为空，返回文档列表"})

    def validate_input(self, params: dict) -> list[str]:
        return [] if params.get("query") else ["缺少 query 参数"]


class WikiReadPageTool(BaseTool):
    """读取 wiki 页面全文"""

    name = "wiki_read_page"
    description = "读取 wiki 页面完整内容"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = InterruptBehavior.CANCEL
    max_result_chars = 200_000

    def __init__(self, db, parser=None):
        self._db = db
        self._parser = parser

    def execute(self, params: dict) -> ToolResult:
        title = params.get("title", "")
        path = params.get("path", "")
        if not title and not path:
            return ToolResult.err("未指定页面标题或路径")

        doc = _find_doc(self._db, title=title, path=path)
        if not doc:
            return ToolResult.err(f"页面不存在: {title or path}")

        doc_path = doc["path"]
        abs_path = self._db.resolve(doc_path)

        # 二进制文件（PDF/Word/PPT）→ 读 .flamme/converted/ 下已转换的 .md
        if doc_path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            content = self._read_converted(doc_path)
            if content is None:
                return ToolResult.ok({
                    "title": doc["title"],
                    "path": doc_path,
                    "level": doc.get("level", ""),
                    "tags": doc.get("tags", []),
                    "content": f"[二进制文件 {doc_path}，尚未转换，请先用 document_ingest 处理]",
                })
            return ToolResult.ok({
                "title": doc["title"],
                "path": doc_path,
                "level": doc.get("level", ""),
                "tags": doc.get("tags", []),
                "content": content,
            })

        if self._parser:
            result = self._parser.execute({"path": abs_path})
            if result.is_error:
                return result
            return ToolResult.ok({
                "title": doc["title"],
                "path": doc_path,
                "level": doc.get("level", ""),
                "tags": doc.get("tags", []),
                "content": result.data.get("content", ""),
                "metadata": result.data.get("metadata", {}),
            })

        p = Path(abs_path)
        if p.exists():
            return ToolResult.ok({
                "title": doc["title"],
                "path": doc_path,
                "level": doc.get("level", ""),
                "content": p.read_text(encoding="utf-8")[:8000],
            })
        return ToolResult.err(f"文件不存在: {abs_path}")

    def _read_converted(self, doc_path: str) -> str | None:
        """读取二进制文件对应的 .flamme/converted/{stem}.md"""
        try:
            from src.tools.paths import converted_dir, source_dir_for_path
            vault = Path(self._db._vault_path)
            abs_file = Path(self._db.resolve(doc_path))
            source_dir = source_dir_for_path(vault, abs_file)
            conv = converted_dir(source_dir)
            conv_md = conv / f"{abs_file.stem}.md"
            if conv_md.exists():
                return conv_md.read_text(encoding="utf-8")
        except Exception:
            pass
        return None

    def validate_input(self, params: dict) -> list[str]:
        return [] if (params.get("title") or params.get("path")) else ["缺少 title 或 path 参数"]


# ── 写工具 (unsafe) ──────────────────────────────────────────


class WikiCreatePageTool(BaseTool):
    """创建 wiki 实体/概念页"""

    name = "wiki_create_page"
    description = "创建 wiki 实体/概念页，自动补 frontmatter"
    is_concurrency_safe = False    # 写文件，不可并行
    is_read_only = False
    interrupt_behavior = InterruptBehavior.BLOCK  # 创建不可中断
    max_result_chars = 1_000

    def __init__(self, db, vault_path: str = ""):
        self._db = db
        self._vault_path = vault_path

    def execute(self, params: dict) -> ToolResult:
        title = params.get("title", "")
        page_type = params.get("type", "entity")
        content = params.get("content", "")
        tags = params.get("tags", [])
        related = params.get("related", [])

        if not title:
            return ToolResult.err("未指定标题")

        today = date.today().isoformat()
        vault = self._vault_path
        if not vault:
            return ToolResult.err("vault 路径未配置")

        if page_type == "entity":
            output_dir = entities_dir(Path(vault))
        else:
            output_dir = page_type_dir(Path(vault), page_type)

        safe_name = re.sub(r'[\\/:*?"<>|]', '_', title)
        file_path = output_dir / f"{safe_name}.md"

        if file_path.exists():
            return ToolResult.err(f"页面已存在: {file_path}")

        metadata = {
            "title": title, "type": page_type,
            "created": today, "updated": today,
            "sources": [], "tags": tags, "related": related,
        }

        fm = yaml.dump(metadata, allow_unicode=True, default_flow_style=False, sort_keys=False)
        full_content = f"---\n{fm}---\n{content}"

        file_path.write_text(full_content, encoding="utf-8")

        self._db.put_document({
            "path": str(file_path), "title": title,
            "level": "pro", "status": "draft",
            "tags": tags, "word_count": len(content),
            "content_hash": self._hash(full_content),
        })
        # DB _norm 会自动将绝对路径转为相对路径

        return ToolResult.ok({"path": str(file_path), "title": title, "created": True})

    def validate_input(self, params: dict) -> list[str]:
        return [] if params.get("title") else ["缺少 title 参数"]

    @staticmethod
    def _hash(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WikiUpdatePageTool(BaseTool):
    """更新已有 wiki 页面"""

    name = "wiki_update_page"
    description = "更新已有 wiki 页面内容"
    is_concurrency_safe = False    # 写文件，不可并行
    is_read_only = False
    interrupt_behavior = InterruptBehavior.BLOCK  # 更新不可中断
    max_result_chars = 1_000

    def __init__(self, db, parser=None):
        self._db = db
        self._parser = parser

    def execute(self, params: dict) -> ToolResult:
        title = params.get("title", "")
        path = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)

        if not title and not path:
            return ToolResult.err("未指定标题或路径")

        doc = _find_doc(self._db, title=title, path=path)
        if not doc:
            return ToolResult.err(f"页面不存在: {title or path}")

        doc_path = doc["path"]
        abs_path = self._db.resolve(doc_path)
        p = Path(abs_path)
        if not p.exists():
            return ToolResult.err(f"文件不存在: {doc_path}")

        existing = p.read_text(encoding="utf-8", errors="replace")

        if append:
            new_content = existing.rstrip() + "\n\n" + content
        else:
            fm_end = existing.find("---", 3)
            if fm_end > 0:
                frontmatter = existing[:fm_end + 3]
                new_content = frontmatter + "\n" + content
            else:
                new_content = content

        today = date.today().isoformat()
        new_content = re.sub(
            r'updated:\s*\d{4}-\d{2}-\d{2}',
            f'updated: {today}',
            new_content,
        )

        p.write_text(new_content, encoding="utf-8")

        self._db.put_document({
            "path": doc_path, "title": doc["title"],
            "level": doc.get("level", ""),
            "status": "stable",
            "tags": doc.get("tags", []),
            "word_count": len(new_content),
            "content_hash": WikiCreatePageTool._hash(new_content),
        })

        return ToolResult.ok({"path": doc_path, "title": doc["title"], "updated": True})

    def validate_input(self, params: dict) -> list[str]:
        errors = []
        if not params.get("title") and not params.get("path"):
            errors.append("缺少 title 或 path 参数")
        return errors


def _find_doc(db, title: str = "", path: str = "") -> dict | None:
    """统一文档查找：path 精确匹配 > title 精确匹配 > title 模糊匹配"""
    # 1. path 精确匹配（最快，走索引）
    if path:
        doc = db.get_document(path)
        if doc:
            return doc
        # DB 存正斜杠，输入可能是反斜杠，统一后再试
        normalized = path.replace("\\", "/")
        if normalized != path:
            doc = db.get_document(normalized)
            if doc:
                return doc
    # 2. title 匹配
    if title:
        docs = db.list_documents()
        title_lower = title.lower()
        # 精确
        for doc in docs:
            if doc["title"].lower() == title_lower:
                return doc
        # 模糊
        for doc in docs:
            if title_lower in doc["title"].lower():
                return doc
        # path 尾部匹配（title 可能是路径的一部分）
        if path:
            norm_path = path.replace("\\", "/")
            for doc in docs:
                doc_path = doc["path"].replace("\\", "/")
                if doc_path.endswith(norm_path) or norm_path.endswith(doc_path):
                    return doc
    return None


# ── 辅助工具 ─────────────────────────────────────────────────


class EntityExtractTool(BaseTool):
    """从文本提取实体"""

    name = "entity_extract"
    description = "从文本中提取实体名和类型"
    is_concurrency_safe = True    # 纯计算/LLM 调用，可并行
    is_read_only = True
    interrupt_behavior = InterruptBehavior.CANCEL
    max_result_chars = 20_000

    def __init__(self, llm=None):
        self._llm = llm

    def execute(self, params: dict) -> ToolResult:
        text = params.get("text", "")
        if not text:
            return ToolResult.err("空文本")

        if not self._llm:
            entities = self._heuristic_extract(text)
            return ToolResult.ok({"entities": entities, "method": "heuristic"})

        messages = [
            {"role": "system", "content": (
                "从以下文本中提取实体。返回 JSON 数组，每个元素: "
                '{"name": "实体名", "type": "person|concept|tool|event|location|organization"}\n'
                "只返回 JSON，不要解释。"
            )},
            {"role": "user", "content": text[:3000]},
        ]
        try:
            import json
            resp = self._llm.complete(messages, max_tokens=1024, temperature=0)
            entities = json.loads(resp)
            return ToolResult.ok({"entities": entities, "method": "llm"})
        except Exception as e:
            entities = self._heuristic_extract(text)
            return ToolResult.ok({"entities": entities, "method": "heuristic", "llm_error": str(e)})

    def validate_input(self, params: dict) -> list[str]:
        return [] if params.get("text") else ["缺少 text 参数"]

    @staticmethod
    def _heuristic_extract(text: str) -> list[dict]:
        entities = []
        seen: set[str] = set()
        for m in re.finditer(r'\[\[([^\]]+)\]\]', text):
            name = m.group(1)
            if name not in seen:
                entities.append({"name": name, "type": "concept"})
                seen.add(name)
        for m in re.finditer(r'\*\*([^*]+)\*\*', text):
            name = m.group(1)
            if name not in seen and len(name) < 30:
                entities.append({"name": name, "type": "concept"})
                seen.add(name)
        return entities
