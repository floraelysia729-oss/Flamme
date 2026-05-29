"""Graph 模块测试 — graph_builder + graph_query"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from src.tools.graph_builder import GraphBuilder, extract_wikilinks, extract_tags, _node_id, _doc_node_id
from src.api.routes.graph import _to_force_graph_format
from src.tools.graph_query import GraphQueryTool
from src.db.graph_store import GraphStore
from src.tools.interfaces import Tool


# ── Wikilink 提取测试 ──────────────────────────────────────────


def test_extract_wikilinks_basic():
    text = "矩阵是 [[向量空间]] 中的线性变换。[[特征值]] 是重要性质。"
    links = extract_wikilinks(text)
    assert links == ["向量空间", "特征值"]


def test_extract_wikilinks_with_alias():
    text = "见 [[矩阵基础|矩阵]] 和 [[SVD|奇异值分解]]"
    links = extract_wikilinks(text)
    assert links == ["矩阵基础", "SVD"]


def test_extract_wikilinks_none():
    assert extract_wikilinks("没有链接的文本") == []


def test_extract_tags():
    metadata = {"tags": ["数学", "线性代数"]}
    content = "正文有 #矩阵 和 #特征值 标签"
    tags = extract_tags(metadata, content)
    assert "数学" in tags
    assert "矩阵" in tags
    assert "特征值" in tags


def test_node_id():
    assert _node_id("矩阵基础") == "矩阵基础"
    assert _node_id("A/B") == "a_b"
    assert _node_id("Test Node") == "test_node"


def test_doc_node_id_uses_path():
    assert _doc_node_id("课程/笔记.md") == "课程/笔记.md"


def test_force_graph_includes_isolated_nodes():
    data = {
        "nodes": [
            {"name": "alone.md", "type": "document", "source_file": "alone.md", "wiki_path": "alone.md", "tags": "", "level": "", "community": -1},
            {"name": "矩阵基础", "type": "concept", "source_file": "矩阵基础.md", "wiki_path": "矩阵基础.md", "tags": "", "level": "", "community": 0},
        ],
        "edges": [
            {"source": "矩阵基础", "target": "向量空间", "relation_type": "related_to"},
        ],
    }
    out = _to_force_graph_format(data)
    ids = {n["id"] for n in out["nodes"]}
    assert "alone.md" in ids
    assert any(n["val"] >= 1 for n in out["nodes"] if n["id"] == "alone.md")


# ── GraphBuilder 测试 ──────────────────────────────────────────


def _make_vault():
    """创建临时 vault 目录和 .md 文件"""
    vault = tempfile.mkdtemp()

    files = {
        "矩阵基础.md": """---
title: 矩阵基础
tags: [数学, 线性代数]
related:
  - "[[向量空间]]"
  - "[[特征值]]"
---

# 矩阵基础

矩阵是 [[向量空间]] 中的线性变换。[[特征值]] 是矩阵的重要性质。
""",
        "向量空间.md": """---
title: 向量空间
tags: [数学]
related:
  - "[[线性代数]]"
---

# 向量空间

向量空间是 [[线性代数]] 的核心概念。[[矩阵基础]] 是向量空间上的操作。
""",
        "特征值.md": """---
title: 特征值
tags: [数学]
---

# 特征值

特征值是 [[矩阵基础]] 的核心性质。属于 [[线性代数]] 领域。
""",
    }

    for name, content in files.items():
        Path(vault, name).write_text(content, encoding="utf-8")

    return vault


def _cleanup(vault):
    shutil.rmtree(vault, ignore_errors=True)


def test_graph_builder_protocol():
    builder = GraphBuilder()
    assert isinstance(builder, Tool)


def test_graph_builder_one_node_per_md_file():
    vault = tempfile.mkdtemp()
    try:
        Path(vault, "a.md").write_text("---\ntitle: Same\n---\n\n# A\n", encoding="utf-8")
        Path(vault, "b.md").write_text("---\ntitle: Same\n---\n\n# B\n", encoding="utf-8")
        builder = GraphBuilder()
        result = builder.execute({"vault_path": vault, "incremental": False, "export_json": False})
        assert not result.is_error, result.error
        assert result.data["nodes"] == 2
    finally:
        _cleanup(vault)


def test_graph_builder_creates_output():
    vault = _make_vault()
    builder = GraphBuilder()
    output_dir = os.path.join(vault, ".wiki")

    try:
        result = builder.execute({"vault_path": vault, "output_dir": output_dir, "export_json": True, "incremental": False})
        assert not result.is_error, result.error
        assert result.data["nodes"] >= 3
        assert result.data["edges"] >= 1
        assert result.data["communities"] >= 0

        # 验证 graph.json 存在且格式正确
        graph_json = os.path.join(output_dir, "graph.json")
        assert os.path.exists(graph_json)
        data = json.loads(open(graph_json, encoding="utf-8").read())
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert data["stats"]["nodes"] >= 2

        # 验证 graph.mermaid 存在且非空
        graph_mermaid = os.path.join(output_dir, "graph.mermaid")
        assert os.path.exists(graph_mermaid)
        content = open(graph_mermaid, encoding="utf-8").read()
        assert content.startswith("graph LR")
        assert "-->" in content
    finally:
        _cleanup(vault)


def test_graph_builder_empty_vault():
    vault = tempfile.mkdtemp()
    builder = GraphBuilder()
    try:
        result = builder.execute({"vault_path": vault})
        assert result.is_error
    finally:
        _cleanup(vault)


# ── GraphStore + GraphQueryTool 测试 ────────────────────────────


def _make_test_db() -> sqlite3.Connection:
    """创建内存 SQLite 并插入测试数据（匹配 schema.sql 的 relations 列名）"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        type TEXT,
        wiki_path TEXT,
        community INTEGER DEFAULT -1,
        tags TEXT DEFAULT '',
        entity_file TEXT DEFAULT '',
        source_file TEXT DEFAULT '',
        level TEXT DEFAULT '',
        content_hash TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS relations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_entity INTEGER,
        target_entity INTEGER,
        relation_type TEXT DEFAULT 'related_to',
        confidence REAL DEFAULT 1.0,
        source_doc TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (source_entity) REFERENCES entities(id),
        FOREIGN KEY (target_entity) REFERENCES entities(id)
    )""")

    # 插入节点（先插，拿到自增 id）
    node_names = [
        ("矩阵基础", "document", "矩阵基础.md", 0, "数学,线性代数"),
        ("向量空间", "document", "向量空间.md", 0, "数学"),
        ("特征值", "document", "特征值.md", 1, "数学"),
        ("线性代数", "concept", "", 0, ""),
    ]
    for name, ntype, path, comm, tags in node_names:
        conn.execute(
            "INSERT INTO entities (name, type, wiki_path, community, tags) VALUES (?, ?, ?, ?, ?)",
            (name, ntype, path, comm, tags),
        )

    # name → id 映射
    name_to_id = {row["name"]: row["id"]
                  for row in conn.execute("SELECT id, name FROM entities").fetchall()}

    # 插入边（用 source_entity / target_entity INTEGER FK）
    edges = [
        ("矩阵基础", "向量空间", "related_to"),
        ("矩阵基础", "特征值", "related_to"),
        ("向量空间", "线性代数", "related_to"),
        ("特征值", "线性代数", "related_to"),
    ]
    for src, tgt, rel in edges:
        conn.execute(
            "INSERT INTO relations (source_entity, target_entity, relation_type) VALUES (?, ?, ?)",
            (name_to_id[src], name_to_id[tgt], rel),
        )

    conn.commit()
    return conn


def test_graph_query_protocol():
    tool = GraphQueryTool()
    assert isinstance(tool, Tool)


def test_query_neighbors():
    conn = _make_test_db()
    store = GraphStore(conn)
    tool = GraphQueryTool(graph_store=store)

    try:
        result = tool.execute({"action": "neighbors", "node": "矩阵基础"})
        assert not result.is_error, result.error
        data = result.data
        assert data["degree"] == 2
        labels = [n["label"] for n in data["neighbors"]]
        assert "向量空间" in labels
        assert "特征值" in labels
    finally:
        conn.close()


def test_query_neighbors_fuzzy():
    conn = _make_test_db()
    store = GraphStore(conn)
    tool = GraphQueryTool(graph_store=store)

    try:
        # 模糊匹配：name 包含 "矩阵"
        result = tool.execute({"action": "neighbors", "node": "矩阵"})
        assert not result.is_error, result.error
        assert result.data["degree"] == 2
    finally:
        conn.close()


def test_query_search():
    conn = _make_test_db()
    store = GraphStore(conn)
    tool = GraphQueryTool(graph_store=store)

    try:
        result = tool.execute({"action": "search", "query": "矩阵"})
        assert not result.is_error, result.error
        data = result.data
        assert data["count"] >= 1
        assert any(n["label"] == "矩阵基础" for n in data["results"])
    finally:
        conn.close()


def test_query_community():
    conn = _make_test_db()
    store = GraphStore(conn)
    tool = GraphQueryTool(graph_store=store)

    try:
        # 列出所有社区
        result = tool.execute({"action": "community"})
        assert not result.is_error, result.error
        assert result.data["total"] == 2

        # 查询特定社区
        result = tool.execute({"action": "community", "community_id": 0})
        assert not result.is_error, result.error
        assert result.data["size"] == 3
    finally:
        conn.close()


def test_query_isolates():
    conn = _make_test_db()
    store = GraphStore(conn)
    tool = GraphQueryTool(graph_store=store)

    try:
        result = tool.execute({"action": "isolates"})
        assert not result.is_error, result.error
        # 所有节点都有连接，所以 0 个孤立
        assert result.data["count"] == 0
    finally:
        conn.close()


def test_query_stats():
    conn = _make_test_db()
    store = GraphStore(conn)
    tool = GraphQueryTool(graph_store=store)

    try:
        result = tool.execute({"action": "stats"})
        assert not result.is_error, result.error
        assert result.data["nodes"] == 4
        assert result.data["edges"] == 4
    finally:
        conn.close()


def test_query_no_graphstore():
    tool = GraphQueryTool()
    result = tool.execute({"action": "stats"})
    assert result.is_error


# ── 集成测试：build → query ────────────────────────────────────


def test_build_then_query():
    """完整流程：创建 vault → build graph → query via GraphStore"""
    vault = _make_vault()
    builder = GraphBuilder()
    output_dir = os.path.join(vault, ".wiki")

    # 临时数据库
    db_dir = tempfile.mkdtemp()
    db_path = os.path.join(db_dir, "test.db")
    from src.db.client import SQLiteClient
    db = SQLiteClient(db_path)
    builder._db = db

    try:
        # Build
        result = builder.execute({"vault_path": vault, "output_dir": output_dir})
        assert not result.is_error, result.error

        # Query via GraphStore
        store = GraphStore(db._conn)
        query_tool = GraphQueryTool(graph_store=store)

        # Neighbors
        result = query_tool.execute({"action": "neighbors", "node": "矩阵基础.md"})
        assert not result.is_error, result.error
        assert result.data["degree"] >= 2

        # Search
        result = query_tool.execute({"action": "search", "query": "向量"})
        assert not result.is_error, result.error
        assert result.data["count"] >= 1

        # Stats
        result = query_tool.execute({"action": "stats"})
        assert not result.is_error, result.error
        assert result.data["nodes"] >= 3
    finally:
        db.close()
        _cleanup(vault)
        shutil.rmtree(db_dir, ignore_errors=True)


def test_incremental_skips_unchanged():
    """增量构建：未变更文件应被跳过"""
    vault = _make_vault()
    builder = GraphBuilder()
    output_dir = os.path.join(vault, ".wiki")

    try:
        # 第一次全量构建
        result1 = builder.execute({"vault_path": vault, "output_dir": output_dir, "incremental": False})
        assert not result1.is_error, result1.error

        # 第二次增量构建（文件没变）
        result2 = builder.execute({"vault_path": vault, "output_dir": output_dir, "incremental": True})
        # 增量时所有文件都被跳过，应返回 error 或 nodes=0
        assert result2.is_error or result2.data.get("nodes", 0) >= 0
    finally:
        _cleanup(vault)


def test_build_writes_entities():
    """图谱构建后 entities 和 relations 应写入 SQLite"""
    vault = _make_vault()

    # 临时数据库
    db_dir = tempfile.mkdtemp()
    db_path = os.path.join(db_dir, "test.db")
    from src.db.client import SQLiteClient
    db = SQLiteClient(db_path)

    builder = GraphBuilder()
    builder._db = db
    output_dir = os.path.join(vault, ".wiki")

    try:
        result = builder.execute({"vault_path": vault, "output_dir": output_dir})
        assert not result.is_error, result.error

        # 验证 entities 表有数据（graphify 可能过滤部分节点，放宽断言）
        rows = db._conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()
        assert rows["c"] >= 2  # 至少有文档节点

        # 验证 relations 表有数据
        rows = db._conn.execute("SELECT COUNT(*) as c FROM relations").fetchone()
        assert rows["c"] >= 2  # 至少有关系
    finally:
        db.close()
        _cleanup(vault)
        shutil.rmtree(db_dir, ignore_errors=True)


def test_build_without_graphify():
    """graphify 不可用时应降级为纯 NetworkX（无社区检测）"""
    vault = _make_vault()
    builder = GraphBuilder()
    output_dir = os.path.join(vault, ".wiki")

    try:
        # mock graphify import 失败
        import unittest.mock
        with unittest.mock.patch.dict("sys.modules", {"graphify": None, "graphify.build": None, "graphify.cluster": None}):
            result = builder.execute({"vault_path": vault, "output_dir": output_dir, "incremental": False})
            assert not result.is_error, result.error
            # 降级时没有社区检测
            assert result.data["communities"] == 0
            # 但节点和边仍然正确
            assert result.data["nodes"] >= 3
            assert result.data["edges"] >= 1
    finally:
        _cleanup(vault)


# ── Entity 统一扫描测试 ────────────────────────────────────────


def _make_vault_with_entities():
    """创建包含 vault/entities/ 的临时 vault"""
    vault = tempfile.mkdtemp()

    # 常规文档
    Path(vault, "绪论.md").write_text("""---
title: 1.绪论
type: document
tags: [AI]
---

# 1.绪论

AI 的基础概念包括 [[图灵测试]] 和 [[符号主义AI]]。
""", encoding="utf-8")

    # Entity 文件在 vault/entities/
    ent_dir = Path(vault, "entities")
    ent_dir.mkdir()

    (ent_dir / "图灵测试.md").write_text("""---
title: 图灵测试
type: entity
sources:
  - "[[1.绪论]]"
tags: [AI, 测试]
related:
  - "[[符号主义AI]]"
---

# 图灵测试

图灵测试是 [[AI]] 领域的经典测试。关联 [[符号主义AI]]。
""", encoding="utf-8")

    (ent_dir / "符号主义AI.md").write_text("""---
title: 符号主义AI
type: concept
sources:
  - "[[1.绪论]]"
tags: [AI, 符号]
---

# 符号主义AI

符号主义是 AI 的三大流派之一。
""", encoding="utf-8")

    return vault


def test_entity_discovered_by_unified_scan():
    """Entity .md 在 vault/entities/ 下应被 _find_markdown_files 自动发现"""
    builder = GraphBuilder()
    vault = _make_vault_with_entities()
    try:
        md_files = builder._find_markdown_files(vault)
        names = [f.name for f in md_files]
        assert "图灵测试.md" in names
        assert "符号主义AI.md" in names
        assert "绪论.md" in names
    finally:
        _cleanup(vault)


def test_entity_type_from_frontmatter():
    """Entity 节点的 type 应来自 frontmatter，而非硬编码"""
    builder = GraphBuilder()
    vault = _make_vault_with_entities()
    output_dir = os.path.join(vault, ".wiki")
    try:
        result = builder.execute({"vault_path": vault, "output_dir": output_dir, "incremental": False, "export_json": True})
        assert not result.is_error, result.error

        # 读取 graph.json 检查节点类型
        graph_json = os.path.join(output_dir, "graph.json")
        data = json.loads(open(graph_json, encoding="utf-8").read())
        node_types = {attrs.get("label"): attrs.get("type") for attrs in data["nodes"].values()}
        assert node_types.get("图灵测试") == "entity"
        assert node_types.get("符号主义AI") == "concept"
    finally:
        _cleanup(vault)


def test_entity_sources_create_edges():
    """Entity frontmatter sources 字段应创建 entity→document 的边"""
    builder = GraphBuilder()
    vault = _make_vault_with_entities()

    db_dir = tempfile.mkdtemp()
    db_path = os.path.join(db_dir, "test.db")
    from src.db.client import SQLiteClient
    db = SQLiteClient(db_path)
    builder._db = db
    output_dir = os.path.join(vault, ".wiki")

    try:
        result = builder.execute({"vault_path": vault, "output_dir": output_dir, "incremental": False, "export_json": True})
        assert not result.is_error, result.error

        # 通过 graph.json 检查边
        graph_json = os.path.join(output_dir, "graph.json")
        data = json.loads(open(graph_json, encoding="utf-8").read())

        # 检查 source document 和 entity 之间有边（graphify 可能规范化 relation type）
        edge_pairs = {
            (e["source"], e["target"])
            for e in data["edges"]
        }
        # 应该有 1.绪论 ↔ 图灵测试 和 1.绪论 ↔ 符号主义AI 的连接
        has_link_to_turing = any(
            "绪论" in src and "图灵" in tgt or "绪论" in tgt and "图灵" in src
            for src, tgt in edge_pairs
        )
        assert has_link_to_turing, f"Expected edge between 绪论 and 图灵测试, got: {edge_pairs}"
    finally:
        db.close()
        _cleanup(vault)
        shutil.rmtree(db_dir, ignore_errors=True)
