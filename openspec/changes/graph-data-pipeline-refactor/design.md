## Context

当前图谱系统的数据流：

- **构建**：`GraphBuilder` 扫描 vault .md → 提取 wikilink/entity → 构建 NetworkX 图 → 双写 `graph.json`（静态文件）和 SQLite（entities/relations 表）
- **查询（前端）**：`graph.py` 路由每次请求 `json.loads()` 整个 graph.json，纯 dict 遍历做 BFS
- **查询（Agent）**：`graph_query.py` Tool 读取同一个 graph.json → 构建 NetworkX DiGraph → mtime 缓存 → 查询
- **前端请求**：`GraphContainer.svelte` 裸 fetch 不带 `X-Vault-Path`，后端 fallback 到 `.env` 默认 vault

关键约束：
- 已有 `config_from_headers()` + `buildAuthHeaders()` 机制，chat 路由已验证可用
- SQLite schema 已有 entities（id, name, type, wiki_path）和 relations（source_entity, target_entity, relation_type, confidence, source_doc）
- `graph_builder._write_to_sqlite()` 已在写 DB，只是查询侧没接

## Goals / Non-Goals

**Goals:**
- 多 vault 数据隔离：所有图谱和 chat 接口通过 `X-Vault-Path` header 正确路由到对应 vault 的 `.wiki/` 数据
- SQLite 成为图谱查询的唯一数据源，消除 graph.json 双读
- 统一图查询引擎，消除 `graph.py` 和 `graph_query.py` 的重复逻辑
- graph.json 降级为可选导出格式

**Non-Goals:**
- 不重做 entity 提取/构建的 LLM 管道（`entity_extract.py`, `entity_builder.py`, `wiki_entity.py`）
- 不改社区检测算法（继续用 graphify Leiden 或 NetworkX 降级）
- 不改 chat/agent 编排架构
- 不做图谱增量更新（仍是全量重建，但目标改为 SQLite）

## Decisions

### Decision 1: 共享查询模块位置 — `src/db/graph_store.py`

**选择**：新增 `src/db/graph_store.py`（GraphStore 类），封装所有图谱 SQL 查询。

**理由**：
- `SQLiteClient` 已有 entities/relations 的写入方法，补查询方法自然归属同一层
- 但 `SQLiteClient` 已 554 行，再塞图谱查询会膨胀
- 独立类更清晰：`GraphStore` 接收 `SQLiteClient` 连接，专注图谱读操作

**备选**：
- 方案 B：直接在 `SQLiteClient` 加方法 → 类过大，职责混杂
- 方案 C：独立 `src/tools/graph_query_shared.py` → 不属于 tools 层，语义不对

### Decision 2: entities 表扩展字段

新增列（`ALTER TABLE` + 新 schema 默认值）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| community | INTEGER | -1 | Leiden 社区 ID |
| tags | TEXT | '' | 逗号分隔标签 |
| entity_file | TEXT | '' | entity markdown 相对路径 |
| source_file | TEXT | '' | 源文档相对路径（与 wiki_path 合并） |
| level | TEXT | '' | pro/lite/raw |
| content_hash | TEXT | '' | 内容 hash（增量构建用） |

**理由**：这些字段当前只存在 graph.json 中，要迁移到 SQLite 必须有对应的列。

### Decision 3: graph_builder 构建流程调整

当前：`vault .md → NetworkX → graph.json + SQLite`

改为：`vault .md → NetworkX → SQLite（主写） → graph.json（可选导出）`

- `_write_to_sqlite()` 扩展为写入全部字段（含新增列）
- `_write_json()` 保留但改为可选，仅在参数指定时导出
- 社区检测结果写入 entities.community 列

### Decision 4: graph.py 路由层改为调 GraphStore

- `/graph/full` → `GraphStore.get_all_nodes()` + `get_all_edges()` → 转 force-graph 格式
- `/graph/subgraph` → `GraphStore.bfs_neighbors(entity, depth)`
- `/graph/neighbors/{node}` → `GraphStore.get_neighbors(node)`
- `/graph/stats` → `GraphStore.get_stats()`
- `/graph/build` → 仍调 `GraphBuilder`（写 SQLite），返回值改为从 DB 读

### Decision 5: graph_query.py Tool 层改为调 GraphStore

- `execute()` 改为接收 `GraphStore` 实例
- 所有 action（neighbors, search, community, isolates, stats, path, explore）改为 SQL 查询
- NetworkX 依赖仅保留给 graph_builder 的构建阶段
- mtime 文件缓存替换为内存缓存（dict + TTL 或简单标记）

### Decision 6: 前端 GraphContainer 改用 ApiClient

- `loadGraph()` → `this.apiClient.getFullGraph()`
- `buildGraph()` → `this.apiClient.buildGraph()`
- ApiClient 已封装 `buildAuthHeaders()`，自带 `X-Vault-Path`
- `deleteSession()` 同理改用 `fetchJSON`

## Risks / Trade-offs

**[风险] SQLite 递归 CTE 性能** → 对于当前规模（<1000 节点）完全够用。如果未来图谱达到 10 万级，考虑在 GraphStore 层加内存缓存。

**[风险] 迁移期间 graph.json 和 SQLite 不一致** → 部署顺序：先改 schema + builder（写两端），再切查询层（读 DB）。过渡期两份数据都写入，查询切到 DB 后 graph.json 变为只导出。

**[风险] graphify 库的 file_type 警告** → 在 `_extract_all()` 创建节点时补 `file_type` 字段（= `type` 的别名），简单映射即可消除。

**[权衡] 放弃 NetworkX 的图算法能力** → BFS 和邻居查询用 SQL 实现无压力。最短路径用递归 CTE。社区检测仍在构建时用 graphify/NetworkX 算好存 DB，查询时只读结果。真正需要复杂图算法时再引入。
