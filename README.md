# Flamme

本地知识库插件 — LLM 驱动的摄入、检索和知识图谱管理，为 Obsidian vault 打造。

## 架构

```
Obsidian Vault
├── .flamme/              ← AI 生成的内容
│   ├── converted/        ← PDF/PPT 转换的 Markdown
│   ├── entities/         ← 知识实体页
│   ├── ocr/              ← 薄页 OCR 文本
│   └── topics/           ← 主题综述页
└── .wiki/                ← 索引（可重建）
    ├── knowledge.db      ← SQLite 元数据
    ├── embeddings/       ← 向量索引
    └── graph.json        ← 知识图谱
```

**文件是真相来源** — SQLite 和向量只是索引，随时可以重建。

## 安装

```bash
# 后端
cd llm-wiki-2
pip install -e .

# 前端
cd flamme
npm install
```

### 依赖

- Python >= 3.10
- Node.js >= 18

## 配置

```bash
cp .env.example .env
```

填入 API key。三角色 LLM 配置：

| 角色 | 用途 | 推荐供应商 |
|------|------|-----------|
| `LLM_*` | 通用对话 + 实体提取 | DeepSeek |
| `EMBED_*` | 向量嵌入 | 阿里 DashScope |
| `BRAIN_*` | 多 Agent 编排 | 智谱 GLM |

## 使用

### 1. 摄入文档

```bash
# PDF → Markdown（MinerU 云端解析，支持表格/公式）
python scripts/ingest.py "论文.pdf" --level pro

# PPTX → Markdown（本地 python-pptx 提取）
python scripts/ingest.py "课件.pptx" --level lite

# PPTX 额外转 PDF 用 MinerU 解析（需安装 PowerPoint）
python scripts/ingest.py "课件.pptx" --level lite --ppt2pdf
```

### 2. 实体提取

```bash
# jieba + LLM 三阶段管线（高质量）
python scripts/entity_builder.py "pro/人工智能导论"

# 或纯 LLM 提取
python scripts/entity_extract.py "pro/人工智能导论" --output entities.json
python scripts/wiki_entity.py generate entities.json
```

### 3. 同步索引

```bash
# 文件变更后同步到 SQLite + 向量
llm-wiki sync
llm-wiki sync --embed        # 同时生成向量
llm-wiki sync --embed --graph # 同时重建图谱
```

### 4. 查询

```bash
# CLI 查询
llm-wiki query "什么是矩阵的奇异值分解"
llm-wiki search "线性代数" --top 5

# 知识图谱
llm-wiki graph build
llm-wiki graph query "矩阵"
llm-wiki graph isolates

# 多 Agent 任务
llm-wiki task "分析所有数学笔记的知识盲点" --workers 3
```

### 5. 启动服务

```bash
# 后端 API（端口 8765）
python -m src.api.app

# 前端（端口 3000，自动代理到后端）
cd flamme && npm run dev
```

API 端点：

| 端点 | 用途 |
|------|------|
| `POST /api/chat` | SSE 流式对话 |
| `POST /api/documents/search` | 语义搜索 |
| `POST /api/ingest/sync` | 同步索引 |
| `GET /api/graph/full` | 知识图谱 |
| `GET /api/status` | 状态统计 |

### 6. 维护

```bash
python scripts/tag_notes.py "pro/人工智能导论"   # LLM 自动标签
python scripts/wiki_fix.py --lint                # 健康检查
python scripts/wiki_fix.py --fix-related         # 修复 wikilink 格式
python scripts/wiki_fix.py --rebuild-index       # 重建索引
```

## 三级处理规则

| 级别 | 适用 | 处理方式 |
|------|------|---------|
| `raw` | 日记、随笔 | 只加 frontmatter，不改原文 |
| `lite` | 课件、PPT | 转换为 .md，加标签建链接 |
| `pro` | 论文、深度分析 | 完整概括，建实体页和概念页 |

## 开发

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
