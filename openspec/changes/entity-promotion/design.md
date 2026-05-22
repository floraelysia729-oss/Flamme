## Context

Flamme 的 entity（知识词条）当前存储在 `.flamme/entities/` 隐藏目录中。这是 PDF ingest 流程的产物 — entity 由 `entity_builder.py`（三阶段流水线：jieba + LLM + 验证）和 `wiki_entity.py`（JSON 模板生成）写入。

`.flamme/` 目录包含四类内容：
- `converted/` — PDF→MD 转换中间产物
- `ocr/` — OCR 输出
- `entities/` — 知识词条（应有用户可见）
- `topics/` — 主题页（应有用户可见）

当前 `entities/` 和 `topics/` 被当作中间产物处理，但它们实际是面向用户的知识内容。

## Goals / Non-Goals

**Goals:**
- Entity .md 文件放在 `vault/entities/` 目录下，Obsidian 原生索引可搜索
- Chat 中 `[[实体名]]` 点击直接打开有内容的 note
- 图谱构建统一走 `_find_markdown_files()`，无需特殊 entity 扫描
- 已有 vault 提供平滑迁移

**Non-Goals:**
- 不改 entity 内容格式（frontmatter 结构不变）
- 不改 entity_builder 的 LLM 提取逻辑
- 不处理 topics/ 迁移（topics 可后续单独处理）
- 不改 `.flamme/converted/` 和 `.flamme/ocr/` 的位置（这些是真正的中间产物）

## Decisions

### D1: Entity 输出目录 → `vault/entities/`

**选择**: 扁平放在 vault 根目录的 `entities/` 文件夹。

**理由**: 与 Obsidian 文件浏览器自然对齐，用户可以直接在文件树中看到所有 entity。不污染源文件目录结构。

**备选**:
- `vault/.flamme/entities/`（现状）— 隐藏，不可搜索
- `vault/知识库/entities/`（中文目录名）— 跨平台兼容性差
- per-source-dir（`人工智能导论/entities/`）— entity 跨文件引用时归属不明

### D2: GraphBuilder 统一扫描

移除 `_find_entity_files()` 和 `_extract_entities()`。Entity 作为普通 `.md` 文件被 `_find_markdown_files()` 扫描。

**影响**:
- Entity 节点的 `type` 从 frontmatter 的 `type: concept` 或 `type: entity` 读取，不再是硬编码 `"entity"`
- `entity_file` 字段不再需要（entity 就是 `source_file` 本身）
- 需要在 `_find_markdown_files` 的 `SKIP_DIRS` 中排除 `entities`（避免把 `entities/` 当作源目录扫描两次），或者让它自然扫入

**选择**: 让 `_find_markdown_files()` 自然扫描 `entities/` 目录。Entity .md 的 frontmatter 有 `type: concept`/`type: entity`，`_extract_all()` 已按 frontmatter 读取 type 字段。

### D3: paths.py 更新

`entities_dir()` 返回 `vault_path / "entities"` 而非 `source_dir / ".flamme" / "entities"`。

**影响**: `entity_builder.py` 和 `wiki_entity.py` 调用 `entities_dir()` 获取写入路径，改动收敛到一个函数。

### D4: source_dir_for_path 调整

当前 `source_dir_for_path()` 通过剥离 `.flamme` 组件定位源目录。Entity 搬出后，路径从 `.flamme/entities/X.md` 变为 `entities/X.md`，不再包含源目录信息。

**选择**: Entity frontmatter 的 `sources` 字段已包含源文档引用。`_source_dir_for_entity()` 逻辑简化 — 直接从 `sources` frontmatter 字段获取源文件路径，不再依赖目录结构推断。

### D5: 迁移策略

提供一次性迁移脚本 `migrate_entities.py`:
1. 扫描 vault 所有 `.flamme/entities/` 目录
2. 将 `.md` 文件移至 `vault/entities/`
3. 同名文件合并（取更新时间更近的）
4. 删除空的 `.flamme/entities/` 目录

## Risks / Trade-offs

- **[vault 根目录污染]** → `entities/` 作为单一子目录，Obsidian 支持折叠，影响可控。用户也可在 settings 中配置目录名
- **[大量 entity 时性能]** → Obsidian 对数千文件 vault 表现良好，不构成问题
- **[迁移中断]** → 迁移脚本先复制再删除，支持 dry-run 模式
- **[entity 重名冲突]** → 不同 `.flamme/entities/` 下可能有同名 entity；取最新版本，日志记录冲突
