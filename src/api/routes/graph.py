"""图谱路由 — 数据、邻居、统计、构建

查询来源：SQLite entities/relations 表（通过 GraphStore）
"""

from pathlib import Path

from fastapi import APIRouter, Request

from src.api.deps import get_request_config_or_default
from src.api.runtime import build_db, build_tools
from src.db.graph_store import GraphStore

router = APIRouter(prefix="/graph")


def _graph_store(cfg) -> GraphStore:
    """从 per-request Config 构建 GraphStore"""
    db = build_db(cfg)
    return GraphStore(db._conn)


def _to_force_graph_format(data: dict) -> dict:
    """将 GraphStore 返回的 {nodes, edges} 转换为 react-force-graph-2d 标准格式"""
    nodes_list = data.get("nodes", [])
    edges_list = data.get("edges", [])

    # 计算 degree
    degree_map: dict[int, int] = {}
    for e in edges_list:
        # GraphStore 返回 source/target 是 name 字符串
        src = e.get("source", "")
        tgt = e.get("target", "")
        degree_map[src] = degree_map.get(src, 0) + 1
        degree_map[tgt] = degree_map.get(tgt, 0) + 1

    nodes = []
    for n in nodes_list:
        node_id = n.get("name", str(n.get("id", "")))
        source_file = n.get("source_file", n.get("wiki_path", ""))
        display = Path(source_file).stem if source_file else node_id
        if "/" in node_id or "\\" in node_id:
            display = Path(node_id.replace("\\", "/")).stem
        degree = degree_map.get(node_id, 0)
        node_item = {
            "id": node_id,
            "label": display,
            "type": n.get("type", "document"),
            "level": n.get("level", ""),
            "tags": n.get("tags", "").split(",") if n.get("tags") else [],
            "community": n.get("community", -1),
            "val": max(degree, 1) if degree == 0 else degree,
            "source_file": source_file,
        }
        nodes.append(node_item)

    edges = []
    for e in edges_list:
        edges.append({
            "source": e.get("source", ""),
            "target": e.get("target", ""),
            "label": e.get("relation_type", ""),
        })

    return {"nodes": nodes, "edges": edges}


@router.get("/full")
def get_full_graph(request: Request):
    """返回标准 {nodes, edges} JSON — react-force-graph-2d 格式"""
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    data = store.get_full_graph()
    return _to_force_graph_format(data)


@router.get("/subgraph")
def get_subgraph(request: Request, entity: str, depth: int = 1):
    """返回以某实体为中心的局部子图"""
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    data = store.bfs_subgraph(entity, depth)
    return _to_force_graph_format(data)


@router.get("/data")
def get_graph_data(request: Request):
    """原始格式（向后兼容）"""
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    return store.get_full_graph()


@router.get("/neighbors/{node:path}")
def get_neighbors(request: Request, node: str):
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    return store.get_neighbors(node)


@router.get("/stats")
def get_graph_stats(request: Request):
    cfg = get_request_config_or_default(request)
    store = _graph_store(cfg)
    return store.get_stats()


@router.post("/build")
def build_graph(request: Request):
    from src.tools.interfaces import ToolResult

    cfg = get_request_config_or_default(request)
    runtime = build_tools(cfg)
    db = runtime["db"]
    registry = runtime["registry"]
    try:
        build_tool = registry.get("graph_builder")
        if not build_tool:
            return {"error": "graph_builder 未注册"}
        result = build_tool.execute({"vault_path": cfg.vault_path})
        if isinstance(result, ToolResult):
            if result.is_error:
                return {"error": result.error}
        elif isinstance(result, dict) and "error" in result:
            return {"error": result["error"]}
        store = GraphStore(db._conn)
        return _to_force_graph_format(store.get_full_graph())
    except Exception as e:
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
    finally:
        db.close()
