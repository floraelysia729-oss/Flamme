"""术语表工具 — 跨领域术语消歧与定义管理"""

from src.db.client import SQLiteClient
from src.tools.interfaces import BaseTool, ToolResult


class GlossaryTool(BaseTool):
    name = "glossary"
    description = "术语表工具。查询、定义、搜索术语，支持按领域消歧。"
    is_concurrency_safe = True
    is_read_only = False
    max_result_chars = 50_000

    def __init__(self, db: SQLiteClient):
        self._db = db

    def execute(self, params: dict) -> ToolResult:
        action = params.get("action", "")
        if not action:
            return ToolResult.err("缺少 action 参数")

        if action == "lookup":
            return self._lookup(params)
        elif action == "define":
            return self._define(params)
        elif action == "list":
            return self._list(params)
        elif action == "search":
            return self._search(params)
        else:
            return ToolResult.err(f"未知 action: {action}")

    def _lookup(self, params: dict) -> ToolResult:
        term = params.get("term", "")
        if not term:
            return ToolResult.err("lookup 需要 term 参数")
        domain = params.get("domain", "")
        results = self._db.lookup_term(term, domain)
        if not results:
            return ToolResult.ok(data={"term": term, "found": False})
        return ToolResult.ok(data={"term": term, "found": True, "definitions": results})

    def _define(self, params: dict) -> ToolResult:
        term = params.get("term", "")
        domain = params.get("domain", "")
        definition = params.get("definition", "")
        if not term or not domain or not definition:
            return ToolResult.err("define 需要 term, domain, definition 参数")
        row_id = self._db.define_term(
            term=term, domain=domain, definition=definition,
            aliases=params.get("aliases", ""),
            seealso=params.get("seealso", ""),
            source=params.get("source", ""),
        )
        return ToolResult.ok(data={"id": row_id, "term": term, "domain": domain, "status": "saved"})

    def _list(self, params: dict) -> ToolResult:
        domain = params.get("domain", "")
        results = self._db.list_terms(domain)
        return ToolResult.ok(data={"total": len(results), "terms": results})

    def _search(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        if not query:
            return ToolResult.err("search 需要 query 参数")
        results = self._db.search_terms(query)
        return ToolResult.ok(data={"query": query, "total": len(results), "results": results})
