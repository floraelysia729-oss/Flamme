"""图谱构建 Tool — 从 vault .md 文件提取 wikilink，构建知识图谱

流程：
  扫描 vault .md → 解析 frontmatter + [[wikilinks]] → extraction dict
  → graphify.build_from_json() → NetworkX 图 → graphify.cluster() Leiden 社区检测
  → 导出 graph.json (邻接表) + graph.mermaid (人读)
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import yaml

from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult


# ── Wikilink 提取 ──────────────────────────────────────────────

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
_TAG_INLINE_RE = re.compile(r"#([a-zA-Z\u4e00-\u9fff][\w\u4e00-\u9fff/-]*)")


def extract_wikilinks(text: str) -> list[str]:
    """从文本中提取 [[wikilink]] 目标"""
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def extract_tags(metadata: dict, content: str) -> list[str]:
    """从 frontmatter tags + 正文 #tag 提取标签"""
    tags = set()
    # frontmatter tags
    for t in metadata.get("tags", []):
        tags.add(str(t).strip())
    # 正文 inline tags（排除标题 # ）
    for m in _TAG_INLINE_RE.finditer(content):
        tags.add(m.group(1))
    return sorted(tags)


def _node_id(name: str) -> str:
    """规范化节点 ID"""
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", name).strip("_").lower() or name.lower()


def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── GraphBuilder Tool ──────────────────────────────────────────


class GraphBuilder(BaseTool):
    """图谱构建 — 扫描 vault .md → 提取 wikilink → 构建 NetworkX 图 → 导出

    execute params: {"vault_path": str, "output_dir": str (optional), "incremental": bool (default True)}
    returns: {"nodes": int, "edges": int, "communities": int, "output_dir": str}
    """

    name = "graph_builder"
    description = "从 vault 构建/更新知识图谱，输出 graph.json + graph.mermaid"
    is_concurrency_safe = False    # 写文件 + 写 DB，不可并行
    is_read_only = False
    interrupt_behavior = InterruptBehavior.BLOCK  # 构建过程不可中断
    max_result_chars = 1_000

    def __init__(self):
        self._db = None  # 外部注入 SQLiteClient

    @staticmethod
    def _to_relpath(abs_path: str | Path, vault_path: str) -> str:
        """绝对路径 → vault 相对路径（正斜杠）"""
        try:
            return str(Path(abs_path).relative_to(vault_path)).replace("\\", "/")
        except ValueError:
            return str(Path(abs_path)).replace("\\", "/")

    def execute(self, params: dict) -> ToolResult:
        vault_path = params.get("vault_path", "")
        if not vault_path:
            return ToolResult.err("未指定 vault_path")

        output_dir = params.get("output_dir", "")
        incremental = params.get("incremental", True)
        export_json = params.get("export_json", False)

        # 默认输出目录 — 从 vault_path 派生，不调 load_config()
        if not output_dir:
            output_dir = str(Path(vault_path) / ".wiki")

        # 1. 扫描 .md 文件（含 vault/entities/ 下的 entity .md）
        md_files = self._find_markdown_files(vault_path)

        if not md_files:
            return ToolResult.err(f"vault 中没有可用的内容文件: {vault_path}")

        nodes, edges = self._extract_all(md_files, incremental, output_dir, vault_path)

        if not nodes:
            return ToolResult.err("没有提取到有效节点")

        # 5. 构建 NetworkX 图 + 社区检测
        graph, communities = self._build_graph(nodes, edges)

        # 6. 写入 SQLite（主目标，写入全字段含 community）
        node_to_community = {}
        for cid, node_list in communities.items():
            for nid in node_list:
                node_to_community[nid] = cid
        self._write_to_sqlite(nodes, edges, node_to_community)

        # 7. 可选导出 graph.json + graph.mermaid
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        if export_json:
            json_path = str(Path(output_dir) / "graph.json")
            mermaid_path = str(Path(output_dir) / "graph.mermaid")
            self._write_json(graph, communities, json_path)
            self._write_mermaid(graph, communities, mermaid_path)

        return ToolResult.ok({
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "communities": len(communities),
            "output_dir": output_dir,
        })

    def _load_existing_hashes(self, output_dir: str) -> dict:
        """从已有 graph.json 加载 source_file → content_hash 映射"""
        json_path = Path(output_dir) / "graph.json"
        if not json_path.exists():
            return {}
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        hashes = {}
        for nid, attrs in data.get("nodes", {}).items():
            sf = attrs.get("source_file", "")
            ch = attrs.get("content_hash", "")
            if sf and ch:
                hashes[sf] = ch
        return hashes

    SKIP_DIRS = {".wiki", ".obsidian", ".git", "node_modules", ".trash", ".flamme"}
    SKIP_SUFFIXES = (".excalidraw.md", ".ocr.md")

    def _find_markdown_files(self, vault_path: str) -> list[Path]:
        """递归查找所有 .md 文件（排除噪声目录和辅助文件）"""
        vault = Path(vault_path)
        files = []
        for p in vault.rglob("*.md"):
            if any(part in self.SKIP_DIRS for part in p.parts):
                continue
            if p.name.endswith(self.SKIP_SUFFIXES):
                continue
            files.append(p)
        return sorted(files)

    def _extract_all(self, md_files: list[Path], incremental: bool,
                     output_dir: str, vault_path: str) -> tuple[list[dict], list[dict]]:
        """从所有 .md 文件（含 entity）统一提取节点和边。

        source_file 统一存储 vault 相对路径（正斜杠），保证可移植。
        两遍扫描：Pass 1 建所有节点，Pass 2 连边（解决文件序依赖）。

        Entity 文件通过 frontmatter type 字段识别，sources 字段创建 entity→document 边。
        """
        nodes = {}  # id → node dict
        # Pass 1 收集的边数据，供 Pass 2 建边
        pending_edges: list[tuple[str, str, str, str]] = []  # (src_id, tgt_id, etype, rel_path)

        # 增量：加载已有 hash 映射，跳过未变更文件
        existing_hashes = {}
        if incremental:
            existing_hashes = self._load_existing_hashes(output_dir)

        # ── Pass 1: 创建所有节点 + 收集边数据 ──
        for fp in md_files:
            try:
                raw = fp.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    raw = fp.read_text(encoding="gbk", errors="replace")
                except Exception:
                    continue
            content_hash = _compute_hash(raw)
            rel_path = self._to_relpath(fp, vault_path)

            # 增量跳过：文件内容未变更
            if incremental and rel_path in existing_hashes:
                if existing_hashes[rel_path] == content_hash:
                    continue

            # 解析 frontmatter
            metadata, content = self._parse_frontmatter(raw)

            # 节点
            title = metadata.get("title", fp.stem)
            node_id = _node_id(title)

            # 判断 wiki 页类型（frontmatter type 或路径在 entities/topics/ 等下）
            wiki_page_parts = {"entities", "topics", "comparisons", "explorations"}
            page_type = metadata.get("type", "")
            is_wiki_page = (
                page_type in ("entity", "concept", "topic", "comparison", "exploration")
                or any(p in wiki_page_parts for p in fp.parts)
            )
            is_entity = page_type in ("entity", "concept") or "entities" in fp.parts

            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": title,
                    "type": page_type or ("concept" if is_entity else "document"),
                    "file_type": "entity" if is_entity else ("wiki_page" if is_wiki_page else "document"),
                    "source_file": rel_path,
                    "tags": extract_tags(metadata, content),
                    "level": metadata.get("level", ""),
                    "content_hash": content_hash,
                }

            # 收集 wikilink 边（Pass 2 处理）
            for target in extract_wikilinks(content):
                pending_edges.append((node_id, _node_id(target), "wikilink", rel_path))

            # 收集 frontmatter related 边
            for rel in metadata.get("related", []):
                if not isinstance(rel, str):
                    continue
                rel_name = rel.strip("[]").strip()
                if rel_name:
                    pending_edges.append((node_id, _node_id(rel_name), "frontmatter", rel_path))

            # Entity sources → document 边
            if is_entity:
                for src in metadata.get("sources", []):
                    src_name = str(src).strip("[]").strip()
                    if not src_name:
                        continue
                    src_id = _node_id(src_name)
                    # 为 source document 创建占位节点（如果尚不存在）
                    if src_id not in nodes:
                        nodes[src_id] = {
                            "id": src_id,
                            "label": src_name,
                            "type": "document",
                            "file_type": "document",
                            "source_file": "",
                            "tags": [],
                            "level": "",
                            "content_hash": "",
                        }
                    pending_edges.append((src_id, node_id, "has_entity", rel_path))

        # ── Pass 2: 连边（所有节点已存在） ──
        edges = []
        for src_id, tgt_id, _etype, rel_path in pending_edges:
            if tgt_id in nodes:
                edges.append({
                    "source": src_id,
                    "target": tgt_id,
                    "relation": _etype if _etype == "has_entity" else "related_to",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": rel_path,
                })

        return list(nodes.values()), edges

    def _parse_frontmatter(self, raw: str) -> tuple[dict, str]:
        """分离 frontmatter 和正文"""
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not match:
            return {}, raw
        try:
            metadata = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            metadata = {}
        content = raw[match.end():]
        return metadata, content

    def _build_graph(self, nodes: list[dict], edges: list[dict]):
        """构建 NetworkX 图 + Leiden 社区检测（graphify 不可用时降级为纯 NetworkX）"""
        try:
            from graphify.build import build_from_json
            from graphify.cluster import cluster

            extraction = {"nodes": nodes, "edges": edges}
            G = build_from_json(extraction)
            communities = cluster(G) if G.number_of_edges() > 0 else {}
            return G, communities
        except ImportError:
            # 降级：纯 NetworkX 构建（无 Leiden 社区检测）
            import networkx as nx
            G = nx.DiGraph()
            for n in nodes:
                G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
            for e in edges:
                G.add_edge(e["source"], e["target"],
                           **{k: v for k, v in e.items() if k not in ("source", "target")})
            return G, {}

    def _write_json(self, G, communities: dict, path: str) -> None:
        """导出邻接表 graph.json"""
        from networkx.readwrite import json_graph

        # 节点数据
        node_data = json_graph.node_link_data(G)

        # 构建社区映射
        node_to_community = {}
        for cid, node_list in communities.items():
            for nid in node_list:
                node_to_community[nid] = cid

        # 社区信息
        community_info = {}
        for cid, node_list in communities.items():
            community_info[str(cid)] = {
                "nodes": node_list,
                "size": len(node_list),
            }

        output = {
            "nodes": {},
            "edges": [],
            "communities": community_info,
            "stats": {
                "nodes": G.number_of_nodes(),
                "edges": G.number_of_edges(),
                "communities": len(communities),
                "updated_at": datetime.now().isoformat(),
            },
        }

        # 邻接表格式
        for node in node_data.get("nodes", []):
            nid = node.get("id", node.get("node", ""))
            attrs = {k: v for k, v in node.items() if k not in ("id", "node")}
            attrs["community"] = node_to_community.get(nid, -1)
            output["nodes"][nid] = attrs

        for link in node_data.get("links", node_data.get("edges", [])):
            edge_info = {
                "source": link.get("source"),
                "target": link.get("target"),
            }
            if "relation" in link:
                edge_info["relation"] = link["relation"]
            output["edges"].append(edge_info)

        Path(path).write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_mermaid(self, G, communities: dict, path: str) -> None:
        """导出 Mermaid 图（人读）"""
        lines = ["graph LR"]

        # 节点社区映射
        node_to_community = {}
        for cid, node_list in communities.items():
            for nid in node_list:
                node_to_community[nid] = cid

        # 按社区分组输出
        written_edges = set()
        for u, v, data in G.edges(data=True):
            edge_key = (min(u, v), max(u, v))
            if edge_key in written_edges:
                continue
            written_edges.add(edge_key)
            # Mermaid 安全 ID：替换特殊字符
            u_safe = _mermaid_id(u)
            v_safe = _mermaid_id(v)
            u_label = G.nodes[u].get("label", u)
            v_label = G.nodes[v].get("label", v)
            lines.append(f"    {u_safe}[\"{u_label}\"] --> {v_safe}[\"{v_label}\"]")

        # 孤立节点
        for nid in G.nodes():
            if G.degree(nid) == 0:
                safe = _mermaid_id(nid)
                label = G.nodes[nid].get("label", nid)
                lines.append(f"    {safe}[\"{label}\"]")

        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_to_sqlite(self, nodes: list[dict], edges: list[dict],
                         node_to_community: dict[str, int] | None = None) -> None:
        """将提取的实体和关系写入 SQLite（全字段）"""
        if not self._db:
            return
        community_map = node_to_community or {}
        for node in nodes:
            nid = node.get("id", "")
            self._db.upsert_entity(
                name=node["label"],
                entity_type=node.get("type", "concept"),
                wiki_path=node.get("source_file", ""),
                community=community_map.get(nid, -1),
                tags=",".join(node.get("tags", [])),
                entity_file="",
                source_file=node.get("source_file", ""),
                level=node.get("level", ""),
                content_hash=node.get("content_hash", ""),
            )
        for edge in edges:
            source_node = next((n for n in nodes if n["id"] == edge["source"]), None)
            target_node = next((n for n in nodes if n["id"] == edge["target"]), None)
            if source_node and target_node:
                self._db.upsert_relation(
                    source_name=source_node["label"],
                    target_name=target_node["label"],
                    relation_type=edge.get("relation", "related_to"),
                    source_doc=edge.get("source_file", ""),
                )


def _mermaid_id(s: str) -> str:
    """生成 Mermaid 安全的节点 ID"""
    return "n" + hashlib.md5(s.encode()).hexdigest()[:8]
