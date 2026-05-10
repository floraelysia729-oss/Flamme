"""具体 Worker 实现 — Ingest / Query / Lint / BatchTag

每个 Worker 只处理自己类型的 task_queue 任务。
逻辑复用自 Agent，但不走 Router。
"""

import hashlib
import json
import os
import re

from src.agent.worker import BaseWorker
from src.db.client import SQLiteClient
from src.tools.interfaces import ToolResult


class IngestWorker(BaseWorker):
    """摄入 Worker — 解析 .md 文件并写入知识库"""

    @property
    def worker_type(self) -> str:
        return "ingest"

    def _execute_task(self, payload: dict) -> str:
        path = payload.get("path", "")
        level = payload.get("level", "lite")

        if not path:
            return "错误: 未指定文件路径"

        # 相对路径 → 绝对路径
        if not os.path.isabs(path) and self._db._vault_path:
            path = os.path.join(self._db._vault_path, path)

        # 按文件类型选择处理器
        if path.endswith(".excalidraw.md"):
            return self._handle_excalidraw(path)
        elif path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            return self._handle_pdf(path, level)

        # 默认: Markdown 处理
        return self._handle_markdown(path, level)

    def _handle_markdown(self, path: str, level: str) -> str:
        parser = self._tools.get("markdown_parser")
        if not parser:
            return "错误: markdown_parser 未注册"

        parsed = self._tool_exec(parser, {"path": path})
        if "error" in parsed:
            raise ValueError(parsed["error"])

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

        # 自动 embedding
        embedded = self._auto_embed(path, content, content_hash)
        return f"已导入: {os.path.basename(path)} (level={metadata.get('level', level)})"

    def _handle_pdf(self, path: str, level: str) -> str:
        tool = self._tools.get("pdf_parse")
        if not tool:
            return "错误: pdf_parse 未注册（需配置 MINERU_API_TOKEN）"
        parsed = self._tool_exec(tool, {"path": path})
        if "error" in parsed:
            return f"PDF 解析失败: {parsed['error']}"

        markdown = parsed.get("markdown", "")
        if not markdown:
            return "PDF 解析结果为空"

        content_hash = self._compute_hash(markdown)
        self._db.put_document({
            "path": path,
            "title": os.path.splitext(os.path.basename(path))[0],
            "level": level,
            "status": "draft",
            "tags": [],
            "word_count": len(markdown),
            "content_hash": content_hash,
        })
        self._auto_embed(path, markdown, content_hash)
        return f"已导入 PDF: {path} ({len(markdown)} chars)"

    def _handle_excalidraw(self, path: str) -> str:
        tool = self._tools.get("excalidraw_ocr")
        if not tool:
            return "错误: excalidraw_ocr 未注册（需配置 OCR_API_KEY 或 EMBED_API_KEY）"
        parsed = self._tool_exec(tool, {"path": path})
        if "error" in parsed:
            return f"Excalidraw OCR 失败: {parsed['error']}"
        ocr_path = parsed.get("ocr_path", "")
        return f"已 OCR: {path} → {ocr_path} ({parsed.get('chars', '?')} chars)"

    def _auto_embed(self, doc_path: str, content: str, content_hash: str) -> bool:
        if not self._llm or not self._embedding_store:
            return False
        if self._embedding_store.has_hash(content_hash):
            return False
        try:
            embeddings = self._call_llm(self._llm.embed, [content])
            vector = embeddings[0]
            self._embedding_store.add(doc_path, vector, content_hash)
            self._db.put_embedding(doc_path, content_hash)
            return True
        except Exception:
            return False

    @staticmethod
    def _compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class QueryWorker(BaseWorker):
    """查询 Worker — 语义检索 + LLM 生成回答"""

    @property
    def worker_type(self) -> str:
        return "query"

    def _execute_task(self, payload: dict) -> str:
        question = payload.get("question", "")
        if not question:
            return "错误: 空查询"

        if not self._llm:
            return "错误: LLM 未配置"

        # 语义检索
        context_parts = []
        if self._embedding_store and self._embedding_store.count() > 0:
            context_parts = self._semantic_context(question)

        # 退回全量文档列表（含正文摘要）
        if not context_parts:
            docs = self._db.list_documents()
            parser = self._tools.get("markdown_parser") if self._tools else None
            for doc in docs[:10]:
                snippet = ""
                if parser:
                    parsed = self._tool_exec(parser, {"path": self._db.resolve(doc["path"])})
                    if "error" not in parsed:
                        snippet = parsed.get("content", "")[:500]
                context_parts.append(f"- [{doc['title']}] {snippet}")

        context = "\n".join(context_parts) if context_parts else "无文档"

        messages = [
            {"role": "system", "content": f"你是知识库助手。以下是知识库中的相关内容，请基于这些内容回答用户问题。如果内容不足以回答，请明确说明。\n\n{context}"},
            {"role": "user", "content": question},
        ]

        return self._call_llm(self._llm.complete, messages)

    def _semantic_context(self, question: str) -> list[str]:
        try:
            embeddings = self._call_llm(self._llm.embed, [question])
            query_vector = embeddings[0]
            results = self._embedding_store.search(query_vector, top_k=5)
            parser = self._tools.get("markdown_parser") if self._tools else None
            context = []
            for r in results:
                doc = self._db.get_document(r["doc_id"])
                if not doc:
                    continue
                content_snippet = ""
                if parser:
                    parsed = self._tool_exec(parser, {"path": self._db.resolve(r["doc_id"])})
                    if "error" not in parsed:
                        full_content = parsed.get("content", "")
                        content_snippet = full_content[:1500]
                entry = f"## {doc['title']} (相关度: {r['score']:.2f})\n{content_snippet}"
                context.append(entry)
            return context
        except Exception:
            return []


class LintWorker(BaseWorker):
    """Lint Worker — 知识库完整性检查"""

    @property
    def worker_type(self) -> str:
        return "lint"

    def _is_source_doc(self, path: str) -> bool:
        """判断归一化后的路径是否属于 pro/lite/raw"""
        if "copilot-custom-prompts" in path:
            return False
        return (path.startswith("pro/") or path.startswith("lite/")
                or path.startswith("raw/"))

    def _execute_task(self, payload: dict) -> str:
        docs = self._db.list_documents()
        vault = self._db._vault_path
        issues = []

        def _abs(relpath: str) -> str:
            return os.path.join(vault, relpath) if vault else relpath

        # ── 1. DB 记录 vs 实际文件 ──
        missing_files = []
        for doc in docs:
            if not os.path.isfile(_abs(doc["path"])):
                missing_files.append(doc["path"])
        if missing_files:
            issues.append(f"[文件缺失] {len(missing_files)} 个 DB 记录指向不存在的文件:")
            for f in missing_files[:10]:
                issues.append(f"  - {f}")

        # ── 2. pro/lite/raw 文档的 frontmatter 检查 ──
        fm_issues = []
        for doc in docs:
            if not self._is_source_doc(doc["path"]):
                continue

            abs_path = _abs(doc["path"])
            if not os.path.isfile(abs_path):
                continue  # 已在上面报告

            # 读文件验证 frontmatter
            try:
                text = open(abs_path, encoding="utf-8").read()
            except Exception:
                fm_issues.append(f"[读失败] {doc['path']}")
                continue

            if not text.startswith("---"):
                fm_issues.append(f"[无frontmatter] {doc['path']}")
                continue

            fm_end = text.find("---", 3)
            if fm_end < 0:
                fm_issues.append(f"[frontmatter未闭合] {doc['path']}")
                continue

            # 检查 body 中是否有 orphan tags 块
            body = text[fm_end + 3:]
            if re.search(r'^---\s*\n\s*tags:', body, re.MULTILINE):
                fm_issues.append(f"[双frontmatter] {doc['path']}")

            # 检查 tags（从文件内容而非 DB）
            fm_text = text[3:fm_end]
            has_tags = bool(re.search(r'tags:\s*(\S|\n\s*-)', fm_text))
            if not has_tags:
                fm_issues.append(f"[缺tags] {doc['path']}")

        if fm_issues:
            issues.append(f"[Frontmatter] {len(fm_issues)} 个问题:")
            for i in fm_issues[:20]:
                issues.append(f"  - {i}")
            if len(fm_issues) > 20:
                issues.append(f"  ... 还有 {len(fm_issues) - 20} 个")

        # ── 3. 图谱节点 vs 页面 ──
        graph_issues = self._check_graph_nodes(docs)
        issues.extend(graph_issues)

        if not issues:
            return f"Lint 通过: {len(docs)} 个文档，无问题"
        return f"Lint 发现 {len(docs)} 个文档中的问题:\n" + "\n".join(f"  - {i}" for i in issues)

    def _check_graph_nodes(self, docs: list[dict]) -> list[str]:
        """检查图谱中有节点但无对应页面的情况"""
        graph_tool = self._tools.get("graph_query") if self._tools else None
        if not graph_tool:
            return []

        # 从工具获取默认 graph 路径
        graph_path = getattr(graph_tool, "_default_graph_path", "")
        if not graph_path or not os.path.isfile(graph_path):
            return []

        try:
            import json as _json
            raw = _json.loads(open(graph_path, encoding="utf-8").read())
        except Exception:
            return []

        nodes = raw.get("nodes", {})
        if not nodes:
            return []

        # 从 edges 计算 degree
        from collections import Counter
        degree = Counter()
        for edge in raw.get("edges", []):
            degree[edge.get("source", "")] += 1
            degree[edge.get("target", "")] += 1

        # 建立已有页面的 path 集合（归一化后的相对路径）
        known_paths = set()
        known_titles = set()
        for doc in docs:
            known_paths.add(doc["path"])
            if doc.get("title"):
                known_titles.add(doc["title"].lower())

        # 检查图谱节点是否有对应页面
        orphans = []
        for nid, attrs in nodes.items():
            source = attrs.get("source_file", "")
            node_type = attrs.get("type", "")
            label = attrs.get("label", nid)
            deg = degree.get(nid, 0)

            # 有 source_file 的节点：归一化后比较
            if source:
                rel_source = self._db._norm(source)
                if rel_source not in known_paths and not os.path.isfile(source):
                    orphans.append(f"{label} (type={node_type}, degree={deg})")
            # 无 source_file 的实体节点（degree >= 5）：检查标题
            elif deg >= 5 and label.lower() not in known_titles:
                orphans.append(f"{label} (type={node_type}, degree={deg}, 无实体页)")

        issues = []
        if orphans:
            issues.append(f"[图谱孤立节点] {len(orphans)} 个图谱节点无对应页面:")
            for o in orphans[:15]:
                issues.append(f"  - {o}")
            if len(orphans) > 15:
                issues.append(f"  ... 还有 {len(orphans) - 15} 个")

        return issues


class BatchTagWorker(BaseWorker):
    """批量标签修复 Worker — LLM 为缺标签文档补全 tags"""

    @property
    def worker_type(self) -> str:
        return "batch_tag"

    def _execute_task(self, payload: dict) -> str:
        doc_path = payload.get("path", "")
        if not doc_path:
            return "错误: 未指定文件路径"

        # 1. 读文件
        p = __import__("pathlib").Path(doc_path)
        if not p.exists():
            return f"文件不存在: {doc_path}"

        raw = p.read_text(encoding="utf-8")

        # 解析 frontmatter
        fm_tags, content = self._parse_frontmatter_tags(raw)

        # 已有标签则跳过
        if fm_tags:
            return f"跳过（已有 {len(fm_tags)} 个标签）: {doc_path}"

        # 2. LLM 补标签
        if not self._llm:
            return f"跳过（LLM 未配置）: {doc_path}"

        new_tags = self._llm_suggest_tags(doc_path, content)
        if not new_tags:
            return f"LLM 未返回标签: {doc_path}"

        # 3. 写回 frontmatter
        updated = self._inject_tags(raw, new_tags)
        p.write_text(updated, encoding="utf-8")

        # 4. 更新 DB
        self._db.put_document({
            "path": doc_path,
            "title": __import__("os").path.splitext(__import__("os").path.basename(doc_path))[0],
            "tags": new_tags,
            "word_count": len(content),
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })

        return f"已补标签 {new_tags}: {doc_path}"

    @staticmethod
    def _parse_frontmatter_tags(text: str) -> tuple[list[str], str]:
        """提取 frontmatter 中的 tags 和正文（纯字符串解析，不依赖 yaml）"""
        if not text.startswith("---"):
            return [], text
        fm_end = text.find("---", 3)
        if fm_end < 0:
            return [], text
        fm_text = text[3:fm_end]
        content = text[fm_end + 3:].strip()

        # 字符串级别找 tags: 行
        tags = []
        in_tags = False
        for line in fm_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("tags:"):
                in_tags = True
                val = stripped[5:].strip()
                if val == "[]" or not val:
                    continue
                # inline format: tags: [a, b]
                if val.startswith("[") and val.endswith("]"):
                    tags = [t.strip().strip("\"'") for t in val[1:-1].split(",") if t.strip()]
                    break
                # tags: a  (single value)
                tags = [val.strip("\"'")]
                continue
            if in_tags and stripped.startswith("- "):
                tags.append(stripped[2:].strip("\"'"))
            elif in_tags and stripped:
                in_tags = False

        return [t for t in tags if t], content

    @staticmethod
    def _clean_orphan_tags_blocks(body: str) -> str:
        """清理正文中所有孤立的 --- tags: ... --- 块"""
        import re as _re
        # 匹配正文中的 --- tags: ... --- 块（可能跨多行）
        pattern = _re.compile(
            r"\n---\s*\n\s*tags:\s*\n(?:\s*- .+\n)*\s*---",
            _re.MULTILINE,
        )
        return pattern.sub("", body).strip()

    @staticmethod
    def _inject_tags(text: str, tags: list[str]) -> str:
        """将 tags 注入 frontmatter（纯字符串操作，不经过 YAML round-trip）"""
        tag_block = "tags:\n" + "\n".join(f"  - {t}" for t in tags)

        # 无 frontmatter → 新建
        if not text.startswith("---"):
            return f"---\n{tag_block}\n---\n{text}"

        fm_end = text.find("---", 3)
        if fm_end < 0:
            return text

        fm_text = text[3:fm_end]
        body = BatchTagWorker._clean_orphan_tags_blocks(text[fm_end + 3:])

        # 在 frontmatter 中替换或追加 tags
        lines = fm_text.split("\n")
        new_lines = []
        skip_old_tags = False
        found = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("tags:"):
                new_lines.append(tag_block)
                skip_old_tags = True
                found = True
                continue
            if skip_old_tags and (stripped.startswith("- ") or stripped.startswith("[") or stripped == "[]"):
                continue
            skip_old_tags = False
            new_lines.append(line)
        if not found:
            new_lines.append(tag_block)

        return "---\n" + "\n".join(new_lines) + "\n---\n" + body

    def _llm_suggest_tags(self, doc_path: str, content: str) -> list[str]:
        """调用 LLM 为文档推荐标签"""
        snippet = content[:2000] if content else "(空文件)"
        filename = os.path.basename(doc_path)

        messages = [
            {"role": "system", "content": (
                "你是知识库标签助手。根据文件路径和内容，推荐 3-8 个标签。\n"
                "只返回 JSON 数组，例如: [\"微积分\", \"数学\", \"极值\"]\n"
                "不要解释，只返回 JSON。"
            )},
            {"role": "user", "content": f"文件: {filename}\n路径: {doc_path}\n\n{snippet}"},
        ]
        try:
            resp = self._call_llm(self._llm.complete, messages, max_tokens=256, temperature=0)
            # 提取 JSON
            match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if match:
                tags = json.loads(match.group())
                return [t for t in tags if isinstance(t, str) and len(t) < 30]
        except Exception:
            pass
        return []
