## ADDED Requirements

### Requirement: 所有 API 路由支持从 header 读取配置
所有 `/api/` 路由 SHALL 支持从请求 header 读取用户配置（API key、MinerU token、vault 路径），行为与 `/api/chat` 一致。

#### Scenario: 插件向 ingest 路由传递 MinerU token
- **WHEN** 插件向 `/api/ingest` 发送请求，header 包含 `x-mineru-token: my-token`
- **THEN** 后端使用 `my-token` 作为 MinerU API token 执行解析

#### Scenario: 插件向 ingest 路由传递 vault 路径
- **WHEN** 插件向 `/api/ingest` 发送请求，header 包含 `x-vault-path: /data/my-vault`
- **THEN** 后端使用 `/data/my-vault` 作为 vault 路径进行后续操作

#### Scenario: 无 header 时使用默认配置
- **WHEN** 请求不包含任何配置 header
- **THEN** 后端使用 `.env` 或环境变量的默认配置，行为与改动前一致

### Requirement: `config_from_headers` 支持 vault 路径
`config_from_headers()` 函数 SHALL 识别 `x-vault-path` header，将其作为 `vault_path` 传入 Config。

#### Scenario: Header 传递 vault 路径
- **WHEN** 请求 header 包含 `x-vault-path: D:\test-vault`
- **THEN** `config_from_headers()` 返回的 Config 的 `vault_path` 为 `D:\test-vault`

#### Scenario: Header vault 路径优先于环境变量
- **WHEN** `LLM_WIKI_VAULT` 环境变量设置为 `/env-vault`，同时请求 header 包含 `x-vault-path: /header-vault`
- **THEN** Config 使用 `/header-vault` 作为 vault 路径

### Requirement: per-request config 的依赖注入
系统 SHALL 提供一个可复用的依赖注入函数，让任何路由都能方便地获取 per-request 配置。

#### Scenario: 路由使用依赖注入获取配置
- **WHEN** 路由通过 `Depends(get_request_config_or_default)` 注入配置
- **THEN** 如果请求有配置 header 则返回 per-request Config，否则返回默认 cached Config
