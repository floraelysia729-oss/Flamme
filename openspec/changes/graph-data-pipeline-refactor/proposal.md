## Why

图谱系统存在两类严重缺陷：

1. **多 vault 数据隔离失效**：前端 GraphContainer 的全部 6 个图谱接口裸 fetch 不带 `X-Vault-Path` header，两个 Obsidian vault 共用后端时所有图谱请求 fallback 到 `.env` 默认 vault，导致读错数据、构建写入错误目录。`ApiClient` 已封装 `buildAuthHeaders()` 但 GraphContainer 未使用。
2. **数据流设计不合理**：`graph.json` 静态文件是所有图谱查询的唯一数据源，`graph_builder` 同时双写 SQLite 和 graph.json 但 SQLite 的 entities/relations 无人读取。`graph.py`（API 路由）和 `graph_query.py`（Agent Tool）各自独立实现了一套图查询引擎（BFS、节点匹配、邻居查询），逻辑高度重复。每次 `/graph/full` 请求全量 `json.loads` 无缓存。

## What Changes

- **修复前端数据隔离**：GraphContainer 改用 `ApiClient`（已有 `buildAuthHeaders` 封装），`deleteSession` 补 auth headers
- **SQLite 成为图谱唯一 source of truth**：entities 表补充缺失字段（community, tags, entity_file, source_file, level, content_hash），graph_builder 构建目标改为 SQLite
- **统一图查询层**：新增共享查询模块，`graph.py` 路由和 `graph_query.py` Tool 共用一套从 SQLite 读取的查询逻辑，消除两套 BFS / 节点匹配 / 邻居查询的重复实现
- **graph.json 降级为可选导出**：仍可导出供外部工具使用，但不再是查询数据源
- **修复 graphify file_type 警告**：节点创建时补 `file_type` 字段

## Capabilities

### New Capabilities
- `sqlite-graph-query`: 统一的 SQLite 图谱查询层，供 API 路由和 Agent Tool 共用，支持邻居查询、BFS 子图、搜索、路径、统计。替代当前 graph.json 双读 + 双引擎的架构。

### Modified Capabilities

（无已有 specs 需要修改。`vault-path-resolution` 和 `per-request-config` 属于 change `fix-init-path-and-apikey` 的范畴，此处不修改其 spec 级需求，仅确保图谱路由走已有的 per-request config 路径。）

## Impact

- **后端核心**：`src/api/routes/graph.py`（查询逻辑改为调共享层）、`src/tools/graph_query.py`（改为调共享层）、`src/tools/graph_builder.py`（构建目标改为 SQLite 优先）
- **数据库**：`src/db/schema.sql`（entities 表加列）、`src/db/client.py`（补充图查询方法）
- **插件前端**：`plugin/src/svelte/graph/GraphContainer.svelte`（改用 ApiClient）、`plugin/src/api/client.ts`（补 deleteSession header）
- **向后兼容**：graph.json 仍可通过 `/graph/export` 或构建时导出，但不作为热路径查询数据源
