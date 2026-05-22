## ADDED Requirements

### Requirement: Entity files stored in vault root entities/ directory
Entity .md 文件 SHALL 存储在 `vault/entities/` 目录下（vault 根目录的直接子目录），而非 `.flamme/entities/`。

#### Scenario: New entity created during ingest
- **WHEN** entity_builder 为一个概念创建新的 entity 文件
- **THEN** 文件 SHALL 写入 `<vault_path>/entities/<entity_name>.md`

#### Scenario: Entity file is a regular Obsidian note
- **WHEN** 用户在 Obsidian 文件浏览器中查看 vault
- **THEN** `entities/` 目录 SHALL 可见，其中所有 .md 文件 SHALL 可被 Obsidian 索引和搜索

### Requirement: Chat wikilink resolves to entity note
Chat 中的 `[[实体名]]` 链接 SHALL 直接打开 `vault/entities/` 中对应的 entity note。

#### Scenario: Click entity wikilink in chat
- **WHEN** 用户点击聊天消息中的 `[[图灵测试]]` 链接
- **THEN** Obsidian SHALL 打开 `entities/图灵测试.md` 并显示其完整内容（摘要、要点、关联概念）

#### Scenario: Entity note not found
- **WHEN** 用户点击的 wikilink 没有对应的 entity 文件
- **THEN** Obsidian 的默认行为 SHALL 正常生效（提示创建新 note）

### Requirement: Graph preview shows entity content
图谱节点点击预览 SHALL 能正确渲染 entity note 内容。

#### Scenario: Click entity node in graph
- **WHEN** 用户在图谱中点击一个 entity 类型的节点
- **THEN** 右侧预览面板 SHALL 使用 Obsidian MarkdownRenderer 渲染 entity 的完整 .md 内容

### Requirement: Migration from .flamme/entities/ to vault/entities/
系统 SHALL 提供迁移工具将已有 `.flamme/entities/` 下的 entity 文件移至 `vault/entities/`。

#### Scenario: Migrate existing vault
- **WHEN** 运行迁移脚本并指定 vault 路径
- **THEN** 脚本 SHALL 将所有 `.flamme/entities/*.md` 文件复制到 `vault/entities/`，处理同名冲突（取较新版本），并记录操作日志

#### Scenario: Dry run migration
- **WHEN** 运行迁移脚本带 `--dry-run` 参数
- **THEN** 脚本 SHALL 仅输出将要执行的操作而不实际移动文件
