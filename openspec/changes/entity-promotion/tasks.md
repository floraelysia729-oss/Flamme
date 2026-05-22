## 1. 路径层迁移

- [x] 1.1 `paths.py` — `entities_dir()` 改为返回 `vault_path / "entities"`（忽略 source_dir 参数）
- [x] 1.2 `paths.py` — 确认 `all_flamme_dirs()` 和其他路径工具不受影响

## 2. Entity 写入层迁移

- [x] 2.1 `entity_builder.py` — `build_from_file()` 调用 `entities_dir(vault)` 而非 `entities_dir(source_dir)`，写入 `vault/entities/`
- [x] 2.2 `wiki_entity.py` — 输出路径改为 `vault/entities/<title>.md`
- [x] 2.3 验证 entity_builder 对已有 entity 的增量更新逻辑（同名文件 upsert）

## 3. GraphBuilder 统一扫描

- [x] 3.1 `graph_builder.py` — 移除 `_find_entity_files()` 和 `_extract_entities()` 方法
- [x] 3.2 `graph_builder.py` — `execute()` 中移除 entity 相关的 Pass 1/Pass 2/合并逻辑，统一走 `_extract_all()`
- [x] 3.3 `graph_builder.py` — `_extract_all()` 处理 entity frontmatter 的 `sources` 字段创建 entity→document 边
- [x] 3.4 `graph_builder.py` — `_extract_all()` 处理 entity frontmatter 的 `type` 字段作为节点类型
- [x] 3.5 `_to_force_graph_format()` — 移除 `entity_file` 字段的特殊处理，统一用 `source_file`

## 4. 前端适配

- [x] 4.1 `GraphContainer.svelte` — 预览路径简化，移除 `entity_file` 优先级逻辑，统一用 `source_file`
- [x] 4.2 `types.ts` — `GraphNode` 中 `entity_file` 标记为可选/deprecated

## 5. 迁移脚本

- [x] 5.1 创建 `scripts/migrate_entities.py` — 扫描 vault 所有 `.flamme/entities/`，复制 .md 到 `vault/entities/`，处理同名冲突
- [x] 5.2 支持 `--dry-run` 模式，输出迁移计划不执行
- [x] 5.3 迁移后清理空的 `.flamme/entities/` 目录

## 6. 测试更新

- [x] 6.1 更新 `test_graph.py` — 移除 `_extract_entities` 相关测试，改为测试 entity .md 在 `entities/` 目录下的统一扫描
- [x] 6.2 新增测试 — entity frontmatter 的 sources 字段生成 entity→document 边
- [x] 6.3 新增测试 — entity node type 来自 frontmatter 而非硬编码

## 7. 集成验证

- [ ] 7.1 测试 vault（D:\dev\LLM-WIKI\test）迁移后重建图谱 → 验证节点和边正确
- [ ] 7.2 Chat 中点击 `[[图灵测试]]` → 验证打开有内容的 entity note
- [ ] 7.3 图谱界面点击 entity 节点 → 验证预览渲染正常
