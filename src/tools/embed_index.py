"""向量索引 Tool — 批量/单文档 embedding"""

import logging
import sys

from src.tools.interfaces import BaseTool, InterruptBehavior, ToolResult
from src.tools.sync import content_hash

logger = logging.getLogger(__name__)

MAX_CHARS = 6000
BATCH_SIZE = 10


def embed_one(db, llm, embedding_store, doc_path: str, content: str,
              content_hash_value: str, llm_queue=None) -> bool:
    """为单个文档生成 embedding。返回是否成功写入。"""
    if not llm or not embedding_store:
        return False
    if embedding_store.has_hash(content_hash_value):
        return False

    def _embed(texts):
        if llm_queue:
            return llm_queue.run(llm.embed, texts)
        return llm.embed(texts)

    try:
        vector = _embed([content])[0]
        embedding_store.add(doc_path, vector, content_hash_value)
        db.put_embedding(doc_path, content_hash_value)
        return True
    except Exception as e:
        logger.warning("[embed 失败] %s: %s", doc_path, e)
        return False


class EmbedIndexTool(BaseTool):
    """为文档批量生成向量索引"""

    name = "embed_index"
    description = "为未索引文档批量生成 embedding 向量"
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = InterruptBehavior.BLOCK

    def __init__(self, db, llm=None, embedding_store=None, parser=None, llm_queue=None):
        self._db = db
        self._llm = llm
        self._embedding_store = embedding_store
        self._parser = parser
        self._llm_queue = llm_queue

    def _call_llm(self, fn, *args, **kwargs):
        if self._llm_queue:
            return self._llm_queue.run(fn, *args, **kwargs)
        return fn(*args, **kwargs)

    def execute(self, params: dict) -> ToolResult:
        if not self._llm or not self._embedding_store:
            return ToolResult.err("LLM 或向量存储未配置")
        if not self._parser:
            return ToolResult.err("markdown_parser 未注册")

        full = params.get("full", False)
        docs = self._db.list_documents() if full else self._db.get_unembedded_docs()
        if not docs:
            return ToolResult.ok({"result": "没有需要索引的文档", "embedded": 0, "skipped": 0, "failed": 0})

        existing_hashes = self._embedding_store.get_all_hashes()
        skipped = 0
        failed = 0
        items: list[tuple[str, str, str]] = []

        for doc in docs:
            path = doc["path"]
            chash = doc.get("content_hash", "")
            if chash and chash in existing_hashes:
                skipped += 1
                continue

            parsed = self._parser.execute({"path": self._db.resolve(path)})
            if parsed.is_error:
                failed += 1
                continue

            content = parsed.data.get("content", "") if isinstance(parsed.data, dict) else ""
            if not content:
                skipped += 1
                continue

            items.append((path, content, chash or content_hash(content)))

        if not items:
            summary = f"索引完成: 新增 0, 跳过 {skipped}, 失败 {failed}"
            return ToolResult.ok({"result": summary, "embedded": 0, "skipped": skipped, "failed": failed})

        truncated = []
        for path, text, chash in items:
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS]
            truncated.append((path, text, chash))

        total_embedded = 0
        embed_failed = 0
        failed_details: list[str] = []

        for batch_start in range(0, len(truncated), BATCH_SIZE):
            batch_items = truncated[batch_start:batch_start + BATCH_SIZE]
            try:
                texts = [item[1] for item in batch_items]
                embeddings = self._call_llm(self._llm.embed, texts)
                batch = [(batch_items[j][0], embeddings[j], batch_items[j][2])
                         for j in range(len(batch_items))]
                self._embedding_store.add_batch(batch)
                for path, _, ch in batch_items:
                    self._db.put_embedding(path, ch)
                total_embedded += len(batch_items)
                print(f"  索引进度: {total_embedded}/{len(truncated)}", file=sys.stderr)
            except Exception:
                for path, text, ch in batch_items:
                    if embed_one(self._db, self._llm, self._embedding_store, path, text, ch, self._llm_queue):
                        total_embedded += 1
                    else:
                        embed_failed += 1
                        failed_details.append(path)

        summary = f"索引完成: 新增 {total_embedded}, 跳过 {skipped}, 失败 {failed + embed_failed}"
        if failed_details:
            summary += "\n失败详情:\n" + "\n".join(f"  - {d}" for d in failed_details[:20])

        return ToolResult.ok({
            "result": summary,
            "embedded": total_embedded,
            "skipped": skipped,
            "failed": failed + embed_failed,
        })

    def validate_input(self, params: dict) -> list[str]:
        return []
