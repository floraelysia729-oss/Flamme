# Desktop 集成

Flamme Desktop 是 Tauri 桌面 IDE（fork [Tolaria](https://github.com/refactoring-club/tolaria)），位于 [`desktop/`](../desktop/) 目录。

## 前置条件

| 工具 | 版本 |
|------|------|
| Node.js | 20+ |
| pnpm | 10+ |
| Rust | 1.77+ |
| Python | 3.10+ |

## Monorepo 布局

```
Flamme/                    ← 仓库根 = Python 后端
├── src/api/app.py
├── .env
└── desktop/               ← 本目录
    ├── src/               # React 前端
    ├── src-tauri/         # Rust vault + sidecar
    └── scripts/
```

Desktop 启动时，Rust sidecar 自动查找 Python 后端，优先级：

1. `desktop/flamme-backend/`（可选 junction，本地开发用）
2. **Monorepo 根目录** `../`（clone 后默认可用，无需 junction）

## 快速开始

### 1. 安装后端依赖（仓库根目录）

```powershell
cd Flamme
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env   # 填入 API Key
```

### 2. 启动 Desktop

```powershell
cd desktop
pnpm install
pnpm tauri dev
```

打开 vault 后，Tauri 会在后台启动 Python sidecar（`127.0.0.1:8765`），StatusBar 显示 **Flamme · 已就绪**。

### 3. 验证

```powershell
curl http://127.0.0.1:8765/api/status
```

## 开发模式

### 自动 spawn（默认）

打开 vault → Rust 后台 spawn uvicorn → 轻量索引 `index + git`（不阻塞编辑）。

### 双终端调试（`FLAMME_DEV=1`）

Rust 不自动 spawn，需手动启动后端：

```powershell
# 终端 1
cd desktop
$env:FLAMME_DEV = "1"
pnpm tauri dev

# 终端 2
cd desktop
.\scripts\dev-flamme.ps1 -VaultPath "D:\path\to\your-vault"
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `FLAMME_VAULT_PATH` | Python 定位 vault 根目录 |
| `FLAMME_WIKI_DIR` | 默认 `{vault}/.wiki` |
| `FLAMME_DEV=1` | Rust 不自动 spawn sidecar |
| `FLAMME_PYTHON` | 指定 Python 可执行文件 |

Python 选择优先级：`FLAMME_PYTHON` → `.python-path` → `venv/` → 系统 `python`。

```powershell
# 使用仓库根 venv
$env:FLAMME_PYTHON = "D:\path\to\Flamme\venv\Scripts\python.exe"
pnpm tauri dev
```

## API 边界

| 层 | 职责 |
|----|------|
| **Rust invoke** | `.md` CRUD、Git、文件监听 |
| **Python `:8765`** | Agent、语义检索、图谱、索引流水线 |

运维 API：`/api/pipeline/*`（避免与 Tolaria mock 冲突）。

## 可选：flamme-backend junction

本地若习惯旧布局，可创建 junction（**不提交 git**）：

```powershell
cd desktop
cmd /c mklink /J flamme-backend ..
```

## Release

Desktop 版本 tag：`desktop-v0.x.x`

打包范围：仅 `desktop/` 目录。构建：

```powershell
cd desktop
pnpm tauri build
```

## 相关文档

- [Flamme × Tolaria 集成蓝图](../desktop/docs/FLAMME-TOLARIA-INTEGRATION.md)
- [Desktop README](../desktop/README.md)
