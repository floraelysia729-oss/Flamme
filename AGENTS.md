# Agent 指南 — Flamme Monorepo

> 供 Cursor / Claude Code 等 agent 读取，确保正确理解仓库结构与发布流程。

## 仓库信息

| 项 | 值 |
|----|-----|
| GitHub | `https://github.com/floraelysia729-oss/Flamme.git` |
| 默认分支 | `main` |
| 结构 | **Monorepo** — 一个 repo，多个目录 |

## 目录职责

```
Flamme/
├── plugin/          # Obsidian 插件（Svelte 5）— 独立 release
├── src/             # Python 后端（FastAPI）— 与 plugin/desktop 共用
├── pyproject.toml   # Python 包定义
├── tests/           # Python 测试
├── desktop/         # Tauri Desktop IDE — 独立 release
│   ├── src/         # React 前端
│   ├── src-tauri/   # Rust + flamme_sidecar
│   └── scripts/     # dev-flamme.ps1 等
└── docs/            # 跨组件文档
```

**不要**把 `desktop/` 内容放到仓库根；**不要**把 `plugin/` 或 `src/` 移到 `desktop/` 内。

## 后端路径解析（Desktop）

`desktop/src-tauri/src/flamme_sidecar.rs` 和 `desktop/scripts/dev-flamme.ps1` 按以下顺序查找 Python 后端：

1. `desktop/flamme-backend/`（本地 junction，gitignore）
2. Monorepo 根目录 `Flamme/`（含 `src/api/app.py`）

Clone 后**无需**创建 junction 即可开发 Desktop。

## 日常开发

| 任务 | 工作目录 | 命令 |
|------|----------|------|
| Python 后端 | 仓库根 | `pip install -e .` / `pytest` / `uvicorn src.api.app:app --port 8765` |
| Obsidian 插件 | `plugin/` | `npm install` / `npm run dev` |
| Desktop | `desktop/` | `pnpm install` / `pnpm tauri dev` |

## Git 操作

- **提交目标**：`https://github.com/floraelysia729-oss/Flamme.git`
- **工作目录**：`Flamme/`（不是 `LLM-WIKI/3.0/` 或 `LLM-WIKI/2.0/`）
- 改 `plugin/` 或 `desktop/` 互不影响，都在 `main` 分支
- **不要提交**：`.env`、`node_modules/`、`dist/`、`venv/`、`.python-path`、`desktop/flamme-backend/` junction

## Release / Tag 规范

各组件**独立**打 tag，从 `main` 分支：

| 组件 | Tag 格式 | 打包内容 | Release 标题示例 |
|------|----------|----------|------------------|
| 插件 | `plugin-v2.1.0` | `plugin/main.js`, `manifest.json`, `styles.css` | Flamme-plugin-v2.1.0 |
| 后端 | `backend-v2.0.0` | `src/`, `pyproject.toml`, `tests/` | Flamme-backend-v2.0.0 |
| Desktop | `desktop-v0.1.0` | `desktop/` 整棵 | Flamme-desktop-v0.1.0 |

### 插件 Release 步骤

```bash
cd plugin && npm run build
# 上传 main.js, manifest.json, styles.css 到 GitHub Release
git tag plugin-v2.1.0
git push origin plugin-v2.1.0
```

### Desktop Release 步骤

```bash
cd desktop
pnpm install
pnpm tauri build
# 上传安装包到 GitHub Release
git tag desktop-v0.1.0
git push origin desktop-v0.1.0
```

## 用户入口

- Obsidian 用户 clone 后看根 [README.md](../README.md) → [docs/obsidian-plugin.md](obsidian-plugin.md) → 进 `plugin/`
- Desktop 用户 clone 后看根 README → [docs/desktop-integration.md](desktop-integration.md) → 进 `desktop/`

## 常见错误

| 错误 | 原因 | 修复 |
|------|------|------|
| `flamme-backend not found` | 在旧 `3.0/` 目录开发，未在 monorepo | 切换到 `Flamme/desktop/` |
| sidecar 找不到 Python | 未安装 venv | 在仓库根 `pip install -e .`，设 `FLAMME_PYTHON` |
| 提交了 junction | `desktop/flamme-backend/` 未被 ignore | 已在 `.gitignore`，勿 force add |
| push 到错误 remote | 在 `LLM-WIKI/3.0` 而非 `Flamme/` | `cd Flamme && git push origin main` |
