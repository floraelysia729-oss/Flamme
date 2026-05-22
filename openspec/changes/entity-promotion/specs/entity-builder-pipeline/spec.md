## ADDED Requirements

### Requirement: entity_builder writes to vault/entities/
`entity_builder.py` 的 `build_from_file()` SHALL 将生成的 entity .md 文件写入 `<vault_path>/entities/<safe_filename>.md`。

#### Scenario: Entity created for pro-level PDF
- **WHEN** IngestWorker 处理一个 pro-level PDF 并触发 entity 构建
- **THEN** 生成的 entity 文件 SHALL 写入 `vault/entities/` 目录

#### Scenario: entities/ directory auto-created
- **WHEN** entity_builder 写入文件时 `vault/entities/` 目录不存在
- **THEN** 目录 SHALL 自动创建

### Requirement: wiki_entity writes to vault/entities/
`wiki_entity.py` SHALL 将生成的 entity 页面写入 `<vault_path>/entities/<title>.md`。

#### Scenario: Generate entity page from JSON
- **WHEN** wiki_entity 从 JSON 数据生成 entity 页面
- **THEN** 输出路径 SHALL 为 `vault/entities/<title>.md`

### Requirement: paths.py entities_dir() returns vault/entities/
`entities_dir()` SHALL 返回 `<vault_path>/entities/`，不再返回 `<source_dir>/.flamme/entities/`。

#### Scenario: entities_dir called from entity_builder
- **WHEN** entity_builder 调用 `entities_dir(source_dir)` 获取写入路径
- **THEN** 返回值 SHALL 为 `vault_path/entities/`（忽略 source_dir 参数，统一写入 vault 级目录）

### Requirement: Entity frontmatter sources field preserved
Entity .md 文件的 frontmatter `sources` 字段 SHALL 保持不变，用于溯源到原始 PDF/文档。

#### Scenario: Entity references source PDF
- **WHEN** entity 的 sources 字段包含 `"1.绪论"`
- **THEN** 该引用 SHALL 在图谱中创建 entity → document 的边关系
