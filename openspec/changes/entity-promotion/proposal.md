## Why

Entity 知识词条被生成在隐藏的 `.flamme/entities/` 目录中，导致三个问题叠加：
1. **图谱构建跳过** — `_find_markdown_files()` 跳过 `.flamme`，纯 PDF vault 没有普通 .md 文件时图谱为空
2. **Chat 点击空白** — `[[图灵测试]]` 在聊天中点击时 Obsidian 找不到文件，创建空白 note
3. **预览失效** — GraphContainer 的 entity_file 路径指向隐藏目录，渲染异常

Entity 本质是知识词条，应作为一等公民 note 存在于 vault 中。

## What Changes

- **BREAKING**: Entity 输出目录从 `.flamme/entities/` 改为 `vault/entities/`（vault 根目录下的 `entities/` 文件夹）
- `entity_builder.py` 和 `wiki_entity.py` 写入路径改为 `vault/entities/`
- `paths.py` 的 `entities_dir()` 指向新位置
- `graph_builder.py` 去掉 `_find_entity_files()` 特殊处理，entity 作为普通 .md 被 `_find_markdown_files()` 发现
- GraphContainer 预览路径简化（不再需要 `entity_file` 字段的特殊处理）
- 提供迁移脚本将已有 `.flamme/entities/*.md` 移至 `vault/entities/`

## Capabilities

### New Capabilities
- `entity-storage`: Entity 一等公民存储 — entity 作为 vault 根目录 `entities/` 下的普通 note，Obsidian 原生索引可搜索可跳转

### Modified Capabilities
- `graph-build`: 图谱构建不再需要 `_find_entity_files()` 特殊路径扫描，entity 随普通 .md 文件一起被扫描
- `entity-builder-pipeline`: `entity_builder.py` 和 `wiki_entity.py` 写入路径从 `.flamme/entities/` 改为 `vault/entities/`

## Impact

- **写入层**: `src/scripts/entity_builder.py`, `src/scripts/wiki_entity.py` — 输出路径变更
- **路径工具**: `src/tools/paths.py` — `entities_dir()` 指向新位置
- **图谱构建**: `src/tools/graph_builder.py` — 移除 `_find_entity_files()` 和 `_extract_entities()` 的特殊处理
- **前端**: `GraphContainer.svelte` — 预览路径逻辑简化
- **DB schema**: `entities` 表的 `entity_file` 字段值路径变更（从 `.flamme/entities/X.md` → `entities/X.md`）
- **向后兼容**: 已有 vault 需迁移，`.flamme/entities/` 下的旧文件需移至 `entities/`
