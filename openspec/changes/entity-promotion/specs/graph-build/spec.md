## ADDED Requirements

### Requirement: GraphBuilder discovers entity files via regular .md scan
GraphBuilder SHALL 通过 `_find_markdown_files()` 统一扫描发现 entity .md 文件，不再需要专用的 `_find_entity_files()` 方法。

#### Scenario: Entity files in vault/entities/ discovered
- **WHEN** GraphBuilder 扫描包含 `entities/` 目录的 vault
- **THEN** `entities/*.md` 文件 SHALL 被包含在扫描结果中，与其他 .md 文件统一处理

#### Scenario: Entity node type from frontmatter
- **WHEN** GraphBuilder 处理一个 frontmatter 含 `type: concept` 的 entity .md 文件
- **THEN** 生成的图谱节点 `type` SHALL 为 frontmatter 中的 `type` 值（concept/entity），而非硬编码

### Requirement: Entity node source_file points to vault/entities/ path
Entity 节点的 `source_file` SHALL 指向 `entities/X.md`（vault 相对路径），不再需要单独的 `entity_file` 字段。

#### Scenario: Entity node source_file in graph data
- **WHEN** 图谱构建完成，查询某个 entity 节点
- **THEN** `source_file` SHALL 为 `entities/图灵测试.md` 格式的 vault 相对路径

#### Scenario: Frontend preview uses source_file directly
- **WHEN** GraphContainer 预览 entity 节点
- **THEN** SHALL 使用 `source_file` 路径（`entities/X.md`）通过 `app.vault.getAbstractFileByPath()` 打开文件

### Requirement: No special entity extraction pass
GraphBuilder SHALL 移除 `_find_entity_files()` 和 `_extract_entities()` 方法。Entity 的 wikilink、related、tags 全部通过标准的 `_extract_all()` 流程处理。

#### Scenario: Entity wikilinks create graph edges
- **WHEN** entity .md 文件正文包含 `[[符号主义AI]]`
- **THEN** GraphBuilder SHALL 通过标准 wikilink 提取创建从该 entity 到目标 entity 的边
