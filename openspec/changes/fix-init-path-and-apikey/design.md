## Context

后端有两种运行场景：(1) CLI 直接运行（`src/main.py`），(2) FastAPI 服务模式（`src/api/app.py`）。当前 vault 路径解析在两种场景下都依赖 CWD 或 `.env` 硬编码路径，新环境部署时极易出错。

当前有两套独立的 vault 检测逻辑（`src/config.py` 和 `src/scripts/__init__.py`），检查不同的环境变量名，可能导致不一致。

API 配置方面，只有 `/api/chat` 路由通过 `get_request_config()` 读取 header 中的 API key，其他路由（`/api/ingest`、`/api/documents`）直接使用 `@lru_cache` 单例，忽略插件传来的配置。

## Goals / Non-Goals

**Goals:**
- 新环境零配置即可启动（只要从 vault 目录内启动或通过插件传路径）
- 所有 API 路由一致地读取插件传来的配置（API key、vault 路径）
- 消除两套 vault 检测逻辑的分歧
- 向后兼容：现有 `.env` 配置继续有效

**Non-Goals:**
- 不做配置热重载（仍需重启生效）
- 不做完整的启动健康检查（单独 issue）
- 不改变 `.wiki/` 目录放在 vault 内的设计

## Decisions

### D1: 统一 vault 路径解析优先级

采用明确的优先级链：**插件 header > 环境变量 > CWD 自动检测**。

`config.py::detect_vault()` 成为唯一实现，`scripts/__init__.py` 复用同一函数。

理由：避免两套逻辑，优先级清晰。

替代方案：在插件启动时写入 `.env` — 放弃，因为会产生文件写入副作用。

### D2: 新增 `x-vault-path` header

插件通过 `x-vault-path` header 传递 vault 绝对路径。后端在 `config_from_headers()` 中读取。

理由：与现有 `x-llm-key` 等 header 风格一致，无额外接口。

### D3: 为 `/api/ingest` 等路由添加 per-request config 支持

创建新的依赖注入函数 `get_request_config_or_default`，行为：
- 如果请求包含配置 header → 返回 per-request Config
- 否则 → 返回 `@lru_cache` 的默认 Config

需要修改的受影响路由逐个接入。对于 `/api/ingest`，MinerU token 是核心需求，必须支持 header 传入。

理由：不改 `@lru_cache` 单例本身，而是让路由层选择使用 per-request 还是默认 config。

替代方案：去掉所有 `@lru_cache` 改为 per-request — 放弃，改动太大且有性能影响。

### D4: 修复 `.env.example`

将 `FLAMME_VAULT` 改为 `LLM_WIKI_VAULT`，添加注释说明路径优先级。

## Risks / Trade-offs

- **[插件需同步更新]** → 插件需要在每个请求中附加 `x-vault-path` header，这是必须的插件侧改动
- **[per-request Config 对 DB 的影响]** → `/api/ingest` 如果使用 per-request config，需要确保 DB 路径正确。当前 DB 路径基于 `vault_path`，如果 header 传了不同 vault，会打开不同的 DB — 这是期望行为
- **[向后兼容]** → 不传 header 时行为完全不变，只读 `.env` — 无风险
