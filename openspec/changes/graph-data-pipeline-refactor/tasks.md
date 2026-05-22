## 1. 数据库 Schema 扩展

- [x] 1.1 entities 表新增列：community INTEGER DEFAULT -1, tags TEXT DEFAULT '', entity_file TEXT DEFAULT '', source_file TEXT DEFAULT '', level TEXT DEFAULT '', content_hash TEXT DEFAULT ''
- [x] 1.2 验证 ALTER TABLE 对已有 DB 的兼容性（新列有默认值，无破坏性变更）

## 2. GraphStore 共享查询层

- [x] 2.1 新建 `src/db/graph_store.py`，实现 GraphStore 类（接收 SQLite 连接）
- [x] 2.2 实现 `get_full_graph()` → SQL 查询所有 entities + relations
- [x] 2.3 实现 `get_neighbors(node_id)` → SQL 查询出边 + 入边邻居
- [x] 2.4 实现 `bfs_subgraph(entity, depth)` → SQLite 递归 CTE（depth 上限 4）
- [x] 2.5 实现 `search_nodes(query)` → LIKE 模糊匹配 name 字段
- [x] 2.6 实现 `get_stats()` → COUNT 查询 nodes/edges/communities/isolates
- [x] 2.7 实现 `get_node_by_name(name)` → 精确 + 模糊节点查找
- [x] 2.8 编写 GraphStore 单元测试

## 3. GraphBuilder 构建目标迁移

- [x] 3.1 扩展 `_write_to_sqlite()` 写入全部新字段（community, tags, entity_file, source_file, level, content_hash）
- [x] 3.2 社区检测结果写入 entities.community 列（替代仅存 graph.json）
- [x] 3.3 `_write_json()` 改为可选（参数 `export_json=False` 默认不导出）
- [x] 3.4 修复 graphify file_type 警告：节点创建时补 `file_type` 字段

## 4. 后端路由层迁移

- [x] 4.1 `graph.py` 的 `/graph/full` 改为调 GraphStore.get_full_graph()，转 force-graph 格式
- [x] 4.2 `graph.py` 的 `/graph/subgraph` 改为调 GraphStore.bfs_subgraph()
- [x] 4.3 `graph.py` 的 `/graph/neighbors/{node}` 改为调 GraphStore.get_neighbors()
- [x] 4.4 `graph.py` 的 `/graph/stats` 改为调 GraphStore.get_stats()
- [x] 4.5 `graph.py` 的 `/graph/build` 构建后返回值改为从 DB 读取（不再依赖 graph.json）
- [x] 4.6 `graph.py` 的 `/graph/data`（旧格式兼容）改为从 DB 读取

## 5. Agent Tool 层迁移

- [x] 5.1 `graph_query.py` 的 `execute()` 改为接收 GraphStore 实例
- [x] 5.2 所有 action（neighbors, search, community, isolates, stats, path, explore）改为调 GraphStore
- [x] 5.3 移除 NetworkX 图构建和 mtime 文件缓存逻辑
- [x] 5.4 `bootstrap.py` 中注册 graph_query tool 时注入 GraphStore

## 6. 前端数据隔离修复

- [x] 6.1 `GraphContainer.svelte` 的 `loadGraph()` 改为通过 ApiClient.getFullGraph()
- [x] 6.2 `GraphContainer.svelte` 的 `buildGraph()` 改为通过 ApiClient.buildGraph()
- [x] 6.3 GraphContainer 接收 plugin 实例后构建 ApiClient（复用 settings）
- [x] 6.4 `client.ts` 的 `deleteSession()` 改用 `fetchJSON` 补 auth headers
- [x] 6.5 验证所有图谱和 chat 接口的 X-Vault-Path header 正确传递

## 7. 集成验证

- [ ] 7.1 新 vault 构建 → 验证 SQLite 写入正确（entities/relations 含全字段）
- [ ] 7.2 前端图谱展示 → 验证节点点击预览正常
- [ ] 7.3 Chat agent graph_query tool → 验证查询结果正确
- [ ] 7.4 双 vault 并发 → 验证数据隔离（不同 vault 读到不同数据）
- [ ] 7.5 无 X-Vault-Path header 时 → 验证 fallback 到 .env 默认 vault
