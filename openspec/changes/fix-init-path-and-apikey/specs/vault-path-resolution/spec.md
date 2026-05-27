## ADDED Requirements

### Requirement: Unified vault detection
系统 SHALL 使用唯一的 `detect_vault()` 函数进行 vault 路径检测，所有模块（config、scripts）MUST 复用同一实现。

#### Scenario: 环境变量指定 vault
- **WHEN** 环境变量 `LLM_WIKI_VAULT` 设置为有效路径 `/data/my-vault`
- **THEN** `detect_vault()` 返回 `/data/my-vault`

#### Scenario: CWD 自动检测 vault
- **WHEN** `LLM_WIKI_VAULT` 未设置，且当前工作目录包含 `.obsidian/`
- **THEN** `detect_vault()` 返回当前工作目录

#### Scenario: 父目录自动检测 vault
- **WHEN** `LLM_WIKI_VAULT` 未设置，且 CWD 是 vault 的子目录（如 `/data/my-vault/notes/`）
- **THEN** `detect_vault()` 向上查找并返回 `/data/my-vault`

#### Scenario: 无 vault 时的 fallback
- **WHEN** `LLM_WIKI_VAULT` 未设置，且 CWD 及其父目录均不包含 `.obsidian/`
- **THEN** `detect_vault()` 返回 CWD 并记录 warning 日志

### Requirement: Scripts 模块复用 config 的 vault 检测
`src/scripts/__init__.py` MUST 移除独立的 `_detect_vault()` 函数，改为调用 `src/config.py` 中的 `detect_vault()`。

#### Scenario: Scripts 模块使用统一检测
- **WHEN** `entity_builder.py` 或其他 scripts 模块需要 vault 路径
- **THEN** 使用 `config.detect_vault()` 获取路径，结果与环境变量和 config 模块一致

### Requirement: `.env.example` 修正
`.env.example` SHALL 展示正确的环境变量名 `LLM_WIKI_VAULT`，并注明路径解析优先级。

#### Scenario: 用户按 `.env.example` 配置
- **WHEN** 用户复制 `.env.example` 为 `.env` 并填写 `LLM_WIKI_VAULT=/path/to/vault`
- **THEN** 后端启动时正确使用该路径作为 vault 路径
