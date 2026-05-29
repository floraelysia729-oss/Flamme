# Flamme

LLM 驱动的 Obsidian 知识库插件 — 智能摄入、语义检索、知识图谱。

> **隐私设计**：你的笔记文件始终留在本地 vault，从不上传。后端仅用你提供的 API Key 转发请求到 LLM 供应商，不存用户数据。

## 快速开始

### 前置条件

- Python 3.10+
- Node.js 18+（仅插件开发时需要）
- API Keys：至少需要 Chat LLM 和 Embedding 各一个

### 1. 部署后端

```bash
git clone https://github.com/floraelysia729-oss/Flamme.git
cd Flamme

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安装依赖
pip install -e .

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

启动服务：

```bash
# 开发模式
python -m uvicorn src.api.app:app --port 8765 --reload

# 生产模式（后台运行）
python -m uvicorn src.api.app:app --port 8765

# 或使用 entry point
flamme
```

默认端口 `8765`，启动后访问 `http://localhost:8765` 验证服务是否正常。

### 2. 安装 Obsidian 插件

将 `plugin/` 目录中的 `main.js`、`manifest.json`、`styles.css` 复制到你的 vault：

```
your-vault/
└── .obsidian/
    └── plugins/
        └── flamme/
            ├── main.js
            ├── manifest.json
            └── styles.css
```

在 Obsidian 中启用插件：设置 → 社区插件 → 已安装插件 → 启用 **Flamme**。

### 3. 配置插件

打开 Flamme 设置页：

**连接**
- **Backend URL** — 本地部署填 `http://localhost:8765`，远程服务器填对应地址
- **Test Connection** — 验证连通；成功时会显示文档数与 `vault_source`（应为 `header`）

插件会自动从 Obsidian 读取当前 vault 绝对路径，并在每个 API 请求携带 `X-Vault-Path` header，**无需在设置页手动填写 vault 路径**。

## 环境变量

编辑 `.env` 文件配置 API Key：

```bash
cp .env.example .env
```

### 必填

| 变量 | 用途 | 推荐供应商 |
|------|------|-----------|
| `LLM_API_KEY` | Chat 模型（对话 + 实体提取） | DeepSeek |
| `LLM_BASE_URL` | Chat API 地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | Chat 模型名 | `deepseek-chat` |
| `EMBED_API_KEY` | 向量嵌入 | 阿里 DashScope |
| `EMBED_MODEL` | 嵌入模型名 | `text-embedding-v3` |

### 可选

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `BRAIN_API_KEY` | 多 Agent 编排（不填则复用 LLM_KEY） | 同 LLM_API_KEY |
| `BRAIN_BASE_URL` | Agent 编排 API 地址 | 同 LLM_BASE_URL |
| `MINERU_API_TOKEN` | PDF/PPT/Word 精准解析 | 无（关闭 PDF 解析） |
| `LLM_WIKI_VAULT` | Vault 绝对路径 | 自动检测 `.obsidian/` |
| `LLM_MAX_CONCURRENCY` | 并发 LLM 请求数 | 2 |
| `LLM_LOG_LEVEL` | 日志级别 | INFO |

## 使用

- **对话** — 打开 Flamme 侧边栏，直接提问。支持搜索（检索已有笔记）和学习（深度解释）两种模式
- **摄入** — 对话中提到 PDF/PPT/Word 文件时自动解析入库，提取实体和概念
- **知识图谱** — 可视化笔记间的关联，发现孤立页面和知识盲点
- **自动同步** — vault 文件变更自动同步到索引

## 架构

```
  Obsidian Vault (本地)               Backend (本地/远程)
  ┌──────────────────┐              ┌──────────────────────────────┐
  │ plugin (Svelte 5) │─── HTTP ───→│  FastAPI 路由                 │
  │  X-Vault-Path     │              │    ↓ VaultContext（vault）   │
  │  X-LLM-Key 等     │              │    ↓ runtime 分层组装          │
  │ vault .md 文件    │              │  Orchestrator / Tools / DB   │──→ LLM API
  │ .flamme/ (AI生成) │              │  返回 JSON / SSE             │
  │ .wiki/ (索引)     │  ← JSON ────│                               │
  └──────────────────┘              └──────────────────────────────┘
```

**后端组装分层**（[`src/api/runtime.py`](src/api/runtime.py)）：

| 层级 | 函数 | 用途 |
|------|------|------|
| Config | `VaultContext` | 从 `X-Vault-Path` 解析 vault 与 DB 路径 |
| 轻量读 | `build_db` | status、documents 列表 |
| 工具调用 | `build_tools` | search、sync、graph build |
| Worker | `build_coordinator` | ingest 单文件 |
| Agent | `build_runtime` | chat（Orchestrator） |

- **文件不离开本地** — 所有 .md 文件、SQLite 索引、向量数据都在你的 vault 里
- **后端不存数据** — 只转发请求到 LLM 供应商，不持久化用户内容
- **文件是真相来源** — SQLite 和向量只是索引，随时可以从 .md 文件重建

### 目录结构

```
vault/
├── entities/                  ← 知识实体页（可见、可索引、进图谱）
├── topics/                    ← 主题综述页
├── comparisons/               ← 对比页
├── explorations/              ← 探索页
├── {课程名}/                  ← 人读区（原始文件，任意目录均可）
│   ├── 课件.pdf
│   ├── 笔记.md
│   └── .flamme/              ← 源文件夹级 AI 中间产物
│       ├── converted/        ← PDF/PPT 转换的 Markdown
│       └── ocr/              ← OCR 文本
└── .wiki/                    ← 索引（可重建）
    ├── knowledge.db          ← SQLite 元数据
    └── embeddings/           ← 向量索引
```

## 源文件保护

| 原则 | 说明 |
|------|------|
| 不可删除 | 系统清理只删 SQLite 索引，不删 vault 源文件 |
| 正文不改写 | LLM 产出写入 `.flamme/converted/` 或 `entities/` |
| 元数据可维护 | 允许更新源 `.md` 的 frontmatter 与 tags |

## HTTP 客户端契约

Obsidian 插件与未来 Web 客户端 **MUST** 在每个 API 请求携带以下 header（与 [`plugin/src/api/client.ts`](plugin/src/api/client.ts) 同构）：

| Header | 用途 |
|--------|------|
| `X-Vault-Path` | Obsidian vault 绝对路径（权威 vault 来源） |
| `X-LLM-Key` | Chat 模型 API Key |
| `X-Embed-Key` | 向量嵌入 API Key |
| `X-Brain-Key` | Orchestrator API Key |
| `X-MinerU-Token` | PDF/PPT 解析 Token |

后端通过 `VaultContext` 解析 vault；无 `X-Vault-Path` 时 fallback 到 `LLM_WIKI_VAULT` / 自动检测，并记录 warning。`GET /api/status` 返回 `vault_path`、`vault_source`、`db_path` 供调试。

CLI/scripts 不走 HTTP header，仍使用 `.env` 中的 `LLM_WIKI_VAULT`。

## API 端点

| 端点 | 用途 |
|------|------|
| `POST /api/chat` | SSE 流式对话 |
| `POST /api/documents/search` | 语义搜索 |
| `POST /api/ingest/sync` | 同步索引 |
| `GET /api/graph/full` | 知识图谱 |
| `GET /api/status` | 状态统计 + vault 解析信息（`vault_path`、`vault_source`） |

## CLI 工具

CLI 用于批量操作和自动化：

```bash
llm-wiki ingest "课程/论文.pdf"            # 摄入文档
llm-wiki sync --embed --graph              # 同步索引+图谱
llm-wiki entity-build "课程/人工智能导论"     # 实体提取
llm-wiki tag "课程/笔记.md"                # 自动标签
llm-wiki fix --lint                        # 健康检查
```

## 开发

```bash
pip install -e ".[dev]"
pytest

# 插件开发
cd plugin && npm install && npm run dev
```

## License

MIT
