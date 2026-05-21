"""单 Agent 核心 — Orchestrator 的执行层，提供各 handler 方法

Agent 不再做意图路由，所有意图识别由 Orchestrator (GLM function calling) 完成。
Agent 作为共享的工具执行层，被 Orchestrator 和 Coordinator 复用。

TS 映射: 同名 class, 同样的 run/route 分离
"""

import sys
from pathlib import Path

from src.agent.interfaces import AgentProtocol
from src.tools.registry import ToolRegistry
from src.tools.embedding_store import EmbeddingStore
from src.db.client import SQLiteClient


class Agent:
    """Agent — Orchestrator 的执行层，提供各 handler 方法"""

    def __init__(self, tools: ToolRegistry, db: SQLiteClient, llm=None,
                 embedding_store: EmbeddingStore | None = None,
                 llm_queue=None):
        self._tools = tools
        self._db = db
        self._llm = llm
        self._embedding_store = embedding_store
        self._llm_queue = llm_queue

    def _exec(self, tool_name: str, params: dict) -> dict:
        """执行工具并返回 dict（兼容旧接口）

        ToolResult → dict:  ok → {**data} 或 err → {"error": msg}
        旧式 dict → 原样返回
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return {"error": f"工具未注册: {tool_name}"}
        result = tool.execute(params)
        from src.tools.interfaces import ToolResult
        if isinstance(result, ToolResult):
            if result.is_error:
                return {"error": result.error}
            return result.data if isinstance(result.data, dict) else {"result": result.data}
        if isinstance(result, dict):
            return result
        return {"result": result}

    def _call_llm(self, fn, *args, **kwargs):
        """通过并发队列调用 LLM（无队列则直接调用）"""
        if self._llm_queue:
            return self._llm_queue.run(fn, *args, **kwargs)
        return fn(*args, **kwargs)

    def run(self, prompt: str, **kwargs) -> str:
        """默认行为：直接作为 query 处理（兼容 AgentRegistry 的简单调用）"""
        return self._handle_query({"question": prompt})

    def _handle_status(self) -> str:
        stats = self._db.get_stats()
        emb_stats = self._db.get_embedding_stats()
        lines = [
            f"文档总数: {stats['total_documents']}",
            f"  raw: {stats['by_level'].get('raw', 0)}",
            f"  lite: {stats['by_level'].get('lite', 0)}",
            f"  pro: {stats['by_level'].get('pro', 0)}",
            f"标签数: {stats['total_tags']}",
            f"向量索引: {emb_stats['embedded']}/{emb_stats['total_documents']}",
            f"最后更新: {stats['last_updated'] or '无'}",
        ]
        return "\n".join(lines)

    def _handle_scan(self) -> str:
        """扫描 vault 所有 .md 文件，导入新的，跳过已有的"""
        import os
        from pathlib import Path

        vault = self._get_vault_path()
        if not vault:
            return "错误: vault 路径未配置"

        # 跳过的目录
        skip_dirs = {".obsidian", ".wiki", ".git", "node_modules", ".trash"}

        # 收集所有 .md 文件
        md_files = []
        for root, dirs, files in os.walk(vault):
            # 就地修改 dirs 排除跳过的目录
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if f.endswith(".md") and not f.endswith(".excalidraw.md"):
                    md_files.append(os.path.join(root, f))

        if not md_files:
            return "vault 中没有 .md 文件"

        # 已有文档的 path 集合
        existing_paths = {doc["path"] for doc in self._db.list_documents()}

        # 按目录推断 level
        new_count = 0
        skip_count = 0
        error_count = 0

        parser = self._tools.get("markdown_parser")
        if not parser:
            return "错误: markdown_parser 未注册"

        for path in md_files:
            if path in existing_paths:
                skip_count += 1
                continue

            # 从路径推断 level
            rel_path = os.path.relpath(path, vault).replace("\\", "/")
            if rel_path.startswith("pro/"):
                level = "pro"
            elif rel_path.startswith("raw/"):
                level = "raw"
            else:
                level = "lite"

            try:
                parsed = self._exec("markdown_parser", {"path": path})
                if "error" in parsed:
                    error_count += 1
                    continue

                metadata = parsed.get("metadata", {})
                content = parsed.get("content", "")

                if "title" not in metadata:
                    metadata["title"] = os.path.splitext(os.path.basename(path))[0]
                if "level" not in metadata:
                    metadata["level"] = level

                content_hash = self._compute_hash(content)

                self._db.put_document({
                    "path": path,
                    "title": metadata.get("title", ""),
                    "level": metadata.get("level", level),
                    "status": metadata.get("status", "draft"),
                    "tags": metadata.get("tags", []),
                    "word_count": len(content),
                    "content_hash": content_hash,
                })

                new_count += 1
                # 进度输出（每 50 个打印一次）
                if new_count % 50 == 0:
                    print(f"  已导入 {new_count} 个...", file=sys.stderr)

            except Exception:
                error_count += 1

        lines = [
            f"扫描完成: {len(md_files)} 个 .md 文件",
            f"  新导入: {new_count}",
            f"  已存在: {skip_count}",
            f"  失败: {error_count}",
        ]
        return "\n".join(lines)

    def _handle_ingest(self, params: dict, **kwargs) -> str:
        path = params.get("path", "")
        level = kwargs.get("level", "lite")

        if not path:
            return "错误: 未指定文件路径"

        # 1. 用 markdown_parser 读取
        parser = self._tools.get("markdown_parser")
        if not parser:
            return "错误: markdown_parser 未注册"

        parsed = self._exec("markdown_parser", {"path": path})
        if "error" in parsed:
            return f"错误: {parsed['error']}"

        # 2. 写入 SQLite
        metadata = parsed.get("metadata", {})
        content = parsed.get("content", "")

        # 补全必要字段
        if "title" not in metadata:
            import os
            metadata["title"] = os.path.splitext(os.path.basename(path))[0]
        if "level" not in metadata:
            metadata["level"] = level

        content_hash = self._compute_hash(content)

        self._db.put_document({
            "path": path,
            "title": metadata.get("title", ""),
            "level": metadata.get("level", level),
            "status": metadata.get("status", "draft"),
            "tags": metadata.get("tags", []),
            "word_count": len(content),
            "content_hash": content_hash,
        })

        # 3. 自动生成 embedding（如果 LLM 和 store 可用）
        embedded = self._auto_embed(path, content, content_hash)

        embed_info = f", 向量: {'已索引' if embedded else '跳过'}"
        return f"已导入: {path} (level={metadata.get('level', level)}{embed_info})"

    def _handle_query(self, params: dict) -> str:
        question = params.get("question", "")
        if not question:
            return "错误: 空查询"

        if not self._llm:
            return "错误: LLM 未配置"

        context = self.prepare_context(question)
        messages = [
            {"role": "system", "content": f"你是知识库助手。以下是知识库中的相关内容，请基于这些内容回答用户问题。如果内容不足以回答，请明确说明。\n\n{context}"},
            {"role": "user", "content": question},
        ]

        return self._call_llm(self._llm.complete, messages)

    def prepare_context(self, question: str) -> str:
        """构建查询上下文（从 _handle_query 拆出）"""
        context_parts = []
        if self._embedding_store and self._embedding_store.count() > 0:
            context_parts = self._semantic_context(question)

        if not context_parts:
            docs = self._db.list_documents()
            parser = self._tools.get("markdown_parser")
            for doc in docs[:10]:
                snippet = ""
                if parser:
                    parsed = self._exec("markdown_parser", {"path": self._db.resolve(doc["path"])})
                    if "error" not in parsed:
                        snippet = parsed.get("content", "")[:500]
                context_parts.append(f"- [{doc['title']}] {snippet}")

        return "\n".join(context_parts) if context_parts else "无文档"

    def stream_query(self, question: str):
        """流式查询 — prepare_context + stream_complete"""
        if not self._llm:
            yield "错误: LLM 未配置"
            return

        context = self.prepare_context(question)
        messages = [
            {"role": "system", "content": f"你是知识库助手。当前日期: {self._today()}\n\n以下是知识库中的相关内容，请基于这些内容回答用户问题。如果内容不足以回答，请明确说明。\n\n{context}"},
            {"role": "user", "content": question},
        ]

        if self._llm_queue:
            gen = self._llm_queue.run(self._llm.stream_complete, messages)
        else:
            gen = self._llm.stream_complete(messages)

        for token in gen:
            yield token

    @staticmethod
    def _today() -> str:
        from datetime import date
        return date.today().isoformat()

    def _handle_index(self, params: dict) -> str:
        """全量索引 — 为所有未 embedding 的文档批量生成向量"""
        if not self._llm or not self._embedding_store:
            return "错误: LLM 或向量存储未配置"

        full = params.get("full", False)

        if full:
            docs = self._db.list_documents()
        else:
            docs = self._db.get_unembedded_docs()

        if not docs:
            return "没有需要索引的文档"

        parser = self._tools.get("markdown_parser")
        if not parser:
            return "错误: markdown_parser 未注册"

        # 一次性加载已有 hash 集合
        existing_hashes = self._embedding_store.get_all_hashes()

        skipped = 0
        failed = 0
        items = []  # (path, content, content_hash)

        for doc in docs:
            path = doc["path"]
            content_hash = doc.get("content_hash", "")

            if content_hash and content_hash in existing_hashes:
                skipped += 1
                continue

            parsed = self._exec("markdown_parser", {"path": self._db.resolve(path)})
            if "error" in parsed:
                failed += 1
                continue

            content = parsed.get("content", "")
            if not content:
                skipped += 1
                continue

            items.append((path, content, content_hash or self._compute_hash(content)))

        if not items:
            return f"索引完成: 新增 0, 跳过 {skipped}, 失败 {failed}"

        # 截断过长文本
        # text-embedding-v3 上限 8192 tokens，中文约 1 char ≈ 1.5 token
        # 保守按 6000 字符 ≈ 9000 tokens 留余量
        MAX_CHARS = 6000
        for i, (path, content, chash) in enumerate(items):
            if len(content) > MAX_CHARS:
                items[i] = (path, content[:MAX_CHARS], chash)

        # 分批 embed（千问 DashScope 限制：batch ≤ 10）
        BATCH_SIZE = 10
        total_embedded = 0
        embed_failed = 0
        failed_details = []

        for batch_start in range(0, len(items), BATCH_SIZE):
            batch_items = items[batch_start:batch_start + BATCH_SIZE]
            try:
                texts = [item[1] for item in batch_items]
                embeddings = self._call_llm(self._llm.embed, texts)
                batch = [(batch_items[j][0], embeddings[j], batch_items[j][2])
                         for j in range(len(batch_items))]
                self._embedding_store.add_batch(batch)
                for path, _, content_hash in batch_items:
                    self._db.put_embedding(path, content_hash)
                total_embedded += len(batch_items)
                print(f"  索引进度: {total_embedded}/{len(items)}", file=sys.stderr)
            except Exception as batch_err:
                # 批次失败 → 逐个重试，隔离问题文档
                for path, content, chash in batch_items:
                    try:
                        emb = self._call_llm(self._llm.embed, [content])
                        self._embedding_store.add(path, emb[0], chash)
                        self._db.put_embedding(path, chash)
                        total_embedded += 1
                    except Exception as e:
                        embed_failed += 1
                        failed_details.append(f"{path}: {e}")

        result = f"索引完成: 新增 {total_embedded}, 跳过 {skipped}, 失败 {failed + embed_failed}"
        if failed_details:
            result += "\n失败详情:\n" + "\n".join(f"  - {d}" for d in failed_details[:20])
        return result

    def _handle_search(self, params: dict) -> str:
        """纯语义搜索（不经过 LLM）"""
        query = params.get("query", "")
        top_k = params.get("top_k", 5)

        if not query:
            return "错误: 空搜索"

        if not self._embedding_store or self._embedding_store.count() == 0:
            return "向量索引为空，请先运行 llm-wiki index"

        if not self._llm:
            return "错误: LLM 未配置"

        # 生成 query embedding
        try:
            embeddings = self._call_llm(self._llm.embed, [query])
            query_vector = embeddings[0]
        except Exception as e:
            return f"错误: Embedding 生成失败: {e}"

        results = self._embedding_store.search(query_vector, top_k=top_k)
        if not results:
            return "无结果"

        lines = [f"语义搜索: '{query}' (top {top_k})", ""]
        for i, r in enumerate(results, 1):
            doc = self._db.get_document(r["doc_id"])
            title = doc["title"] if doc else r["doc_id"]
            lines.append(f"  {i}. [{r['score']:.3f}] {title} ({r['doc_id']})")

        return "\n".join(lines)

    def _semantic_context(self, question: str) -> list[str]:
        """语义检索 → 读取相关文档正文 → 构建富 context"""
        try:
            embeddings = self._call_llm(self._llm.embed, [question])
            query_vector = embeddings[0]
            results = self._embedding_store.search(query_vector, top_k=5)
            parser = self._tools.get("markdown_parser")
            context = []
            for r in results:
                doc = self._db.get_document(r["doc_id"])
                if not doc:
                    continue
                # 读取文件正文
                content_snippet = ""
                if parser:
                    parsed = self._exec("markdown_parser", {"path": self._db.resolve(r["doc_id"])})
                    if "error" not in parsed:
                        full_content = parsed.get("content", "")
                        content_snippet = full_content[:1500]
                entry = f"## {doc['title']} (相关度: {r['score']:.2f})\n{content_snippet}"
                context.append(entry)
            return context
        except Exception:
            return []

    def _auto_embed(self, doc_path: str, content: str, content_hash: str) -> bool:
        """自动为文档生成 embedding。返回是否成功"""
        if not self._llm or not self._embedding_store:
            return False

        # hash 去重
        if self._embedding_store.has_hash(content_hash):
            return False

        try:
            embeddings = self._call_llm(self._llm.embed, [content])
            vector = embeddings[0]
            self._embedding_store.add(doc_path, vector, content_hash)
            self._db.put_embedding(doc_path, content_hash)
            return True
        except Exception as e:
            print(f"[embed 失败] {doc_path}: {e}", file=sys.stderr)
            return False

    def _handle_graph(self, params: dict) -> str:
        """图谱操作：构建 / 查询 / 社区 / 孤立检测"""
        action = params.get("action", "build")
        graph_tool = self._tools.get("graph_query")
        build_tool = self._tools.get("graph_builder")

        if action == "build":
            if not build_tool:
                return "错误: graph_builder 未注册"
            result = self._exec("graph_builder", {"vault_path": self._get_vault_path()})
            if "error" in result:
                return f"错误: {result['error']}"
            return f"图谱构建完成: {result['nodes']} 节点, {result['edges']} 边, {result['communities']} 社区"

        # 查询类操作需要 graph.json
        graph_path = self._get_graph_path()
        if not graph_path:
            return "错误: vault 路径未配置"

        if not graph_tool:
            return "错误: graph_query 未注册"

        if action == "query":
            query = params.get("query", "")
            if not query:
                return "错误: 请指定查询节点"
            result = self._exec("graph_query", {"graph_path": graph_path, "action": "neighbors", "node": query})
            if "error" in result:
                return f"错误: {result['error']}"
            lines = [f"节点: {result['node']['label']} (度: {result['degree']})"]
            for n in result["neighbors"]:
                lines.append(f"  - {n['label']} [{n.get('relation', '')}]")
            return "\n".join(lines)

        elif action == "isolates":
            result = self._exec("graph_query", {"graph_path": graph_path, "action": "isolates"})
            if "error" in result:
                return f"错误: {result['error']}"
            if result["count"] == 0:
                return "无孤立节点"
            lines = [f"孤立节点 ({result['count']}):"]
            for n in result["isolates"]:
                lines.append(f"  - {n['label']}")
            return "\n".join(lines)

        elif action == "community":
            result = self._exec("graph_query", {"graph_path": graph_path, "action": "community"})
            if "error" in result:
                return f"错误: {result['error']}"
            lines = [f"社区总数: {result['total']}"]
            for c in result["communities"]:
                lines.append(f"  社区 {c['community_id']}: {c['size']} 节点")
            return "\n".join(lines)

        return f"未知图谱操作: {action}"

    def _get_vault_path(self) -> str:
        """返回 vault 路径（直接从 DB 读取）"""
        return self._db._vault_path or ""

    def _get_graph_path(self) -> str:
        """返回 graph.json 路径（从 db 的 vault_path 派生，不调 load_config）"""
        vault = self._db._vault_path or ""
        if not vault:
            return ""
        gfile = Path(vault) / ".wiki" / "graph.json"
        return str(gfile) if gfile.exists() else ""

    @staticmethod
    def _compute_hash(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
