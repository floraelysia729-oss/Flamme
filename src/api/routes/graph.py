"""图谱路由 — 数据、邻居、统计、构建"""

import json
from collections import deque
from pathlib import Path

from fastapi import APIRouter

from src.api.deps import get_db, get_tool_registry, get_config

router = APIRouter(prefix="/graph")


def _graph_path() -> str:
    cfg = get_config()
    return cfg.graph_json if Path(cfg.graph_json).exists() else ""


def _load_graph() -> dict:
    gp = _graph_path()
    if not gp:
        return {"nodes": {}, "edges": [], "communities": {}}
    data = json.loads(Path(gp).read_text(encoding="utf-8"))
    raw_nodes = data.get("nodes", [])

    # Auto-detect: graphify gives nodes as list [{id,...}], legacy gives dict {id: {...}}
    if isinstance(raw_nodes, list):
        nodes_dict: dict = {}
        for n in raw_nodes:
            nid = n.get("id", "")
            nodes_dict[nid] = {
                "label": n.get("label", nid),
                "type": n.get("file_type", n.get("type", "document")),
                "community": n.get("community"),
                "source_file": n.get("source_file", ""),
                "level": "",
                "tags": [],
            }
        raw_links = data.get("links", data.get("edges", []))
        edges = [{"source": l.get("source", ""), "target": l.get("target", ""),
                  "relation": l.get("relation", "")} for l in raw_links]
        communities: dict = {}
        for nid, attrs in nodes_dict.items():
            cid = attrs.get("community")
            if cid is not None:
                communities.setdefault(cid, []).append(nid)
        return {"nodes": nodes_dict, "edges": edges, "communities": communities}

    return {
        "nodes": raw_nodes,
        "edges": data.get("edges", []),
        "communities": data.get("communities", {}),
    }


def _to_force_graph_format(data: dict) -> dict:
    """将 graph.json 邻接表格式转换为 react-force-graph-2d 标准格式"""
    nodes_dict = data.get("nodes", {})
    edges_list = data.get("edges", [])

    # 构建邻接关系以计算 degree
    degree_map: dict[str, int] = {}
    for e in edges_list:
        src = e.get("source", "")
        tgt = e.get("target", "")
        degree_map[src] = degree_map.get(src, 0) + 1
        degree_map[tgt] = degree_map.get(tgt, 0) + 1

    nodes = []
    for nid, attrs in nodes_dict.items():
        if degree_map.get(nid, 0) == 0:
            continue
        node_item = {
            "id": nid,
            "label": attrs.get("label", nid),
            "type": attrs.get("type", "document"),
            "level": attrs.get("level", ""),
            "tags": attrs.get("tags", []),
            "community": attrs.get("community", -1),
            "val": degree_map[nid],
            "source_file": attrs.get("source_file", ""),
        }
        entity_file = attrs.get("entity_file", "")
        if entity_file:
            node_item["entity_file"] = entity_file
        nodes.append(node_item)

    edges = []
    for e in edges_list:
        edges.append({
            "source": e.get("source", ""),
            "target": e.get("target", ""),
            "label": e.get("relation", ""),
        })

    return {"nodes": nodes, "edges": edges}


@router.get("/full")
def get_full_graph():
    """返回标准 {nodes, edges} JSON — react-force-graph-2d 格式"""
    data = _load_graph()
    return _to_force_graph_format(data)


@router.get("/subgraph")
def get_subgraph(entity: str, depth: int = 1):
    """返回以某实体为中心的局部子图（BFS）"""
    data = _load_graph()
    nodes_dict = data.get("nodes", {})
    edges_list = data.get("edges", [])

    # 找匹配节点
    matched_id = None
    entity_lower = entity.lower()
    for nid, attrs in nodes_dict.items():
        if nid.lower() == entity_lower or attrs.get("label", "").lower() == entity_lower:
            matched_id = nid
            break

    if not matched_id:
        return {"nodes": [], "edges": []}

    # BFS 扩展
    visited = {matched_id}
    queue = deque([(matched_id, 0)])

    while queue:
        current, d = queue.popleft()
        if d >= depth:
            continue
        for e in edges_list:
            src, tgt = e.get("source", ""), e.get("target", "")
            neighbor = None
            if src == current:
                neighbor = tgt
            elif tgt == current:
                neighbor = src
            if neighbor and neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, d + 1))

    # 过滤节点和边
    filtered_nodes = {nid: attrs for nid, attrs in nodes_dict.items() if nid in visited}
    filtered_edges = [
        e for e in edges_list
        if e.get("source", "") in visited and e.get("target", "") in visited
    ]

    return _to_force_graph_format({"nodes": filtered_nodes, "edges": filtered_edges})


@router.get("/data")
def get_graph_data():
    """原始邻接表格式（向后兼容）"""
    return _load_graph()


@router.get("/neighbors/{node:path}")
def get_neighbors(node: str):
    graph = _load_graph()
    nodes = graph.get("nodes", {})
    edges = graph.get("edges", [])

    matched = None
    for nid, attrs in nodes.items():
        if nid == node or attrs.get("label") == node:
            matched = {"id": nid, **attrs}
            break
    if not matched:
        return {"node": node, "neighbors": [], "degree": 0, "error": "not found"}

    neighbors = []
    node_id = matched.get("id", node)
    for e in edges:
        if e.get("source") == node_id:
            target_attrs = nodes.get(e.get("target", ""), {})
            neighbors.append({"id": e["target"], "label": target_attrs.get("label", ""),
                              "relation": e.get("relation", "")})
        elif e.get("target") == node_id:
            src_attrs = nodes.get(e.get("source", ""), {})
            neighbors.append({"id": e["source"], "label": src_attrs.get("label", ""),
                              "relation": e.get("relation", "")})
    return {"node": {"id": node_id, "label": matched.get("label", node)},
            "neighbors": neighbors, "degree": len(neighbors)}


@router.get("/stats")
def get_graph_stats():
    graph = _load_graph()
    return {"nodes": len(graph.get("nodes", {})),
            "edges": len(graph.get("edges", [])),
            "communities": len(graph.get("communities", {}))}


@router.post("/build")
def build_graph():
    try:
        tools = get_tool_registry()
        build_tool = tools.get("graph_builder")
        if not build_tool:
            return {"error": "graph_builder 未注册"}
        cfg = get_config()
        from src.tools.interfaces import ToolResult
        result = build_tool.execute({"vault_path": cfg.vault_path})
        if isinstance(result, ToolResult):
            if result.is_error:
                return {"error": result.error}
        elif isinstance(result, dict) and "error" in result:
            return {"error": result["error"]}
        return get_full_graph()
    except Exception as e:
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
    return get_full_graph()
