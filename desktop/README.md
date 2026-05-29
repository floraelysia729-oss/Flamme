# Flamme Desktop

Tauri 壳（fork 自 [Tolaria](https://github.com/refactoring-club/tolaria)）+ Flamme Python AI 后端。

> 本目录是 Flamme **Monorepo** 的 Desktop 组件。仓库根目录的 `src/` 是共用 Python 后端。  
> 总览见 [根 README](../README.md)，集成说明见 [docs/desktop-integration.md](../docs/desktop-integration.md)。

## 前置条件

| 工具 | 版本 |
|------|------|
| Node.js | 20+ |
| pnpm | 10+ |
| Rust | 1.77+ |
| Python | 3.10+ |

## 仓库结构

```
Flamme/                      ← monorepo 根 = Python 后端
├── src/api/app.py
├── .env
└── desktop/                 ← 本目录
    ├── src/                 # React 前端（Tolaria fork）
    ├── src-tauri/           # Rust vault/git + flamme sidecar
    ├── scripts/             # 开发辅助脚本
    └── docs/                # 集成蓝图
```

Sidecar 自动查找后端：`desktop/flamme-backend/`（可选 junction）→ monorepo 根 `../`。

## 开发模式

### 自动 spawn（默认）

```powershell
# 先在仓库根安装后端
cd ..
pip install -e .
Copy-Item .env.example .env

# 启动 Desktop
cd desktop
pnpm install
pnpm tauri dev
```

打开 vault 后，Tauri 会在后台启动 Python sidecar（`127.0.0.1:8765`）。

设置 `FLAMME_DEV=1` 可恢复双终端调试（Rust 不 spawn，需手动 uvicorn）。

### Phase 0 双终端（`FLAMME_DEV=1` 时）

**终端 1 — Tauri**

```powershell
cd desktop
$env:FLAMME_DEV = "1"
pnpm tauri dev
```

**终端 2 — Python 后端**

```powershell
cd desktop
.\scripts\dev-flamme.ps1 -VaultPath "D:\path\to\your-vault"
```

### 验证

```powershell
curl http://127.0.0.1:8765/api/status
```

StatusBar 应显示 **Flamme · 已就绪**。

## 环境变量

| 变量 | 说明 |
|------|------|
| `FLAMME_VAULT_PATH` | Python 定位 vault 根目录 |
| `FLAMME_WIKI_DIR` | 默认 `{vault}/.wiki` |
| `FLAMME_DEV=1` | Rust 不自动 spawn sidecar |
| `FLAMME_PYTHON` | 指定 sidecar Python 可执行文件 |

Sidecar Python 优先级：`FLAMME_PYTHON` → `.python-path` → `venv/` → 系统 `python`。

```powershell
$env:FLAMME_PYTHON = "D:\path\to\Flamme\venv\Scripts\python.exe"
pnpm tauri dev
```

## API 边界

- **Rust invoke**：所有 `.md` CRUD、Git、文件监听
- **Python `:8765`**：Agent、语义检索、图谱、索引流水线
- 运维 API：`/api/pipeline/*`

## Release

Tag 格式：`desktop-v0.x.x`（仅打包 `desktop/` 目录）

```powershell
pnpm tauri build
```

## 相关文档

- [Desktop 集成指南](../docs/desktop-integration.md)
- [Flamme × Tolaria 集成蓝图](docs/FLAMME-TOLARIA-INTEGRATION.md)
- [Agent 指南（Monorepo）](../AGENTS.md)

## Cargo features

| Feature | 说明 |
|---------|------|
| `flamme`（default） | 无 Tolaria 内置 AI/MCP |
| `tolaria-ai` | 保留 upstream AI/MCP（对比调试用） |

```powershell
cd src-tauri
cargo check --features tolaria-ai
```
