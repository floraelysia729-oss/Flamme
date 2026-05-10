"""图谱查询 Tool — NetworkX 驱动 + 内存缓存 + BFS 探索搜索

对比 graphify 的 serve.py，移植了：
  - 内存缓存：加载一次 NetworkX 图，检查 mtime 判断过期
  - 节点评分：_score_nodes() 按标签和文件名打分
  - BFS 遍历：从匹配节点出发，扩展关联子图
  - 最短路径：两个概念之间的连接路径
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult

logger = logging.getLogger(__name__)


class GraphQueryTool(BaseTool):
    """图谱查询 — NetworkX 图引擎，支持邻居/搜索/社区/路径/探索"""

    name = "graph_query"
    description = "查询知识图谱：邻居、搜索、社区、路径、探索、统计"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = InterruptBehavior.CANCEL
    max_result_chars = 50_000

    def __init__(self, default_graph_path: str = ""):
        self._default_graph_path = default_graph_path
        # 内存缓存
        self._graph: nx.DiGraph | None = None
        self._communities: dict[int, list[str]] = {}
        self._cache_mtime: float = 0.0
        self._cache_path: str = ""

    # ── 图加载 + 缓存 ──────────────────────────────────────

    def _get_graph(self, path: str) -> tuple[nx.DiGraph, dict[int, list[str]]]:
        """加载 NetworkX 图（带 mtime 缓存）"""
        p = Path(path)
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return nx.DiGraph(), {}

        # 缓存命中：同路径 + 文件未变
        if self._graph is not None and path == self._cache_path and mtime == self._cache_mtime:
            return self._graph, self._communities

        # 加载
        t0 = time.monotonic()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("graph.json 加载失败: %s", e)
            return nx.DiGraph(), {}

        # 从邻接表格式构建 NetworkX 图
        G = nx.DiGraph()
        for nid, attrs in raw.get("nodes", {}).items():
            G.add_node(nid, **attrs)
        for edge in raw.get("edges", []):
            src, tgt = edge.get("source", ""), edge.get("target", "")
            if src and tgt:
                G.add_edge(src, tgt, **{k: v for k, v in edge.items() if k not in ("source", "target")})

        # 重建社区映射
        communities: dict[int, list[str]] = {}
        for nid, data in G.nodes(data=True):
            cid = data.get("community")
            if cid is not None:
                communities.setdefault(int(cid), []).append(nid)

        # 写入缓存
        self._graph = G
        self._communities = communities
        self._cache_mtime = mtime
        self._cache_path = path

        elapsed = time.monotonic() - t0
        logger.info("图谱加载完成: %d nodes, %d edges (%.2fs)",
                     G.number_of_nodes(), G.number_of_edges(), elapsed)
        return G, communities

    # ── 工具分发 ──────────────────────────────────────────

    def execute(self, params: dict) -> ToolResult:
        graph_path = params.get("graph_path", "") or self._default_graph_path
        if not graph_path or not Path(graph_path).exists():
            return ToolResult.err(f"图谱文件不存在: {graph_path}")

        G, communities = self._get_graph(graph_path)
        if G.number_of_nodes() == 0:
            return ToolResult.err("图谱为空")

        action = params.get("action", "stats")

        dispatch = {
            "neighbors": lambda: self._neighbors(G, params.get("node", "")),
            "search": lambda: self._search(G, params),
            "community": lambda: self._community(G, communities, params.get("community_id")),
            "isolates": lambda: self._isolates(G),
            "stats": lambda: self._stats(G, communities),
            "path": lambda: self._shortest_path(G, params.get("source", ""), params.get("target", "")),
            "explore": lambda: self._explore(G, params),
        }

        handler = dispatch.get(action)
        if handler is None:
            return ToolResult.err(f"未知操作: {action}")
        return handler()

    # ── 节点评分（移植自 graphify serve.py）──────────────

    @staticmethod
    def _score_nodes(G: nx.DiGraph, terms: list[str]) -> list[tuple[float, str]]:
        """按标签和文件名对节点评分，返回 [(score, node_id)] 降序"""
        scored = []
        for nid, data in G.nodes(data=True):
            label = data.get("label", "").lower()
            source = data.get("source_file", "").lower()
            score = sum(1 for t in terms if t in label) + sum(0.5 for t in terms if t in source)
            if score > 0:
                scored.append((score, nid))
        return sorted(scored, reverse=True)

    @staticmethod
    def _find_node_ids(G: nx.DiGraph, query: str) -> list[str]:
        """模糊查找节点 ID（大小写不敏感，子串匹配）"""
        q = query.lower()
        results = []
        for nid, data in G.nodes(data=True):
            label = data.get("label", "").lower()
            if q in label or q == nid.lower():
                results.append(nid)
        return results

    # ── BFS 遍历（移植自 graphify serve.py）──────────────

    @staticmethod
    def _bfs(G: nx.DiGraph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
        visited: set[str] = set(start_nodes)
        frontier = set(start_nodes)
        edges_seen: list[tuple] = []
        for _ in range(depth):
            next_frontier: set[str] = set()
            for n in frontier:
                if n not in G:
                    continue
                for neighbor in G.neighbors(n):
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                        edges_seen.append((n, neighbor))
            visited.update(next_frontier)
            frontier = next_frontier
        return visited, edges_seen

    # ── Actions ──────────────────────────────────────────

    def _neighbors(self, G: nx.DiGraph, node_query: str) -> ToolResult:
        if not node_query:
            return ToolResult.err("未指定节点")

        matched = self._find_node_ids(G, node_query)
        if not matched:
            return ToolResult.err(f"节点不存在: {node_query}")

        nid = matched[0]
        data = G.nodes[nid]
        neighbors = []
        for nb in G.neighbors(nid):
            edge_data = G.edges[nid, nb] if G.has_edge(nid, nb) else {}
            neighbors.append({
                "id": nb,
                "label": G.nodes[nb].get("label", nb),
                "type": G.nodes[nb].get("type", ""),
                "relation": edge_data.get("relation", ""),
            })
        # 也查入边（谁指向这个节点）
        for pred in G.predecessors(nid):
            edge_data = G.edges[pred, nid] if G.has_edge(pred, nid) else {}
            neighbors.append({
                "id": pred,
                "label": G.nodes[pred].get("label", pred),
                "type": G.nodes[pred].get("type", ""),
                "relation": f"<-{edge_data.get('relation', '')}",
            })

        return ToolResult.ok({
            "node": {"id": nid, "label": data.get("label", nid), "type": data.get("type", "")},
            "neighbors": neighbors,
            "degree": len(neighbors),
        })

    def _search(self, G: nx.DiGraph, params: dict) -> ToolResult:
        """评分搜索 + BFS 扩展：先找匹配节点，再展开关联子图"""
        query = params.get("query", "")
        if not query:
            return ToolResult.err("空搜索")

        terms = [t.lower() for t in query.split() if len(t) > 1]
        if not terms:
            terms = [query.lower()]

        scored = self._score_nodes(G, terms)
        max_results = params.get("top_k", 20)

        if not scored:
            return ToolResult.ok({"query": query, "results": [], "count": 0, "expanded": 0})

        # 直接匹配的节点
        direct_results = []
        for score, nid in scored[:max_results]:
            data = G.nodes[nid]
            direct_results.append({
                "id": nid,
                "label": data.get("label", nid),
                "type": data.get("type", ""),
                "tags": data.get("tags", []),
                "community": data.get("community", -1),
                "degree": G.degree(nid),
                "score": score,
            })

        # BFS 扩展：从 top 3 匹配节点出发，1 跳扩展
        start_nodes = [nid for _, nid in scored[:3]]
        expanded_nodes, expanded_edges = self._bfs(G, start_nodes, depth=1)

        # 收集扩展发现的新节点（排除直接匹配）
        direct_ids = {nid for _, nid in scored}
        related = []
        for nid in expanded_nodes:
            if nid not in direct_ids:
                data = G.nodes[nid]
                related.append({
                    "id": nid,
                    "label": data.get("label", nid),
                    "type": data.get("type", ""),
                    "degree": G.degree(nid),
                })

        return ToolResult.ok({
            "query": query,
            "results": direct_results,
            "count": len(direct_results),
            "expanded": len(related),
            "related": related[:10],
        })

    def _community(self, G: nx.DiGraph, communities: dict, community_id: Any = None) -> ToolResult:
        if community_id is not None:
            try:
                cid = int(community_id)
            except (ValueError, TypeError):
                return ToolResult.err(f"社区 ID 无效: {community_id}")
            if cid not in communities:
                return ToolResult.err(f"社区不存在: {community_id}")
            node_ids = communities[cid]
            nodes = []
            for nid in node_ids:
                data = G.nodes[nid] if nid in G else {}
                nodes.append({
                    "id": nid,
                    "label": data.get("label", nid),
                    "type": data.get("type", ""),
                })
            return ToolResult.ok({"community_id": cid, "nodes": nodes, "size": len(nodes)})

        overview = [
            {"community_id": cid, "size": len(node_list)}
            for cid, node_list in communities.items()
        ]
        return ToolResult.ok({"communities": overview, "total": len(communities)})

    def _isolates(self, G: nx.DiGraph) -> ToolResult:
        isolates = []
        for nid in nx.isolates(G):
            data = G.nodes[nid] if nid in G else {}
            isolates.append({
                "id": nid,
                "label": data.get("label", nid),
                "type": data.get("type", ""),
            })
        return ToolResult.ok({"isolates": isolates, "count": len(isolates)})

    def _stats(self, G: nx.DiGraph, communities: dict) -> ToolResult:
        return ToolResult.ok({
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "communities": len(communities),
            "isolates": sum(1 for _ in nx.isolates(G)),
        })

    def _shortest_path(self, G: nx.DiGraph, source: str, target: str) -> ToolResult:
        """两个概念之间的最短路径"""
        if not source or not target:
            return ToolResult.err("需要 source 和 target 参数")

        src_matches = self._find_node_ids(G, source)
        tgt_matches = self._find_node_ids(G, target)
        if not src_matches:
            return ToolResult.err(f"找不到节点: {source}")
        if not tgt_matches:
            return ToolResult.err(f"找不到节点: {target}")

        src_nid, tgt_nid = src_matches[0], tgt_matches[0]

        # 用无向图找路径（知识图谱的双向关联）
        try:
            path = nx.shortest_path(G.to_undirected(), src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return ToolResult.err(f"{source} 和 {target} 之间没有路径")

        # 构建路径描述
        path_labels = []
        for nid in path:
            data = G.nodes[nid] if nid in G else {}
            path_labels.append(data.get("label", nid))

        return ToolResult.ok({
            "source": source,
            "target": target,
            "hops": len(path) - 1,
            "path": path_labels,
            "path_ids": path,
        })

    def _explore(self, G: nx.DiGraph, params: dict) -> ToolResult:
        """BFS 探索：从一个概念出发，发现关联子图"""
        query = params.get("query", "")
        depth = min(int(params.get("depth", 2)), 4)

        if not query:
            return ToolResult.err("需要 query 参数")

        terms = [t.lower() for t in query.split() if len(t) > 1]
        if not terms:
            terms = [query.lower()]

        scored = self._score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]
        if not start_nodes:
            return ToolResult.err(f"找不到匹配节点: {query}")

        visited, edges = self._bfs(G, start_nodes, depth)

        # 构建子图描述
        nodes_info = []
        for nid in sorted(visited, key=lambda n: G.degree(n) if n in G else 0, reverse=True):
            data = G.nodes[nid] if nid in G else {}
            nodes_info.append({
                "id": nid,
                "label": data.get("label", nid),
                "type": data.get("type", ""),
                "degree": G.degree(nid) if nid in G else 0,
                "community": data.get("community", -1),
            })

        edges_info = []
        for u, v in edges:
            edge_data = G.edges[u, v] if G.has_edge(u, v) else {}
            edges_info.append({
                "source": G.nodes[u].get("label", u) if u in G else u,
                "target": G.nodes[v].get("label", v) if v in G else v,
                "relation": edge_data.get("relation", ""),
            })

        return ToolResult.ok({
            "query": query,
            "depth": depth,
            "start_nodes": [G.nodes[n].get("label", n) for n in start_nodes if n in G],
            "nodes": nodes_info,
            "edges": edges_info,
            "total_nodes": len(nodes_info),
            "total_edges": len(edges_info),
        })
