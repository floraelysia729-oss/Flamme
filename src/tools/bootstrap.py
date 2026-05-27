"""工具注册引导 — 单一注册点，API 共用

所有工具在此注册一次，路由层和 Orchestrator 都调用 build_registry()。
"""

from src.tools.registry import ToolRegistry
from src.tools.markdown_parser import MarkdownParser
from src.tools.embedding_store import EmbeddingStore
from src.tools.graph_builder import GraphBuilder
from src.tools.graph_query import GraphQueryTool
from src.tools.pdf_parser import PDFParserTool
from src.tools.excalidraw_ocr import ExcalidrawOCRTool
from src.tools.glossary import GlossaryTool
from src.db.graph_store import GraphStore


def build_registry(config, db, llm=None, embedding_store=None, llm_queue=None) -> ToolRegistry:
    """构建完整工具注册表。

    Args:
        config: Config 实例
        db: SQLiteClient 实例
        llm: DefaultLLM 实例（可选，wiki 工具需要）
        embedding_store: EmbeddingStore 实例（可选，搜索工具需要）

    Returns:
        已注册所有工具的 ToolRegistry
    """
    from src.tools.wiki_ops import (
        WikiSearchTool, WikiReadPageTool, WikiCreatePageTool,
        WikiUpdatePageTool, EntityExtractTool,
    )

    from src.tools.embed_index import EmbedIndexTool

    registry = ToolRegistry()
    parser = MarkdownParser()

    # --- 基础工具 ---
    registry.register(parser)

    # --- 图谱工具 ---
    gb = GraphBuilder()
    gb._db = db
    registry.register(gb)
    graph_store = GraphStore(db._conn)
    registry.register(GraphQueryTool(graph_store=graph_store))

    # --- Wiki 工具（需要 db + 可选 llm/embedding） ---
    registry.register(WikiSearchTool(db=db, embedding_store=embedding_store, llm=llm))
    registry.register(WikiReadPageTool(db=db, parser=parser))
    registry.register(WikiCreatePageTool(db=db, vault_path=config.vault_path))
    registry.register(WikiUpdatePageTool(db=db, parser=parser))
    registry.register(EntityExtractTool(llm=llm))

    # --- 术语表 ---
    registry.register(GlossaryTool(db=db))

    # --- 文件解析工具 ---
    registry.register(PDFParserTool(
        api_token=config.mineru_api_token,
        model_version=config.mineru_model_version,
        vault_path=config.vault_path,
    ))
    registry.register(ExcalidrawOCRTool(
        api_key=config.ocr_api_key,
        base_url=config.ocr_base_url,
        model=config.ocr_model,
        vault_path=config.vault_path,
    ))

    # --- 向量索引 ---
    registry.register(EmbedIndexTool(
        db=db,
        llm=llm,
        embedding_store=embedding_store,
        parser=parser,
        llm_queue=llm_queue,
    ))

    return registry
