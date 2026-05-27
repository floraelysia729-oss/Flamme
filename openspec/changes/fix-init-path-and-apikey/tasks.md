## 1. 统一 vault 路径检测

- [x] 1.1 修改 `src/scripts/__init__.py`：移除独立的 `_detect_vault()` 函数，改为从 `src/config.py` 导入 `detect_vault()`
- [x] 1.2 修改 `src/config.py::detect_vault()`：统一环境变量检查，只认 `LLM_WIKI_VAULT`（移除 `FLAMME_VAULT` 分支）
- [x] 1.3 修复 `.env.example`：将 `FLAMME_VAULT` 改为 `LLM_WIKI_VAULT`，添加优先级说明注释

## 2. 扩展 header 配置支持

- [x] 2.1 修改 `src/config.py::config_from_headers()`：新增 `x-vault-path` header 解析，映射到 `vault_path`
- [x] 2.2 修改 `src/api/deps.py`：新增 `get_request_config_or_default()` 依赖注入函数，有 header 返回 per-request Config，否则返回 cached 默认 Config

## 3. 路由接入 per-request config

- [x] 3.1 修改 `/api/ingest` 路由：使用 `get_request_config_or_default` 替代直接使用 `get_db()` 等单例，确保 MinerU token 从 header 读取
- [x] 3.2 修改 `/api/documents` 路由：同上，接入 per-request config
- [x] 3.3 检查其他 `/api/` 路由：确认是否有需要接入的，逐一处理

## 4. 验证

- [x] 4.1 新环境测试：在 `D:\dev\LLM-WIKI\test` 目录从零启动后端，验证路径解析正确
- [x] 4.2 Header 配置测试：通过 curl 发送带 `x-mineru-token` 和 `x-vault-path` header 的请求，验证后端正确读取
- [x] 4.3 向后兼容测试：不带任何 header 发送请求，验证 `.env` 配置仍然生效
