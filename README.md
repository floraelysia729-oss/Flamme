# Flamme

LLM 驱动的 Obsidian 知识库插件 — 智能摄入、语义检索、知识图谱。

> **隐私设计**：你的笔记文件始终留在本地 vault，从不上传。后端仅用你提供的 API Key 转发请求到 LLM 供应商，不存用户数据。

## 安装插件

### 1. 安装到 Obsidian

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

### 2. 配置

打开 Flamme 设置页：

**连接**
- **Backend URL** — `http://120.26.21.155:8765`（已部署的云端后端）
- **Test Connection** — 验证连通

**API Keys**（填入你自己的 Key）

| Key | 用途 | 推荐供应商 |
|-----|------|-----------|
| LLM API Key | 对话 + 实体提取 | DeepSeek |
| Embedding API Key | 向量嵌入 | 阿里 DashScope |
| Brain API Key | 多 Agent 编排 | 智谱 GLM |
| MinerU Token | PDF 精准解析 | MinerU |

不需要自己部署后端，后端已由开发者维护。

### 3. 使用

- **对话** — 打开 Flamme 侧边栏，直接提问。支持搜索（检索已有笔记）和学习（深度解释）两种模式。
- **知识图谱** — 可视化笔记间的关联，发现孤立页面和知识盲点。
- **自动同步** — vault 文件变更自动同步到索引。

## 部署云端后端

```bash
git clone https://github.com/floraelysia729-oss/Flamme.git
cd Flamme
python3.11 -m venv venv
./venv/bin/pip install -e .
```

启动服务（生产推荐 gunicorn）：

```bash
./venv/bin/gunicorn -c gunicorn.conf.py src.api.app:app
```

默认端口 `8765`。插件 Backend URL 填写 `http://your-server:8765`。

### 环境变量

服务端在 `.env` 中统一配置 LLM API Key：

```bash
cp .env.example .env
```

| 变量 | 用途 |
|------|------|
| `LLM_API_KEY` | Chat 模型 |
| `LLM_BASE_URL` | Chat API 地址 |
| `EMBED_API_KEY` | 向量嵌入 |
| `BRAIN_API_KEY` | Agent 编排 |
| `MINERU_API_TOKEN` | PDF 解析 |

## 架构

```
  本地 Obsidian Vault                云端后端 (FastAPI)
  ┌──────────────────┐              ┌──────────────────┐
  │ plugin (Svelte 5) │─── HTTP ───→│  API 路由         │
  │   │               │              │   │               │
  │ vault .md 文件    │              │  调用各 LLM API   │──→ DeepSeek / GLM / DashScope
  │ .flamme/ (AI生成) │              │  返回处理结果     │
  │ .wiki/ (索引)     │  ← JSON ────│                   │
  └──────────────────┘              └──────────────────┘
```

- **文件不离开本地** — 所有 .md 文件、SQLite 索引、向量数据都在你的 vault 里
- **云端不存数据** — 后端只转发请求到 LLM 供应商，不持久化用户内容
- **文件是真相来源** — SQLite 和向量只是索引，随时可以从 .md 文件重建

```
vault/
├── .flamme/              ← AI 生成的内容
│   ├── converted/        ← PDF/PPT 转换的 Markdown
│   ├── entities/         ← 知识实体页
│   ├── ocr/              ← OCR 文本
│   └── topics/           ← 主题综述页
└── .wiki/                ← 索引（可重建）
    ├── knowledge.db      ← SQLite 元数据
    └── embeddings/       ← 向量索引
```

## API 端点

| 端点 | 用途 |
|------|------|
| `POST /api/chat` | SSE 流式对话 |
| `POST /api/documents/search` | 语义搜索 |
| `POST /api/ingest/sync` | 同步索引 |
| `GET /api/graph/full` | 知识图谱 |
| `GET /api/status` | 状态统计 |

## CLI 工具

CLI 用于 agent 自动化和批量操作，不需要普通用户使用。

```bash
llm-wiki ingest "论文.pdf" --level pro     # 摄入文档
llm-wiki sync --embed --graph              # 同步索引+图谱
llm-wiki entity-build "pro/人工智能导论"     # 实体提取
llm-wiki tag "pro/人工智能导论"              # 自动标签
llm-wiki fix --lint                        # 健康检查
```

## 三级处理规则

| 级别 | 适用 | 处理方式 |
|------|------|---------|
| `raw` | 日记、随笔 | 只加 frontmatter，不改原文 |
| `lite` | 课件、PPT | 转 .md，加标签建链接 |
| `pro` | 论文、深度分析 | 完整概括，建实体页和概念页 |

## 开发

```bash
pip install -e ".[dev]"
pytest

# 插件开发
cd plugin && npm install && npm run dev
```

## License

MIT
