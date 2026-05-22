"""图谱查询 Tool — 通过 GraphStore (SQLite) 驱动

替代旧的 NetworkX + graph.json 文件缓存架构。
所有查询走 SQLite entities/relations 表。
"""

import logging
from typing import Any

from src.db.graph_store import GraphStore
from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult

logger = logging.getLogger(__name__)


class GraphQueryTool(BaseTool):
    """图谱查询 — GraphStore 驱动，支持邻居/搜索/社区/路径/探索"""

    name = "graph_query"
    description = "查询知识图谱：邻居、搜索、社区、路径、探索、统计"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = InterruptBehavior.CANCEL
    max_result_chars = 50_000

    def __init__(self, graph_store: GraphStore | None = None):
        self._store = graph_store

    def execute(self, params: dict) -> ToolResult:
        if not self._store:
            return ToolResult.err("GraphStore 未注入")

        action = params.get("action", "stats")

        dispatch = {
            "neighbors": lambda: self._neighbors(params),
            "search": lambda: self._search(params),
            "community": lambda: self._community(params),
            "isolates": lambda: self._isolates(),
            "stats": lambda: self._stats(),
            "path": lambda: self._shortest_path(params),
            "explore": lambda: self._explore(params),
        }

        handler = dispatch.get(action)
        if handler is None:
            return ToolResult.err(f"未知操作: {action}")
        return handler()

    # ── Actions ──────────────────────────────────────────

    def _neighbors(self, params: dict) -> ToolResult:
        node = params.get("node", "")
        if not node:
            return ToolResult.err("未指定节点")
        result = self._store.get_neighbors(node)
        if "error" in result:
            return ToolResult.err(f"节点不存在: {node}")
        return ToolResult.ok(result)

    def _search(self, params: dict) -> ToolResult:
        """搜索节点 + BFS 扩展关联子图"""
        query = params.get("query", "")
        if not query:
            return ToolResult.err("空搜索")

        results = self._store.search_nodes(query, top_k=params.get("top_k", 20))

        if not results:
            return ToolResult.ok({"query": query, "results": [], "count": 0, "expanded": 0})

        # 直接匹配
        direct = []
        for r in results:
            direct.append({
                "id": r["name"],
                "label": r["name"],
                "type": r.get("type", ""),
                "tags": r.get("tags", "").split(",") if r.get("tags") else [],
                "community": r.get("community", -1),
                "degree": r.get("degree", 0),
            })

        # BFS 扩展：从 top 3 匹配出发，1 跳扩展
        expanded_nodes = []
        direct_names = {r["name"] for r in results}
        for r in results[:3]:
            sub = self._store.bfs_subgraph(r["name"], depth=1)
            for n in sub.get("nodes", []):
                nname = n.get("name", "")
                if nname not in direct_names:
                    expanded_nodes.append({
                        "id": nname,
                        "label": nname,
                        "type": n.get("type", ""),
                        "degree": n.get("degree", 0),
                    })

        return ToolResult.ok({
            "query": query,
            "results": direct,
            "count": len(direct),
            "expanded": len(expanded_nodes),
            "related": expanded_nodes[:10],
        })

    def _community(self, params: dict) -> ToolResult:
        community_id = params.get("community_id")
        if community_id is not None:
            try:
                cid = int(community_id)
            except (ValueError, TypeError):
                return ToolResult.err(f"社区 ID 无效: {community_id}")
            result = self._store.get_community(cid)
            if result.get("error"):
                return ToolResult.err(result["error"])
            return ToolResult.ok(result)

        return ToolResult.ok(self._store.get_community())

    def _isolates(self) -> ToolResult:
        return ToolResult.ok({"isolates": self._store.get_isolates(),
                              "count": len(self._store.get_isolates())})

    def _stats(self) -> ToolResult:
        return ToolResult.ok(self._store.get_stats())

    def _shortest_path(self, params: dict) -> ToolResult:
        source = params.get("source", "")
        target = params.get("target", "")
        if not source or not target:
            return ToolResult.err("需要 source 和 target 参数")

        result = self._store.shortest_path(source, target)
        if "error" in result:
            return ToolResult.err(result["error"])
        return ToolResult.ok(result)

    def _explore(self, params: dict) -> ToolResult:
        """BFS 探索：从一个概念出发，发现关联子图"""
        query = params.get("query", "")
        depth = min(int(params.get("depth", 2)), 4)

        if not query:
            return ToolResult.err("需要 query 参数")

        # 先找到匹配节点
        matches = self._store.find_nodes(query)
        if not matches:
            return ToolResult.err(f"找不到匹配节点: {query}")

        # BFS 从匹配节点出发
        start_name = matches[0]["name"]
        sub = self._store.bfs_subgraph(start_name, depth)

        nodes_info = []
        for n in sub.get("nodes", []):
            nodes_info.append({
                "id": n.get("name", ""),
                "label": n.get("name", ""),
                "type": n.get("type", ""),
                "community": n.get("community", -1),
            })

        edges_info = []
        for e in sub.get("edges", []):
            edges_info.append({
                "source": e.get("source", ""),
                "target": e.get("target", ""),
                "relation": e.get("relation_type", ""),
            })

        return ToolResult.ok({
            "query": query,
            "depth": depth,
            "start_nodes": [matches[0]["name"]],
            "nodes": nodes_info,
            "edges": edges_info,
            "total_nodes": len(nodes_info),
            "total_edges": len(edges_info),
        })
