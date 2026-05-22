"""GraphStore — 统一的 SQLite 图谱查询层

供 API 路由（graph.py）和 Agent Tool（graph_query.py）共用。
从 entities + relations 表查询，替代读 graph.json 静态文件。
"""

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


class GraphStore:
    """图谱查询 — 从 SQLite entities/relations 读取"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        conn.row_factory = sqlite3.Row

    # ── 节点查找 ─────────────────────────────────────────

    def get_node_by_name(self, name: str) -> dict | None:
        """精确匹配 name，返回 entity dict 或 None"""
        row = self._conn.execute(
            "SELECT * FROM entities WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def find_nodes(self, query: str) -> list[dict]:
        """模糊查找：name LIKE %query%（大小写不敏感）"""
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE name LIKE ? COLLATE NOCASE",
            (pattern,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 全图 ─────────────────────────────────────────────

    def get_full_graph(self) -> dict:
        """返回所有 entities + relations"""
        nodes = [dict(r) for r in self._conn.execute(
            "SELECT id, name, type, wiki_path, community, tags, "
            "entity_file, source_file, level FROM entities"
        ).fetchall()]
        edges = [dict(r) for r in self._conn.execute(
            "SELECT r.id, e1.name AS source, e2.name AS target, "
            "r.relation_type, r.confidence, r.source_doc "
            "FROM relations r "
            "JOIN entities e1 ON r.source_entity = e1.id "
            "JOIN entities e2 ON r.target_entity = e2.id"
        ).fetchall()]
        return {"nodes": nodes, "edges": edges}

    # ── 邻居查询 ─────────────────────────────────────────

    def get_neighbors(self, node_name: str) -> dict:
        """查询指定节点的所有邻居（出边 + 入边）"""
        entity = self.get_node_by_name(node_name)
        if not entity:
            # 精确匹配失败，尝试模糊匹配
            matches = self.find_nodes(node_name)
            if not matches:
                return {"node": node_name, "neighbors": [], "degree": 0, "error": "not found"}
            entity = matches[0]

        eid = entity["id"]
        neighbors = []

        # 出边
        rows = self._conn.execute(
            """SELECT e2.name, e2.type, r.relation_type
               FROM relations r
               JOIN entities e2 ON r.target_entity = e2.id
               WHERE r.source_entity = ?""",
            (eid,),
        ).fetchall()
        for r in rows:
            neighbors.append({"id": r["name"], "label": r["name"],
                              "type": r["type"], "relation": r["relation_type"]})

        # 入边
        rows = self._conn.execute(
            """SELECT e1.name, e1.type, r.relation_type
               FROM relations r
               JOIN entities e1 ON r.source_entity = e1.id
               WHERE r.target_entity = ?""",
            (eid,),
        ).fetchall()
        for r in rows:
            neighbors.append({"id": r["name"], "label": r["name"],
                              "type": r["type"], "relation": f"<-{r['relation_type']}"})

        return {"node": {"id": eid, "name": entity["name"], "label": entity["name"]},
                "neighbors": neighbors, "degree": len(neighbors)}

    # ── BFS 子图 ─────────────────────────────────────────

    def bfs_subgraph(self, entity_name: str, depth: int = 1) -> dict:
        """SQLite 递归 CTE 实现 BFS 遍历，返回子图"""
        depth = min(depth, 4)

        entity = self.get_node_by_name(entity_name)
        if not entity:
            # 尝试模糊匹配
            matches = self.find_nodes(entity_name)
            if not matches:
                return {"nodes": [], "edges": []}
            entity = matches[0]

        eid = entity["id"]

        # 递归 CTE：从 eid 出发，沿 relations 双向扩展 depth 跳
        cte_sql = f"""
        WITH RECURSIVE bfs(level, node_id) AS (
            VALUES(0, ?)
            UNION
            SELECT b.level + 1, CASE
                WHEN r.source_entity = b.node_id THEN r.target_entity
                ELSE r.source_entity
            END
            FROM bfs b
            JOIN relations r ON (r.source_entity = b.node_id OR r.target_entity = b.node_id)
            WHERE b.level < ?
        )
        SELECT DISTINCT node_id FROM bfs WHERE node_id IS NOT NULL
        """
        visited_rows = self._conn.execute(cte_sql, (eid, depth)).fetchall()
        visited_ids = {r["node_id"] for r in visited_rows}

        if not visited_ids:
            return {"nodes": [], "edges": []}

        # 查节点
        placeholders = ",".join("?" * len(visited_ids))
        nodes = [dict(r) for r in self._conn.execute(
            f"SELECT id, name, type, wiki_path, community, tags, "
            f"entity_file, source_file, level FROM entities WHERE id IN ({placeholders})",
            list(visited_ids),
        ).fetchall()]

        # 查边
        edges = [dict(r) for r in self._conn.execute(
            f"""SELECT e1.name AS source, e2.name AS target, r.relation_type
                FROM relations r
                JOIN entities e1 ON r.source_entity = e1.id
                JOIN entities e2 ON r.target_entity = e2.id
                WHERE r.source_entity IN ({placeholders})
                  AND r.target_entity IN ({placeholders})""",
            list(visited_ids) + list(visited_ids),
        ).fetchall()]

        return {"nodes": nodes, "edges": edges}

    # ── 搜索 ─────────────────────────────────────────────

    def search_nodes(self, query: str, top_k: int = 20) -> list[dict]:
        """LIKE 模糊搜索节点名，按 degree 降序"""
        pattern = f"%{query}%"

        # 按 degree（关系数量）降序排列
        rows = self._conn.execute(
            """SELECT e.*,
                (SELECT COUNT(*) FROM relations r
                 WHERE r.source_entity = e.id OR r.target_entity = e.id) AS degree
               FROM entities e
               WHERE e.name LIKE ? COLLATE NOCASE
               ORDER BY degree DESC
               LIMIT ?""",
            (pattern, top_k),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 统计 ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        """图谱统计：节点、边、社区、孤立节点"""
        nodes = self._conn.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]
        edges = self._conn.execute("SELECT COUNT(*) AS c FROM relations").fetchone()["c"]
        communities = self._conn.execute(
            "SELECT COUNT(DISTINCT community) AS c FROM entities WHERE community >= 0"
        ).fetchone()["c"]
        # 孤立节点：无任何 relation 的 entity
        isolates = self._conn.execute(
            """SELECT COUNT(*) AS c FROM entities e
               WHERE e.id NOT IN (SELECT source_entity FROM relations)
                 AND e.id NOT IN (SELECT target_entity FROM relations)"""
        ).fetchone()["c"]
        return {"nodes": nodes, "edges": edges, "communities": communities, "isolates": isolates}

    # ── 最短路径 ─────────────────────────────────────────

    def shortest_path(self, source_name: str, target_name: str) -> dict:
        """SQLite 递归 CTE 找两个节点之间的最短路径"""
        src = self.get_node_by_name(source_name)
        tgt = self.get_node_by_name(target_name)
        if not src:
            return {"error": f"找不到节点: {source_name}"}
        if not tgt:
            return {"error": f"找不到节点: {target_name}"}

        src_id, tgt_id = src["id"], tgt["id"]
        if src_id == tgt_id:
            return {"source": source_name, "target": target_name,
                    "hops": 0, "path": [source_name], "path_ids": [src_id]}

        # BFS 找路径
        cte_sql = """
        WITH RECURSIVE bfs(level, node_id, path) AS (
            VALUES(0, ?, ?)
            UNION
            SELECT b.level + 1,
                CASE WHEN r.source_entity = b.node_id THEN r.target_entity
                     ELSE r.source_entity END,
                b.path || ',' || CAST(
                    CASE WHEN r.source_entity = b.node_id THEN r.target_entity
                         ELSE r.source_entity END AS TEXT)
            FROM bfs b
            JOIN relations r ON (r.source_entity = b.node_id OR r.target_entity = b.node_id)
            WHERE b.level < 10
              AND b.node_id != ?
        )
        SELECT path FROM bfs WHERE node_id = ? ORDER BY level LIMIT 1
        """
        row = self._conn.execute(cte_sql, (src_id, str(src_id), tgt_id, tgt_id)).fetchone()
        if not row:
            return {"error": f"{source_name} 和 {target_name} 之间没有路径"}

        path_ids = [int(x) for x in row["path"].split(",")]
        # 查节点名
        placeholders = ",".join("?" * len(path_ids))
        names = {r["id"]: r["name"] for r in self._conn.execute(
            f"SELECT id, name FROM entities WHERE id IN ({placeholders})", path_ids
        ).fetchall()}

        path_labels = [names.get(pid, str(pid)) for pid in path_ids]
        return {"source": source_name, "target": target_name,
                "hops": len(path_ids) - 1, "path": path_labels, "path_ids": path_ids}

    # ── 社区 ─────────────────────────────────────────────

    def get_community(self, community_id: int | None = None) -> dict:
        """查询社区信息"""
        if community_id is not None:
            rows = self._conn.execute(
                "SELECT id, name, type FROM entities WHERE community = ?",
                (community_id,),
            ).fetchall()
            nodes = [{"id": r["name"], "label": r["name"], "type": r["type"]} for r in rows]
            return {"community_id": community_id, "nodes": nodes, "size": len(nodes)}

        # 全部社区概览
        rows = self._conn.execute(
            "SELECT community, COUNT(*) AS size FROM entities WHERE community >= 0 "
            "GROUP BY community ORDER BY community"
        ).fetchall()
        return {"communities": [{"community_id": r["community"], "size": r["size"]} for r in rows],
                "total": len(rows)}

    # ── 孤立节点 ─────────────────────────────────────────

    def get_isolates(self) -> list[dict]:
        """返回所有无 relation 的孤立节点"""
        rows = self._conn.execute(
            """SELECT e.id, e.name, e.type FROM entities e
               WHERE e.id NOT IN (SELECT source_entity FROM relations)
                 AND e.id NOT IN (SELECT target_entity FROM relations)"""
        ).fetchall()
        return [{"id": r["name"], "label": r["name"], "type": r["type"]} for r in rows]
