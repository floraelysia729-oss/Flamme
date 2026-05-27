"""文档 API 共用逻辑 — 列表筛选 / 读取 / 语义搜索

三个 HTTP 路径共用此模块，避免与 wiki_read_page / wiki_search 工具重复实现：
  GET  /documents              → filter_documents + paginate（关键词筛 title/path）
  GET  /documents/{path}       → read_document（委托 wiki_read_page）
  POST /documents/search       → search_documents（委托 wiki_search）
"""

from src.tools.interfaces import ToolResult
from src.api.vault_context import VaultContext, normalize_doc_path


def filter_documents(
    db,
    *,
    level: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """按 level / tag / 关键词（title、path 子串）筛选文档元数据。"""
    docs = db.list_documents(level=level)
    if search:
        q = search.lower()
        docs = [
            d for d in docs
            if q in d.get("title", "").lower() or q in d.get("path", "").lower()
        ]
    if tag:
        matched = []
        for d in docs:
            tags = d.get("tags")
            if not tags:
                full = db.get_document(d["path"])
                tags = (full or {}).get("tags", [])
            if tag in tags:
                matched.append(d)
        docs = matched
    return docs


def paginate(items: list[dict], page: int, per_page: int) -> tuple[list[dict], int]:
    total = len(items)
    start = (page - 1) * per_page
    return items[start:start + per_page], total


def read_document(ctx: VaultContext, db, registry, path: str) -> dict:
    """读取单篇文档正文 — 与 Orchestrator wiki_read_page 同路径。"""
    path = normalize_doc_path(ctx, path)
    doc = db.get_document(path)
    if not doc:
        return {"error": "not found", "path": path}

    tool = registry.get("wiki_read_page")
    if not tool:
        return {"error": "wiki_read_page 未注册", "path": path}

    result = tool.execute({"path": path})
    if isinstance(result, ToolResult) and result.is_error:
        return {"error": result.error, "path": path}

    data = result.data if isinstance(result, ToolResult) and isinstance(result.data, dict) else {}
    if isinstance(result, dict) and "error" not in result:
        data = result

    return {
        "path": data.get("path", doc["path"]),
        "title": data.get("title", doc.get("title", "")),
        "content": data.get("content", ""),
        "metadata": doc,
    }


def search_documents(registry, query: str, top_k: int = 5) -> dict:
    """语义搜索 — 与 Orchestrator wiki_search 同路径。"""
    tool = registry.get("wiki_search")
    if not tool:
        return {"results": [], "message": "wiki_search 未注册"}

    result = tool.execute({"query": query, "top_k": top_k})
    if isinstance(result, ToolResult) and result.is_error:
        return {"results": [], "message": result.error}

    data = result.data if isinstance(result, ToolResult) and isinstance(result.data, dict) else {}
    return {"results": data.get("results", []), "total": data.get("total", 0)}
