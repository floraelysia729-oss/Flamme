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
- **Vault Path** — 你的 Obsidian vault 绝对路径（如 `D:\notebook`）
- **Test Connection** — 验证连通

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
  ┌──────────────────┐              ┌──────────────────┐
  │ plugin (Svelte 5) │─── HTTP ───→│  FastAPI 路由     │
  │   │               │              │   │               │
  │ vault .md 文件    │              │  调用各 LLM API   │──→ DeepSeek / DashScope / MinerU
  │ .flamme/ (AI生成) │              │  返回处理结果     │
  │ .wiki/ (索引)     │  ← JSON ────│                   │
  └──────────────────┘              └──────────────────┘
```

- **文件不离开本地** — 所有 .md 文件、SQLite 索引、向量数据都在你的 vault 里
- **后端不存数据** — 只转发请求到 LLM 供应商，不持久化用户内容
- **文件是真相来源** — SQLite 和向量只是索引，随时可以从 .md 文件重建

### 目录结构

```
vault/
├── {level}/{课程名}/          ← 人读区（原始文件）
│   ├── 课件.pdf
│   ├── 笔记.pptx
│   └── .flamme/              ← AI 区（Flamme 管理）
│       ├── converted/        ← PDF/PPT 转换的 Markdown
│       ├── entities/         ← 知识实体页
│       ├── ocr/              ← OCR 文本
│       └── topics/           ← 主题综述页
└── .wiki/                    ← 索引（可重建）
    ├── knowledge.db          ← SQLite 元数据
    └── embeddings/           ← 向量索引
```

## 三级处理规则

| 级别 | 适用 | 处理方式 |
|------|------|---------|
| `raw` | 日记、随笔 | 只加 frontmatter，不改原文 |
| `lite` | 课件、PPT | 转 .md，加标签建链接 |
| `pro` | 论文、深度分析 | 完整概括，建实体页和概念页 |

## API 端点

| 端点 | 用途 |
|------|------|
| `POST /api/chat` | SSE 流式对话 |
| `POST /api/documents/search` | 语义搜索 |
| `POST /api/ingest/sync` | 同步索引 |
| `GET /api/graph/full` | 知识图谱 |
| `GET /api/status` | 状态统计 |

## CLI 工具

CLI 用于批量操作和自动化：

```bash
llm-wiki ingest "论文.pdf" --level pro     # 摄入文档
llm-wiki sync --embed --graph              # 同步索引+图谱
llm-wiki entity-build "pro/人工智能导论"     # 实体提取
llm-wiki tag "pro/人工智能导论"              # 自动标签
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
