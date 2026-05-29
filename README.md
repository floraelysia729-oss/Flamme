# Flamme

LLM 驱动的本地知识库 — Obsidian 插件 + Python 后端 + Tauri 桌面 IDE。

> **隐私设计**：笔记始终留在本地 vault，从不上传。后端仅用你提供的 API Key 转发请求到 LLM 供应商，不持久化用户内容。

## 仓库结构（Monorepo）

```
Flamme/
├── README.md           ← 你在这里
├── plugin/             ← Obsidian 插件
├── src/                ← Python 后端（FastAPI）
├── pyproject.toml
├── tests/
├── desktop/            ← Tauri 桌面 IDE（fork Tolaria）
│   ├── src/            # React 前端
│   ├── src-tauri/      # Rust vault / sidecar
│   └── scripts/
└── docs/
    ├── obsidian-plugin.md
    └── desktop-integration.md
```

| 组件 | 目录 | 说明 |
|------|------|------|
| **Obsidian 插件** | [`plugin/`](plugin/) | Svelte 5 插件，通过 HTTP 调用后端 |
| **Python 后端** | [`src/`](src/) | FastAPI：Agent、检索、图谱、摄入 |
| **Desktop IDE** | [`desktop/`](desktop/) | Tauri 壳 + 自动 sidecar |

## 快速选择

- **Obsidian 用户** → [插件文档](docs/obsidian-plugin.md)，部署后端 + 安装 `plugin/`
- **Desktop 用户** → [Desktop 集成文档](docs/desktop-integration.md)，进入 `desktop/` 开发
- **后端开发** → 仓库根目录 `pip install -e .`，见下方

## 后端（共用）

插件与 Desktop 共用同一套 Python 后端：

```bash
git clone https://github.com/floraelysia729-oss/Flamme.git
cd Flamme

python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -e .
cp .env.example .env   # 填入 API Key

python -m uvicorn src.api.app:app --port 8765 --reload
```

默认端口 `8765`，访问 `http://localhost:8765/api/status` 验证。

## 环境变量

| 变量 | 用途 | 推荐 |
|------|------|------|
| `LLM_API_KEY` | Chat 模型 | DeepSeek |
| `LLM_BASE_URL` | Chat API | `https://api.deepseek.com` |
| `LLM_MODEL` | Chat 模型名 | `deepseek-chat` |
| `EMBED_API_KEY` | 向量嵌入 | 阿里 DashScope |
| `EMBED_MODEL` | 嵌入模型 | `text-embedding-v3` |
| `BRAIN_API_KEY` | 多 Agent 编排（不填则复用 LLM） | 同 LLM |
| `MINERU_API_TOKEN` | PDF/PPT 解析 | 可选 |

## 版本与 Release

各组件独立打 tag，日常开发都在 `main`：

| 组件 | Tag 示例 | 打包范围 |
|------|----------|----------|
| 插件 | `plugin-v2.1.0` | 仅 `plugin/` |
| 后端 | `backend-v2.0.0` | `src/` + `pyproject.toml` + `tests/` |
| Desktop | `desktop-v0.1.0` | 仅 `desktop/` |

Release 名称建议：`Flamme-plugin-v2.x`、`Flamme-desktop-v0.x`。详见 [AGENTS.md](AGENTS.md)。

## 架构概览

```
  Obsidian / Desktop UI          Python Backend (src/)          LLM API
  ┌────────────────────┐        ┌──────────────────────┐      ┌────────┐
  │ plugin/ 或 desktop/ │─HTTP─→│ FastAPI + Orchestrator│─────→│ 供应商  │
  │ X-Vault-Path header │        │ SQLite + 向量 + 图谱   │      └────────┘
  │ vault .md 文件      │←JSON──│ 127.0.0.1:8765        │
  └────────────────────┘        └──────────────────────┘
```

**后端组装分层**（[`src/api/runtime.py`](src/api/runtime.py)）：

| 层级 | 函数 | 用途 |
|------|------|------|
| Config | `VaultContext` | 从 `X-Vault-Path` 解析 vault 与 DB 路径 |
| 轻量读 | `build_db` | status、documents 列表 |
| 工具调用 | `build_tools` | search、sync、graph build |
| Worker | `build_coordinator` | ingest 单文件 |
| Agent | `build_runtime` | chat（Orchestrator） |

- **文件不离开本地** — 所有 .md、SQLite 索引、向量都在 vault 里
- **后端不存数据** — 只转发 LLM 请求
- **文件是真相来源** — 索引随时可从 .md 重建

### Vault 目录结构

```
vault/
├── entities/                  ← 知识实体页
├── topics/                    ← 主题综述页
├── {课程名}/                  ← 人读区（原始文件）
│   ├── 课件.pdf
│   └── .flamme/              ← 源文件夹级 AI 中间产物
│       ├── converted/
│       └── ocr/
└── .wiki/                    ← 索引（可重建）
    ├── knowledge.db
    └── embeddings/
```

## API 端点

| 端点 | 用途 |
|------|------|
| `POST /api/chat` | SSE 流式对话 |
| `POST /api/documents/search` | 语义搜索 |
| `POST /api/ingest/sync` | 同步索引 |
| `GET /api/graph/full` | 知识图谱 |
| `GET /api/status` | 状态统计 + vault 解析信息 |

## CLI 工具

```bash
llm-wiki ingest "课程/论文.pdf"
llm-wiki sync --embed --graph
llm-wiki entity-build "课程/人工智能导论"
llm-wiki fix --lint
```

## 开发

```bash
# 后端测试
pip install -e ".[dev]"
pytest

# 插件
cd plugin && npm install && npm run dev

# Desktop
cd desktop && pnpm install && pnpm tauri dev
```

## 文档

- [Obsidian 插件](docs/obsidian-plugin.md)
- [Desktop 集成](docs/desktop-integration.md)
- [Flamme × Tolaria 蓝图](desktop/docs/FLAMME-TOLARIA-INTEGRATION.md)
- [Agent 指南（Monorepo）](AGENTS.md)

## License

- 后端 + 插件：MIT
- Desktop：AGPL-3.0-or-later（fork 自 Tolaria）
