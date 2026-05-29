# Obsidian 插件

Flamme Obsidian 插件位于仓库 [`plugin/`](../plugin/) 目录。

## 前置条件

- Python 3.10+（后端）
- Node.js 18+（仅插件开发时需要）
- API Keys：至少需要 Chat LLM 和 Embedding 各一个

## 1. 部署后端

在**仓库根目录**（不是 `plugin/`）：

```bash
cd Flamme
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -e .
cp .env.example .env         # 填入 API Key

python -m uvicorn src.api.app:app --port 8765 --reload
```

验证：`curl http://localhost:8765/api/status`

## 2. 安装插件

将 `plugin/` 中的构建产物复制到 vault：

```
your-vault/
└── .obsidian/
    └── plugins/
        └── flamme/
            ├── main.js
            ├── manifest.json
            └── styles.css
```

开发模式：

```bash
cd plugin
npm install
npm run dev    # watch 构建到 plugin/
```

在 Obsidian 中：设置 → 社区插件 → 启用 **Flamme**。

## 3. 配置

**连接**
- **Backend URL** — 本地 `http://localhost:8765`
- **Test Connection** — 验证连通；成功时显示文档数与 `vault_source`（应为 `header`）

插件自动从 Obsidian 读取 vault 绝对路径，每个 API 请求携带 `X-Vault-Path` header，**无需手动填写 vault 路径**。

## HTTP Header 契约

| Header | 用途 |
|--------|------|
| `X-Vault-Path` | Obsidian vault 绝对路径 |
| `X-LLM-Key` | Chat 模型 API Key |
| `X-Embed-Key` | 向量嵌入 API Key |
| `X-Brain-Key` | Orchestrator API Key |
| `X-MinerU-Token` | PDF/PPT 解析 Token |

实现见 [`plugin/src/api/client.ts`](../plugin/src/api/client.ts)。

## 环境变量（后端 .env）

| 变量 | 用途 | 推荐 |
|------|------|------|
| `LLM_API_KEY` | Chat 模型 | DeepSeek |
| `LLM_BASE_URL` | Chat API | `https://api.deepseek.com` |
| `EMBED_API_KEY` | 向量嵌入 | 阿里 DashScope |
| `EMBED_MODEL` | 嵌入模型 | `text-embedding-v3` |

完整列表见根目录 [README](../README.md)。

## Release

插件版本 tag：`plugin-v2.x.x`

打包范围：仅 `plugin/` 目录（`main.js`、`manifest.json`、`styles.css`）。
