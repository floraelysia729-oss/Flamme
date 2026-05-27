## Why

用户在新环境从零搭建后端时，vault 路径解析依赖 CWD 和 `.env` 中硬编码的绝对路径，导致后端找不到正确的 Obsidian vault 目录。同时，Obsidian 插件通过 HTTP header 传递的 MinerU API token 只被 `/api/chat` 路由读取，`/api/ingest` 等路由完全忽略插件传来的 key，导致用户在插件中配置的 API 无法生效。

## What Changes

- **修复路径解析**：消除对 `.env` 硬编码路径和 CWD 的依赖，支持通过插件配置传递 vault 路径，确保新环境开箱即用
- **统一 vault 检测逻辑**：合并 `src/config.py::detect_vault()` 和 `src/scripts/__init__.py::_detect_vault()` 两套独立实现
- **修复 `.env.example`**：将错误的 `FLAMME_VAULT` 示例改为正确的 `LLM_WIKI_VAULT`
- **扩展 header 配置传递**：让 `/api/ingest` 和 `/api/documents` 等路由也读取插件传来的 API key（特别是 MinerU token），不再仅依赖 `.env`

## Capabilities

### New Capabilities

- `vault-path-resolution`: 统一 vault 路径检测与解析逻辑，支持多来源（环境变量、插件 header、CWD 自动检测），确保新环境可用
- `per-request-config`: 扩展所有 API 路由支持从请求 header 读取用户配置（API key、vault 路径等），不限于 chat 路由

### Modified Capabilities

（无已有 specs 需要修改）

## Impact

- **后端核心**：`src/config.py`、`src/api/deps.py`、`src/scripts/__init__.py`
- **API 路由**：`src/api/routes/` 下所有路由需支持 per-request config
- **配置文件**：`.env.example` 需修正环境变量名
- **插件协议**：新增 `x-vault-path` header 用于传递 vault 路径
- **向后兼容**：现有 `.env` 配置方式继续有效，header 是可选覆盖
