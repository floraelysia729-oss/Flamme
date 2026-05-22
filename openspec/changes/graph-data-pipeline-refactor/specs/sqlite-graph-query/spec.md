## ADDED Requirements

### Requirement: GraphStore 统一查询接口

系统 SHALL 提供 `GraphStore` 类，封装所有图谱 SQL 查询操作，供 API 路由和 Agent Tool 共用。`GraphStore` 接收 SQLite 连接，从 entities 和 relations 表读取数据。

#### Scenario: 查询全图节点和边
- **WHEN** 调用 `GraphStore.get_full_graph()`
- **THEN** 返回所有 entities（含 community, tags, entity_file, source_file, level）和所有 relations（含 relation_type, confidence, source_doc）

#### Scenario: 空图谱
- **WHEN** entities 表为空
- **THEN** 返回空列表，不抛异常

### Requirement: BFS 子图查询

系统 SHALL 支持从指定节点出发的 BFS 遍历，使用 SQLite 递归 CTE 实现。

#### Scenario: 查询 1 跳邻居
- **WHEN** 调用 `GraphStore.bfs_subgraph(entity="无信息搜索", depth=1)`
- **THEN** 返回 "无信息搜索" 及其直接邻居节点和连接边

#### Scenario: 节点不存在
- **WHEN** 指定 entity 在 entities 表中不存在
- **THEN** 返回空结果

#### Scenario: 深度限制
- **WHEN** depth 参数超过 4
- **THEN** 系统 SHALL 将 depth 截断为 4

### Requirement: 邻居查询

系统 SHALL 支持查询单个节点的所有邻居（出边 + 入边）。

#### Scenario: 查询有邻居的节点
- **WHEN** 调用 `GraphStore.get_neighbors("BFS")`
- **THEN** 返回所有通过 relations 表连接的邻居节点，包含 relation_type

#### Scenario: 孤立节点
- **WHEN** 节点在 entities 中存在但无任何 relation
- **THEN** 返回空邻居列表，degree=0

### Requirement: 图谱统计

系统 SHALL 返回图谱统计信息。

#### Scenario: 正常统计
- **WHEN** 调用 `GraphStore.get_stats()`
- **THEN** 返回 `{nodes: int, edges: int, communities: int, isolates: int}`

### Requirement: 模糊搜索节点

系统 SHALL 支持按标签模糊搜索节点。

#### Scenario: 搜索匹配
- **WHEN** 调用 `GraphStore.search_nodes("搜索")`
- **THEN** 返回 name 中包含 "搜索" 的所有 entity，按 degree 降序排列

### Requirement: 多 vault 数据隔离

系统 SHALL 通过 per-request Config 中的 `vault_path` 派生 `db_path`，确保不同 vault 的图谱数据存储在各自独立的 `vault/.wiki/knowledge.db` 中。

#### Scenario: Vault A 请求不读到 Vault B 数据
- **WHEN** Vault A 发送请求带 `X-Vault-Path: D:\notebook`，Vault B 发送请求带 `X-Vault-Path: D:\test-vault`
- **THEN** 两个请求分别读写各自 vault 下的 `.wiki/knowledge.db`，互不影响

#### Scenario: 无 X-Vault-Path header 时 fallback
- **WHEN** 请求不包含 `X-Vault-Path` header
- **THEN** 后端使用 `.env` 中 `LLM_WIKI_VAULT` 配置作为默认 vault 路径

### Requirement: 前端图谱请求必须带 vault header

前端插件的所有图谱 API 请求 SHALL 通过 `ApiClient`（`buildAuthHeaders`）发送，携带 `X-Vault-Path` header。

#### Scenario: GraphContainer 请求图谱
- **WHEN** GraphContainer 加载或构建图谱
- **THEN** HTTP 请求包含 `X-Vault-Path` header，值为当前 Obsidian vault 的绝对路径

#### Scenario: Chat 删除会话
- **WHEN** 前端调用 deleteSession
- **THEN** HTTP DELETE 请求包含 `X-Vault-Path` header

### Requirement: graph.json 作为可选导出

`GraphBuilder` 构建完成后 SHALL 优先写入 SQLite。graph.json 仅在显式请求或兼容场景下导出。

#### Scenario: 构建写入 SQLite
- **WHEN** `GraphBuilder.execute()` 完成
- **THEN** entities 和 relations 表包含完整的节点和边数据（含 community, tags, entity_file, source_file, level, content_hash）

#### Scenario: 可选导出 graph.json
- **WHEN** 构建参数指定 `export_json=True`
- **THEN** 额外导出 graph.json 到 `vault/.wiki/graph.json`
